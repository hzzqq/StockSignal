"""
backend/recommend_scheduler.py
------------------------------
每日荐股调度器（T-233）：每交易日收盘后（北京时间 ≥15:30）自动生成当日推荐并落盘。

范式抄 market_alert_engine（守护线程 + 幂等 + 测试跳过三件套），窗口判断改为：
「工作日 & 时间 ≥15:30 & 今日 data/recommendations/YYYY-MM-DD.json 尚不存在」，
幂等由 today_generated() 保证，绝不重复生成。

T-236 判活（long-running-task-healthcheck 范式）：assess_recommend_health() 读归档目录
最新日期判 ok/warn/dead——防「调度器静默停摆、页面照常等推荐」（决策闭环 09-10/09-15 事故同款）。
T-237 推送：生成成功后可选微信推送摘要（STOCKSIGNAL_RECOMMEND_PUSH=1 开启，默认关；
复用 modules/push_channel，失败留痕不阻断主流程，绝不谎报已推送）。
T-250 缓存预热：生成前先跑 modules.cache_warmer.warm_universe（引擎同参拉候选池日线，
cache.db 即检查点、TTL 内自动跳过＝幂等），把「生成时才发现取不到」变「闲时充分重试」；
SS_CACHE_WARM=0 可关；预热失败不阻断生成（荐股侧有 T-248 诚实兜底标注）。
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

_SCHEDULER_STARTED = False
_SCAN_INTERVAL_MINUTES = 20


def _after_close_cst(now: datetime | None = None) -> bool:
    """北京时间工作日 15:30 之后（含周末不生成）。"""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    return now.hour > 15 or (now.hour == 15 and now.minute >= 30)


def _last_expected_trade_date(now: datetime) -> date:
    """最近一个「应已生成荐股」的工作日：今天（工作日且已过 15:30）或往前最近的工作日。"""
    d = now.date()
    if not (d.weekday() < 5 and (now.hour > 15 or (now.hour == 15 and now.minute >= 30))):
        d = d - timedelta(days=1)  # 今天窗口未到，至少昨天应已生成
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _prev_trade_date(d: date) -> date:
    p = d - timedelta(days=1)
    while p.weekday() >= 5:
        p -= timedelta(days=1)
    return p


def assess_recommend_health(now: datetime | None = None, data_dir: str = None) -> dict:
    """T-236：荐股调度健康（纯函数，94 页消息中心告警用）。

    以「最近应生成的工作日」为基准（自然工作日粗口径，**不含法定节假日**，如实注明）：
    - latest ≥ 基准 → ok
    - latest == 基准的前一个工作日（只缺最近一轮）→ warn
    - 更旧 / 目录为空 → dead
    """
    now = now or datetime.now()
    try:
        from modules.recommend_engine import rec_paths

        archive_dir = os.path.dirname(rec_paths(data_dir)[0])
        names = os.listdir(archive_dir) if os.path.isdir(archive_dir) else []
    except Exception as e:  # noqa: BLE001 — 健康检查自身失败也要如实上报，不静默
        return {"status": "dead", "latest": None, "age_days": None,
                "message": f"健康检查失败：{type(e).__name__}: {e}"}
    dates = sorted(m[:-5] for m in names if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", m))
    if not dates:
        return {"status": "dead", "latest": None, "age_days": None, "message": "从未生成过荐股"}
    latest = date.fromisoformat(dates[-1])
    expected = _last_expected_trade_date(now)
    age = (now.date() - latest).days
    if latest >= expected:
        status, msg = "ok", f"最新荐股 {latest}"
    elif latest == _prev_trade_date(expected):
        status = "warn"
        msg = f"最新荐股停在 {latest}（{age} 天前），最近一轮（{expected}）尚未生成"
    else:
        status = "dead"
        msg = f"荐股已 {age} 天未更新（最新 {latest}），调度器可能停摆"
    return {"status": status, "latest": dates[-1], "age_days": age, "message": msg}


def _maybe_push(rec: dict) -> None:
    """T-237：生成成功后可选微信推送摘要（默认关；失败留痕绝不谎报）。"""
    if os.environ.get("STOCKSIGNAL_RECOMMEND_PUSH", "0") != "1":
        return
    try:
        from modules.push_channel import push_text

        picks = rec.get("picks") or []
        lines = [f"📅 每日荐股 {rec.get('date')}（{len(picks)} 只）"]
        for i, p in enumerate(picks[:3], 1):
            lines.append(f"{i}. {p.get('name', '')}（{p.get('code')}）综合 {p.get('composite', '—')} 分")
        stale = rec.get("data_staleness") or {}
        if stale.get("stale"):
            lines.append(f"⚠️ {stale.get('note', '行情数据滞后')}")
        lines.append("模拟统计与免责详见「每日荐股」页；不构成投资建议。")
        res = push_text("\n".join(lines))
        ok = bool(res.get("ok")) if isinstance(res, dict) else False
        logger.info("[recommend_scheduler] 微信推送%s: %s", "成功" if ok else "未成功", res)
    except Exception as e:  # noqa: BLE001 — 推送失败不影响推荐主流程，但必须留痕
        logger.warning("[recommend_scheduler] 微信推送异常: %s", e)


def _warm_once() -> None:
    """T-250：荐股生成前预热日线缓存（引擎同参；失败留痕不阻断生成）。"""
    try:
        from modules.cache_warmer import warm_universe

        res = warm_universe()
        logger.info("[recommend_scheduler] 缓存预热 warmed=%s failed=%s total=%s %ss%s",
                    res.get("warmed"), res.get("failed"), res.get("total"),
                    res.get("elapsed_s"), f" | {res['reason']}" if res.get("reason") else "")
    except Exception as e:  # noqa: BLE001 — 预热失败绝不阻断荐股主流程，但必须留痕
        logger.warning("[recommend_scheduler] 缓存预热异常（不阻断生成）: %s", e)


def _generate_once() -> dict | None:
    """生成当日推荐（幂等：已有当日文件则跳过）。返回 rec 或 None。"""
    from modules.recommend_engine import generate_daily_recommendation, today_generated
    if today_generated():
        return None
    steps = {"p": 0.0}

    def progress(pct, msg):
        steps["p"] = pct
        logger.info("[recommend_scheduler] %.0f%% %s", pct * 100, msg)

    rec = generate_daily_recommendation(progress=progress)
    logger.info("[recommend_scheduler] 当日推荐生成完成 status=%s picks=%s",
                rec.get("status"), len(rec.get("picks", [])) if isinstance(rec.get("picks"), list) else 0)
    if rec.get("status") == "ok" and rec.get("picks"):
        _maybe_push(rec)
    return rec


def start_recommend_scheduler(app, *, interval_minutes: int = _SCAN_INTERVAL_MINUTES) -> None:
    """启动荐股守护线程（测试/禁用环境自动跳过）。"""
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if os.environ.get("PYTEST_CURRENT_TEST") or app.config.get("TESTING"):
        logger.info("检测到测试环境，跳过荐股调度器")
        return
    if os.environ.get("STOCKSIGNAL_ENABLE_RECOMMEND_SCHEDULER", "1") == "0":
        logger.info("STOCKSIGNAL_ENABLE_RECOMMEND_SCHEDULER=0，跳过荐股调度器")
        return
    _SCHEDULER_STARTED = True

    def _loop() -> None:
        # 启动后先等 90s，让 Flask/数据源热身
        time.sleep(90)
        while True:
            try:
                if _after_close_cst() and not os.environ.get("STOCKSIGNAL_RECOMMEND_FORCE_OFF"):
                    _warm_once()
                    _generate_once()
            except Exception as e:  # noqa: BLE001 — 调度循环永不中断
                logger.warning("[recommend_scheduler] 生成失败（下轮重试）: %s", e)
            time.sleep(max(5, interval_minutes) * 60)

    t = threading.Thread(target=_loop, name="recommend-scheduler", daemon=True)
    t.start()
    logger.info("荐股调度器已启动（间隔 %d 分钟，交易日 15:30 后生成）", interval_minutes)
