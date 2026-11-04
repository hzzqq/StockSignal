"""backend/p1_sync_scheduler.py
-------------------------------
P1 信号同步守护线程（T-XXX 方向：把一次性同步脚本变成每日流水线）。

范式与 ``backend/recommend_scheduler`` 一致（守护线程 + 幂等 + 测试跳过三件套），
但判定逻辑全部复用 ``modules.p1_sync_health``，本文件只负责「何时跑」：
  · 启动后先等 45s 让 Flask/数据源热身，之后每 ``interval_minutes`` 跑一轮；
  · 每轮 = 同步 + 体检 + 落档（``data/p1_sync_status.json``），幂等，重复跑不重写副本；
  · 单轮失败只留痕等下一轮，**循环永不中断**。

环境开关：
  · ``STOCKSIGNAL_ENABLE_P1_SYNC_SCHEDULER=0`` 关调度（默认开：只写 data/ 副本，幂等）；
  · ``STOCKSIGNAL_P1_SYNC_PUSH=1`` 失败才推送（默认关，按自然日去重）。
"""
from __future__ import annotations

import logging
import os
import threading
import time

from modules.p1_sync_health import (
    DEFAULT_INTERVAL_MINUTES,
    assess_p1_sync_health,
    run_sync_cycle,
    status_path,
)

logger = logging.getLogger(__name__)

_SCHEDULER_STARTED = False

__all__ = [
    "DEFAULT_INTERVAL_MINUTES",
    "assess_p1_sync_health",
    "run_sync_cycle",
    "status_path",
    "start_p1_sync_scheduler",
]


def start_p1_sync_scheduler(app, *, interval_minutes: int = DEFAULT_INTERVAL_MINUTES) -> None:
    """启动 P1 同步守护线程（测试 / 显式关闭环境自动跳过）。"""
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if os.environ.get("PYTEST_CURRENT_TEST") or app.config.get("TESTING"):
        logger.info("检测到测试环境，跳过 P1 同步调度器")
        return
    if os.environ.get("STOCKSIGNAL_ENABLE_P1_SYNC_SCHEDULER", "1") == "0":
        logger.info("STOCKSIGNAL_ENABLE_P1_SYNC_SCHEDULER=0，跳过 P1 同步调度器")
        return
    _SCHEDULER_STARTED = True

    def _loop() -> None:
        time.sleep(45)  # 让 Flask / 数据源热身，避免启动瞬间和刷新任务抢 IO
        while True:
            try:
                snap = run_sync_cycle(mode="scheduler", interval_minutes=interval_minutes)
                logger.info("[p1_sync_scheduler] 本轮 ok=%s status=%s written=%d errors=%d",
                            snap.get("ok"), (snap.get("health") or {}).get("status"),
                            len(snap.get("written") or []), len(snap.get("errors") or []))
            except Exception as e:  # noqa: BLE001 — 调度循环永不中断，但每轮失败必须留痕
                logger.warning("[p1_sync_scheduler] 本轮失败（下轮重试）: %s", e)
            time.sleep(max(5, int(interval_minutes)) * 60)

    t = threading.Thread(target=_loop, name="p1-sync-scheduler", daemon=True)
    t.start()
    logger.info("P1 同步调度器已启动（间隔 %d 分钟：同步 + 体检 + 状态快照）", interval_minutes)
