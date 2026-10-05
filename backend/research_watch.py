"""backend/research_watch.py — H1+ 方向 B：研究智能体定时自驱盯盘（编排薄层）。

定位：把研究智能体从「用户提问才跑」升级为「**盯到异动 → 自驱发起针对性研究 → 落库 + 推送**」。

**复用优先（不新建调度框架）**：
- 触发源 = `backend.market_alert_engine` 产出的 `market_alerts`（其已有 15min 扫描 / 6h 冷却 /
  交易时段 / pytest 自动跳过）。
- 研究执行 = `modules.research_agent.run_research`（**自带只读红线 AC3 + 有界 clamp AC2 + 溯源 AC4/AC5**）。
- 推送 = 复用既有消息中心 / 桌面通知通道（本模块只落库，推送由调用方按需接）。

设计铁律：
- **AC-B1 只读红线不回退**：本模块**只读告警、只调研究**，绝不触发任何写操作/下单。
- **AC-B2 有界**：单次 `max_steps`/`budget_s` 沿用 H1 clamp；**全局配额**（每轮最小间隔）+
  **同触发源冷却**（按 metric_key 去重）双重闸。
- **AC-B3 诚实降级**：研究 `status` 原样落库（unavailable 就是 unavailable），绝不改写成 ok。
- **AC-B4 测试隔离**：pytest / TESTING / `STOCKSIGNAL_ENABLE_RESEARCH_WATCH=0` 下**不启动**调度线程。
- **AC-B6 时段与去重**：非交易时段休眠（复用 alert 引擎 `_in_trading_window`）；同 metric_key 冷却期内不重复研究。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 全局配额：两次自驱研究至少间隔（秒）——防 LLM 成本失控
MIN_INTERVAL_SECONDS = 1800          # 30 分钟
# 同一触发指标（metric_key）冷却：避免同一异动反复研究
PER_TRIGGER_COOLDOWN_SECONDS = 6 * 3600   # 6 小时
# 单次研究的步数/时间预算（沿用 H1 的有界约定）
MAX_STEPS = 4
BUDGET_S = 60.0
SCAN_INTERVAL_MINUTES = 15
INITIAL_DELAY_SECONDS = 30

_SCHEDULER_STARTED = False
# 运行时状态（进程内；重启清零）
_last_global_ts: float = 0.0
_last_trigger_ts: dict[str, float] = {}


def build_question(alert: dict) -> str:
    """由一条异动告警组装**只读**研究问题（纯函数，便于离线单测）。

    只描述「发生了什么 + 请分析原因与影响」，**不含任何操作指令**（守 AC-B1 只读红线）。
    """
    a = alert or {}
    name = str(a.get("metric_name") or a.get("metric_key") or "市场指标")
    sev = {"danger": "严重", "warning": "偏警", "warn": "偏警", "info": "提示"}.get(
        str(a.get("severity") or "info"), "提示")
    msg = str(a.get("message") or "").strip()
    value = a.get("value")
    extra = f"，当前值 {value}" if value is not None else ""
    tail = f"（{msg}{extra}）" if (msg or value is not None) else ""
    return (f"【自驱盯盘·{sev}】{name} 出现异动{tail}。请分析该异动的可能原因、"
            f"对市场与相关板块的影响，以及后续需要关注的风险信号。"
            f"仅做研究与信息汇总，不给出任何交易操作建议。")


def _norm_alert(alert) -> dict:
    """把 ORM 行 / dict 归一为纯 dict（便于离线测试）。"""
    if alert is None:
        return {}
    if isinstance(alert, dict):
        return dict(alert)
    return {
        "id": getattr(alert, "id", None),
        "metric_key": getattr(alert, "metric_key", None),
        "metric_name": getattr(alert, "metric_name", None),
        "severity": getattr(alert, "severity", None),
        "message": getattr(alert, "message", None),
        "value": getattr(alert, "value", None),
        "created_at": getattr(alert, "created_at", None),
    }


def gate_allows(now_ts: float, metric_key: str | None, *,
                last_global_ts: float = None, last_trigger_ts: dict | None = None,
                min_interval: int = MIN_INTERVAL_SECONDS,
                cooldown: int = PER_TRIGGER_COOLDOWN_SECONDS) -> tuple[bool, str]:
    """配额 + 冷却双闸（纯函数）。返回 ``(是否放行, 原因)``。"""
    lg = _last_global_ts if last_global_ts is None else last_global_ts
    lt = _last_trigger_ts if last_trigger_ts is None else last_trigger_ts
    if lg and (now_ts - lg) < min_interval:
        return False, f"全局配额冷却中（距上次 {int(now_ts - lg)}s < {min_interval}s）"
    if metric_key and lt.get(metric_key) and (now_ts - lt.get(metric_key)) < cooldown:
        return False, f"同触发源 {metric_key} 冷却中（< {cooldown}s）"
    return True, "ok"


def run_watch_once(*, alert, research_fn=None, persist_fn=None, now=None,
                   max_steps: int = MAX_STEPS, budget_s: float = BUDGET_S) -> dict:
    """执行一次自驱研究（可注入 research_fn/persist_fn，离线可测）。

    :return: 研究记录 dict（含 trigger/question/status/answer/citations/limitations/created_at）
    """
    a = _norm_alert(alert)
    question = build_question(a)
    if research_fn is None:
        from modules.research_agent import run_research as research_fn  # 延迟导入（含只读红线）
    res = research_fn(question, max_steps=max_steps, budget_s=budget_s) or {}
    record = {
        "trigger": {"metric_key": a.get("metric_key"), "metric_name": a.get("metric_name"),
                    "severity": a.get("severity"), "alert_id": a.get("id")},
        "question": question,
        "status": res.get("status", "unavailable"),        # AC-B3：原样透传，不粉饰
        "answer": res.get("answer", ""),
        "citations": res.get("citations", []),
        "limitations": res.get("limitations", []),
        "steps": res.get("steps", []),
        "created_at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    if persist_fn is not None:
        try:
            persist_fn(record)
        except Exception as e:  # noqa: BLE001
            # 诚实降级：落库失败须留痕，绝不谎报成功
            logger.warning("自驱研究落库失败：%s", e)
    return record


def persist_run(record: dict) -> None:
    """把研究记录落库（AC-B5 可追溯）。失败**抛异常**由调用方留痕，绝不静默。"""
    import json as _json

    from .extensions import db
    from .models import ResearchRun
    t = record.get("trigger") or {}
    db.session.add(ResearchRun(
        trigger_metric_key=t.get("metric_key"),
        trigger_metric_name=t.get("metric_name"),
        trigger_severity=t.get("severity"),
        alert_id=t.get("alert_id"),
        question=record.get("question", ""),
        status=record.get("status", "unavailable"),
        answer=record.get("answer", ""),
        citations_json=_json.dumps(record.get("citations", []), ensure_ascii=False),
        limitations_json=_json.dumps(record.get("limitations", []), ensure_ascii=False),
    ))
    db.session.commit()


def _mark_ran(now_ts: float, metric_key: str | None) -> None:
    global _last_global_ts
    _last_global_ts = now_ts
    if metric_key:
        _last_trigger_ts[metric_key] = now_ts


def notify_run(trigger: dict, record: dict) -> None:
    """研究完成后的桌面弹窗通知（T-216，复用 conditional_engine 的 desktop_notify 先例）。

    - ``STOCKSIGNAL_RESEARCH_NOTIFY=0`` 关闭（默认开）；
    - 通知异步非阻塞，失败只留痕，绝不影响研究/调度链路。
    """
    if os.environ.get("STOCKSIGNAL_RESEARCH_NOTIFY", "1") == "0":
        return
    try:
        from .desktop_notify import notify as _notify
        name = (trigger or {}).get("metric_name") or (trigger or {}).get("metric_key") or "市场异动"
        _notify("🛰️ 自驱研究完成",
                f"{name}：status={record.get('status')}（详见 消息中心/星辰AI）")
    except Exception as e:  # noqa: BLE001
        logger.debug("自驱研究桌面通知失败（不影响链路）: %s", e)


def latest_unprocessed_alert(app):
    """取最近一条「尚未被自驱研究过」的告警（只读）。无则 None。

    通过 ``ResearchRun.alert_id`` 反查已研究过的告警并排除，令「unprocessed」名副其实，
    避免冷却期过后的同一告警被反复研究（AC-B6 去重）。
    """
    try:
        from sqlalchemy import select
        from .models import MarketAlert, ResearchRun
        from .extensions import db
        researched = select(ResearchRun.alert_id).where(ResearchRun.alert_id.isnot(None))
        row = db.session.execute(
            select(MarketAlert)
            .where(MarketAlert.id.notin_(researched))
            .order_by(MarketAlert.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row
    except Exception as e:  # noqa: BLE001
        logger.warning("读取市场告警失败（自驱研究跳过本轮）：%s", e)
        return None


def start_research_watch_scheduler(app, *, interval_minutes: int = SCAN_INTERVAL_MINUTES) -> None:
    """启动自驱研究守护线程（AC-B4：测试/禁用环境自动跳过；AC-B6：仅交易时段）。"""
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if os.environ.get("PYTEST_CURRENT_TEST") or app.config.get("TESTING"):
        logger.info("检测到测试环境，跳过自驱研究调度器")
        return
    if os.environ.get("STOCKSIGNAL_ENABLE_RESEARCH_WATCH", "1") == "0":
        logger.info("STOCKSIGNAL_ENABLE_RESEARCH_WATCH=0，跳过自驱研究调度器")
        return
    _SCHEDULER_STARTED = True

    def _loop() -> None:
        time.sleep(INITIAL_DELAY_SECONDS)
        from .market_alert_engine import _in_trading_window
        while True:
            try:
                if _in_trading_window():
                    with app.app_context():
                        alert = latest_unprocessed_alert(app)
                        if alert is not None:
                            a = _norm_alert(alert)
                            now_ts = time.time()
                            ok, why = gate_allows(now_ts, a.get("metric_key"))
                            if ok:
                                rec = run_watch_once(alert=a, persist_fn=persist_run)
                                _mark_ran(now_ts, a.get("metric_key"))
                                notify_run(a, rec)
                                app.logger.info("自驱研究完成：%s（status=%s）",
                                                a.get("metric_name"), rec.get("status"))
                            else:
                                app.logger.info("自驱研究跳过：%s", why)
            except Exception as e:  # noqa: BLE001
                app.logger.warning("自驱研究调度异常：%s", e)
            time.sleep(interval_minutes * 60)

    threading.Thread(target=_loop, daemon=True, name="research-watch-scheduler").start()
    app.logger.info("自驱研究调度器已启动（间隔 %d 分钟，仅交易时段）", interval_minutes)
