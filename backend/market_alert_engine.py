"""
市场指标异动检测 + 定时调度器（运行于 Flask 后端进程）
======================================================
复用 modules.market_drivers.get_market_drivers 取数（与前端 P_市场情绪 页同口径），
对广度 / 情绪 / 估值 / 宏观 / 技术 类关键指标做阈值越界判定，
按「冷却去重」写入 market_alerts 表，前端铃铛读取未读。

设计要点：
- 阈值语义与 CSV 指标表 / P 页信号灯一致（高=过热/冷、低=恐慌/低估 等）。
- 冷却：同一指标 6 小时内只告警一次，避免盘中反复刷屏。
- 交易时段才扫描（北京时间 09:00–15:30，周一至周五），其余时段休眠。
- 调度器为守护线程，测试环境（pytest）与 STOCKSIGNAL_ENABLE_ALERT_SCHEDULER=0 时自动跳过。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from .extensions import db
from .models import MarketAlert
from .market_alert_config import get_alert_config, resolve_rules

logger = logging.getLogger(__name__)

COOLDOWN_HOURS = 6
SCAN_INTERVAL_MINUTES = 15
INITIAL_DELAY_SECONDS = 10
_SCHEDULER_STARTED = False

# 规则表：仅用 warn_/danger_ 阈值判定；hi_msg/lo_msg 为触发的文案。
# 对 PMI / 长短利差 / 股息率 等「越低越差」的指标，用 warn_lo/danger_lo 表达低位风险。
RULES = [
    dict(key="adr", name="涨跌比率(ADR)", warn_hi=1.4, danger_hi=1.8, warn_lo=0.6, danger_lo=0.4,
         hi_msg="涨跌比率过热（赚钱效应极端）", lo_msg="涨跌比率恐慌（个股普跌）"),
    dict(key="vix", name="VIX恐慌指数", warn_hi=20, danger_hi=30,
         hi_msg="恐慌指数走高（避险情绪升温）"),
    dict(key="pcr", name="PCR(认沽/认购比)", warn_hi=1.0, danger_hi=1.2,
         hi_msg="认沽认购比偏高（市场避险）"),
    dict(key="zt_ratio", name="涨停家数占比", warn_hi=3.0, danger_hi=5.0,
         hi_msg="涨停占比偏高（情绪过热）"),
    dict(key="pe_pct", name="PE历史百分位", warn_hi=80, danger_hi=90, warn_lo=20,
         hi_msg="市场估值偏高", lo_msg="市场估值偏低（配置价值凸显）"),
    dict(key="div_yield", name="股息率", warn_hi=3.5,
         hi_msg="股息率走高（指数低迷，配置价值上升）"),
    dict(key="north_net", name="北向资金净流入", warn_hi=100, danger_hi=200, warn_lo=-100, danger_lo=-200,
         hi_msg="北向资金大幅净流入", lo_msg="北向资金大幅净流出"),
    dict(key="margin_net", name="融资净买入额", warn_hi=100, danger_hi=200, warn_lo=-50, danger_lo=-100,
         hi_msg="融资盘大幅净买入", lo_msg="融资盘大幅净偿还"),
    dict(key="pmi", name="PMI", warn_lo=50, danger_lo=48,
         lo_msg="制造业景气跌破荣枯线（PMI<50）"),
    dict(key="rsi", name="RSI", warn_hi=70, danger_hi=80, warn_lo=30, danger_lo=20,
         hi_msg="RSI 超买", lo_msg="RSI 超卖"),
    dict(key="bias", name="价格乖离率", warn_hi=8, danger_hi=12, warn_lo=-8, danger_lo=-12,
         hi_msg="价格大幅正乖离（有回拉压力）", lo_msg="价格大幅负乖离（有修复动力）"),
    dict(key="yield_spread", name="长短期利差", warn_lo=0, danger_lo=-0.2,
         lo_msg="长短利差倒挂（衰退风险）"),
    dict(key="nhnl", name="新高新低指标", warn_lo=-200, danger_lo=-500,
         lo_msg="新高新低转负（市场广度恶化）"),
]

# 正向触发（数值偏高）但属「利好」的指标：severity 降为 info
_POSITIVE_HI = {"north_net", "margin_net"}


def _beijing_now() -> datetime:
    return datetime.utcnow() + timedelta(hours=8)


def _in_trading_window() -> bool:
    """北京时间周一至周五 09:00–15:30 视为交易时段。"""
    t = _beijing_now()
    if t.weekday() >= 5:  # 周六(5)/周日(6)
        return False
    if (t.hour, t.minute) < (9, 0) or (t.hour, t.minute) > (15, 30):
        return False
    return True


def _latest_two(series):
    """返回 (latest, prev) 最近两个非 NaN 值。"""
    if series is None:
        return None, None
    vals = [float(v) for v in series.dropna().tolist()]
    if not vals:
        return None, None
    latest = vals[-1]
    prev = vals[-2] if len(vals) >= 2 else None
    return latest, prev


def _evaluate(rule: dict, latest, prev):
    """阈值判定，返回 (severity, message, threshold) 或 None。"""
    if latest is None:
        return None
    key = rule["key"]
    if rule.get("danger_hi") is not None and latest >= rule["danger_hi"]:
        sev = "info" if key in _POSITIVE_HI else "danger"
        return sev, rule.get("hi_msg") or f"{rule['name']} 触及危险高位 {latest:.2f}", rule["danger_hi"]
    if rule.get("warn_hi") is not None and latest >= rule["warn_hi"]:
        sev = "info" if key in _POSITIVE_HI else "warning"
        return sev, rule.get("hi_msg") or f"{rule['name']} 偏高 {latest:.2f}", rule["warn_hi"]
    if rule.get("danger_lo") is not None and latest <= rule["danger_lo"]:
        return "danger", rule.get("lo_msg") or f"{rule['name']} 触及危险低位 {latest:.2f}", rule["danger_lo"]
    if rule.get("warn_lo") is not None and latest <= rule["warn_lo"]:
        return "warning", rule.get("lo_msg") or f"{rule['name']} 偏低 {latest:.2f}", rule["warn_lo"]
    return None


def detect_anomalies(df, meta=None) -> list:
    """给定 market_drivers 的 (df, meta)，返回告警 dict 列表（未去重）。"""
    out = []
    if df is None or getattr(df, "empty", True):
        return out
    for rule in resolve_rules(RULES):
        key = rule["key"]
        if key not in df.columns:
            continue
        latest, prev = _latest_two(df[key])
        res = _evaluate(rule, latest, prev)
        if res:
            sev, msg, thr = res
            out.append({
                "metric_key": key,
                "metric_name": rule["name"],
                "severity": sev,
                "message": msg,
                "value": latest,
                "threshold": thr,
            })
    return out


def scan_and_store(commit: bool = True) -> int:
    """拉取最新市场数据，检测异动，按冷却去重写库。返回新增条数。"""
    try:
        from modules.market_drivers import get_market_drivers
    except Exception as e:  # noqa: BLE001
        logger.warning("无法导入 modules.market_drivers：%s", e)
        return 0
    try:
        df, meta = get_market_drivers(days=180)
    except Exception as e:  # noqa: BLE001
        logger.warning("market_drivers 取数失败：%s", e)
        return 0

    anomalies = detect_anomalies(df, meta)
    if not anomalies:
        return 0

    cooldown_hours = get_alert_config().get("cooldown_hours", COOLDOWN_HOURS)
    cutoff = datetime.utcnow() - timedelta(hours=cooldown_hours)
    inserted = 0
    for a in anomalies:
        recent = db.session.execute(
            select(MarketAlert).where(
                MarketAlert.metric_key == a["metric_key"],
                MarketAlert.created_at > cutoff,
            )
        ).scalars().first()
        if recent:
            continue  # 冷却期内已告警，跳过
        db.session.add(MarketAlert(
            metric_key=a["metric_key"],
            metric_name=a["metric_name"],
            severity=a["severity"],
            message=a["message"],
            value=a["value"],
            threshold=a["threshold"],
        ))
        inserted += 1

    if inserted and commit:
        try:
            db.session.commit()
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            logger.warning("写入市场异动告警失败：%s", e)
            return 0
    return inserted


def start_alert_scheduler(app, interval_minutes: int = SCAN_INTERVAL_MINUTES) -> None:
    """在 Flask 进程内启动守护线程定时扫描。测试/禁用环境下自动跳过。"""
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if os.environ.get("PYTEST_CURRENT_TEST") or app.config.get("TESTING"):
        logger.info("检测到测试环境，跳过市场异动调度器")
        return
    if os.environ.get("STOCKSIGNAL_ENABLE_ALERT_SCHEDULER", "1") == "0":
        logger.info("STOCKSIGNAL_ENABLE_ALERT_SCHEDULER=0，跳过市场异动调度器")
        return
    cfg = get_alert_config()
    interval_minutes = int(cfg.get("scan_interval_minutes", SCAN_INTERVAL_MINUTES))
    initial_delay = int(cfg.get("initial_delay_seconds", INITIAL_DELAY_SECONDS))
    _SCHEDULER_STARTED = True

    def _loop() -> None:
        time.sleep(initial_delay)
        while True:
            try:
                if _in_trading_window():
                    with app.app_context():
                        n = scan_and_store()
                        if n:
                            app.logger.info("市场异动扫描：新增 %d 条告警", n)
            except Exception as e:  # noqa: BLE001
                app.logger.warning("市场异动扫描异常：%s", e)
            time.sleep(interval_minutes * 60)

    t = threading.Thread(target=_loop, daemon=True, name="market-alert-scheduler")
    t.start()
    app.logger.info("市场异动调度器已启动（间隔 %d 分钟，仅交易时段扫描）", interval_minutes)
