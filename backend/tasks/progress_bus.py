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
from typing import Callable, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)

# task_id -> reporter_fn(stage_key, message)
_REPORTERS: Dict[str, Callable[[str, str], None]] = {}
# task_id -> 最近一次 reporter 调用抛出的异常信息（可观测性，供运维/前端排查）
_LAST_ERROR: Dict[str, str] = {}
# task_id -> 该任务最近若干条进度事件（有界，防止内存无限增长；R1 新需求）
_EVENTS: Dict[str, List[Dict[str, str]]] = {}
# 每个任务最多保留的事件条数（有界内存，避免无上限增长）
MAX_EVENTS = 200
_LOCK = threading.Lock()


def register(task_id: str, fn: Callable[[str, str], None]) -> None:
    with _LOCK:
        _REPORTERS[task_id] = fn
        # 注册新 reporter 时清空旧错误，避免误导
        _LAST_ERROR.pop(task_id, None)
        # 重新注册时清空旧事件，避免孤儿数据
        _EVENTS.pop(task_id, None)


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
    """注销进度上报函数并遗忘其错误记录与事件缓存。"""
    with _LOCK:
        _REPORTERS.pop(task_id, None)
        _LAST_ERROR.pop(task_id, None)
        _EVENTS.pop(task_id, None)


def get_events(task_id: str) -> List[Dict[str, str]]:
    """返回该任务最近记录的进度事件列表（副本，避免调用方绕过锁修改）。

    对未知 task_id 返回空列表而非抛出 KeyError（R2）。
    """
    with _LOCK:
        return list(_EVENTS.get(task_id, []))


def get_status(task_id: str) -> Dict[str, object]:
    """返回一个安全的状态字典，对未知 task_id 也不会抛异常（R2/R5/R6 可观测性）。

    字段：
      - registered: 是否注册了 reporter（bool）
      - last_error: 最近一次 reporter 异常信息或 None（Optional[str]）
      - event_count: 已记录事件条数（int）
      - last_event: 最近一条事件或 None（Optional[dict]）
    """
    with _LOCK:
        events = _EVENTS.get(task_id, [])
        return {
            "registered": task_id in _REPORTERS,
            "last_error": _LAST_ERROR.get(task_id),
            "event_count": len(events),
            "last_event": events[-1] if events else None,
        }


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
    # 记录进度事件（有界：仅保留最近 MAX_EVENTS 条，防止无上限内存增长 —— R1）
    event = {"stage": stage, "message": message}
    with _LOCK:
        buf = _EVENTS.get(task_id)
        if buf is None:
            buf = []
            _EVENTS[task_id] = buf
        buf.append(event)
        if len(buf) > MAX_EVENTS:
            del buf[: len(buf) - MAX_EVENTS]
