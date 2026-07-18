"""
backend/tasks/progress_bus.py
-----------------------------
后台任务「实时进度」总线。

工作器在跑某个任务前，用 register(task_id, fn) 注册一个上报函数；
编排器内部（QuantAgent 的 progress_callback）随时调用 report(task_id, stage, message)，
总线把进度写入对应 Task 对象（progress / stage / logs），供前端轮询。

所有写入都加锁，且对磁盘持久化做节流（避免高频 I/O）。
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

# task_id -> reporter_fn(stage_key, message)
_REPORTERS: Dict[str, Callable[[str, str], None]] = {}
_LOCK = threading.Lock()


def register(task_id: str, fn: Callable[[str, str], None]) -> None:
    with _LOCK:
        _REPORTERS[task_id] = fn


def unregister(task_id: str) -> None:
    with _LOCK:
        _REPORTERS.pop(task_id, None)


def report(task_id: str, stage: str, message: str) -> None:
    """由编排器侧调用：把某个 stage 的进度/日志透传给对应 Task。"""
    fn = None
    with _LOCK:
        fn = _REPORTERS.get(task_id)
    if fn is not None:
        try:
            fn(stage, message)
        except Exception:  # noqa: BLE001
            pass
