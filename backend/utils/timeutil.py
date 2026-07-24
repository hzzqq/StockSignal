"""
时间工具
========
统一生成「naive UTC」时间，规避 ``datetime.utcnow()`` / ``datetime.utcfromtimestamp()``
在 Python 3.12+ 的弃用警告。

约定：
- 本项目的 SQLAlchemy ``DateTime`` 列按 **naive UTC** 存储与比较。
- 因此这些辅助函数返回 ``tzinfo=None`` 的 UTC 时间，与既有逻辑（及弃用前的
  ``datetime.utcnow()``）行为完全等价，可安全替换。
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回 naive UTC 时间（等价于已弃用的 ``datetime.utcnow()``）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_fromtimestamp(ts: float) -> datetime:
    """UTC 时区**感知**的时间戳转换（替代已弃用的 ``datetime.utcfromtimestamp``）。"""
    return datetime.fromtimestamp(ts, tz=timezone.utc)
