"""
backend/utils/ratelimit.py
---------------------------
进程内内存滑动窗口限流。

设计要点：
- 仅用于 /api/auth/login、/api/auth/register 防爆破，纯后端、无外部依赖。
- 计数维度 key = f"{ip}|{username}"，按用户名分别计数，不同用户互不叠加。
- 窗口默认 60s，单 key 上限默认 5 次（可经 config / 环境变量调整）。
- 提供测试接缝：RATE_LIMIT_ENABLED 开关、reset_rate_limit()、get_hit_count()，
  便于集成测试规避跨用例干扰（不会误伤 test_security.py 的 12 个断言）。

注意：进程内内存方案在多 worker / 多进程部署下不共享计数；生产如需全局限流
应换 Redis 等共享存储，本模块接口（is_allowed/reset/get_hit_count）保持不变即可替换实现。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Dict, Deque

from flask import current_app

# 进程内存储：key -> 时间戳双端队列（单调递增时钟）
_store: Dict[str, Deque[float]] = {}
# 多用户并发登录时，多个线程会同时读写 _store；用锁保护避免竞态（丢计数 / RuntimeError）
_lock = threading.Lock()


def _enabled() -> bool:
    return bool(current_app.config.get("RATE_LIMIT_ENABLED", True))


def _max() -> int:
    try:
        return int(current_app.config.get("RATE_LIMIT_MAX", 5))
    except (TypeError, ValueError):
        return 5


def _window() -> float:
    try:
        return float(current_app.config.get("RATE_LIMIT_WINDOW", 60))
    except (TypeError, ValueError):
        return 60.0


def make_key(ip: str, username: str) -> str:
    """构造计数 key；username 已去空格处理。"""
    return f"{ip}|{username}"


def is_allowed(key: str) -> bool:
    """
    滑动窗口判断是否放行。返回 True 表示允许本次请求（并记一次）。
    开关关闭时恒放行（测试/本地调试用）。
    """
    if not _enabled():
        return True

    now = time.monotonic()
    win = _window()
    with _lock:
        dq = _store.get(key)
        if dq is None:
            dq = deque()
            _store[key] = dq

        # 清掉窗口外的时间戳
        while dq and now - dq[0] > win:
            dq.popleft()

        if len(dq) >= _max():
            return False

        dq.append(now)
        return True


def reset_rate_limit() -> None:
    """清空全部计数（测试接缝）。"""
    with _lock:
        _store.clear()


def get_hit_count(key: str) -> int:
    """返回当前窗口内某 key 的命中次数（测试接缝）。"""
    now = time.monotonic()
    win = _window()
    with _lock:
        dq = _store.get(key)
        if not dq:
            return 0
        return sum(1 for t in dq if now - t <= win)
