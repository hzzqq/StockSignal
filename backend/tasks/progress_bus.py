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

import logging
import threading
from typing import Callable, Dict, Optional

_LOGGER = logging.getLogger(__name__)

# task_id -> reporter_fn(stage_key, message)
_REPORTERS: Dict[str, Callable[[str, str], None]] = {}
# task_id -> 最近一次 reporter 调用抛出的异常信息（可观测性，供运维/前端排查）
_LAST_ERROR: Dict[str, str] = {}
_LOCK = threading.Lock()


def register(task_id: str, fn: Callable[[str, str], None]) -> None:
    with _LOCK:
        _REPORTERS[task_id] = fn
        # 注册新 reporter 时清空旧错误，避免误导
        _LAST_ERROR.pop(task_id, None)


def unregister(task_id: str) -> None:
    with _LOCK:
        _REPORTERS.pop(task_id, None)


def is_registered(task_id: str) -> bool:
    """该 task_id 当前是否注册了进度上报函数。"""
    with _LOCK:
        return task_id in _REPORTERS


def last_error(task_id: str) -> Optional[str]:
    """返回该 task_id 最近一次 reporter 调用抛出的异常信息；无则 None。

    用于可观测性：reporter 内部出错不应静默吞掉，调用方/前端可据此判断
    进度推送是否健康。
    """
    with _LOCK:
        return _LAST_ERROR.get(task_id)


def clear(task_id: str) -> None:
    """注销进度上报函数并遗忘其错误记录。"""
    with _LOCK:
        _REPORTERS.pop(task_id, None)
        _LAST_ERROR.pop(task_id, None)


def report(task_id: str, stage: str, message: str) -> None:
    """由编排器侧调用：把某个 stage 的进度/日志透传给对应 Task。

    隐性缺陷修复：旧实现用 ``except Exception: pass`` 静默吞掉 reporter 异常，
    进度总线对外永远「正常」，定位进度丢失/卡住时无从下手。现改为记录日志并存下
    最近一次错误（``last_error``），既不打断编排器主流程，又保留可观测性。
    """
    fn = None
    with _LOCK:
        fn = _REPORTERS.get(task_id)
    if fn is not None:
        try:
            fn(stage, message)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            with _LOCK:
                _LAST_ERROR[task_id] = err
            _LOGGER.warning("progress_bus reporter for %s failed at stage=%s: %s", task_id, stage, err)
