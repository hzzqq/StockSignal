"""
backend/utils/params.py
-----------------------
共享的安全查询参数解析工具。

替代 `int(request.args.get(...))` 这类会在传入非数字时直接抛 500 的写法，
对缺失 / 非数字 / 越界统一做兜底。保持依赖极简，仅用到 Flask 的 `request`。
"""
from __future__ import annotations

from flask import request


def parse_int_param(name, default=0, lo=None, hi=None, source=None):
    """
    从查询参数（或任意 dict-like 的 `source`）中安全解析一个整数。

    - 键缺失 -> 返回 default
    - 非数字（TypeError / ValueError）-> 返回 default
    - 低于 lo -> 钳制为 lo
    - 高于 hi -> 钳制为 hi
    """
    if source is None:
        source = request.args
    try:
        v = int(source.get(name, default))
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v
