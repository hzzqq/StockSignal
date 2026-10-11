"""
backend/recommend_scheduler.py
------------------------------
每日荐股调度器（T-233）：每交易日收盘后（北京时间 ≥15:30）自动生成当日推荐并落盘。

范式抄 market_alert_engine（守护线程 + 幂等 + 测试跳过三件套），窗口判断改为：
「工作日 & 时间 ≥15:30 & 今日 data/recommendations/YYYY-MM-DD.json 尚不存在」，
幂等由 today_generated() 保证，绝不重复生成。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

_SCHEDULER_STARTED = False
_SCAN_INTERVAL_MINUTES = 20


def _after_close_cst(now: datetime | None = None) -> bool:
    """北京时间工作日 15:30 之后（含周末不生成）。"""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    return now.hour > 15 or (now.hour == 15 and now.minute >= 30)


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
                    _generate_once()
            except Exception as e:  # noqa: BLE001 — 调度循环永不中断
                logger.warning("[recommend_scheduler] 生成失败（下轮重试）: %s", e)
            time.sleep(max(5, interval_minutes) * 60)

    t = threading.Thread(target=_loop, name="recommend-scheduler", daemon=True)
    t.start()
    logger.info("荐股调度器已启动（间隔 %d 分钟，交易日 15:30 后生成）", interval_minutes)
