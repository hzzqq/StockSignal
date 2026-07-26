"""
tests/test_stock_routes.py
==========================
对 backend.api.stock_routes 中计数辅助函数的纯离线测试（无需 Flask / DB）。

仅验证 _count_by_key 的纯逻辑：安全处理 None / 空 key，避免产生 {None: n} 这类
不可 JSON 序列化的字典键。
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.api.stock_routes import _count_by_key  # noqa: E402


def test_count_normal_keys():
    """正常 key 原样保留。"""
    assert _count_by_key([("a", 1), ("b", 2)]) == {"a": 1, "b": 2}


def test_count_none_key_mapped_to_default():
    """None key 落为默认 'unknown'。"""
    assert _count_by_key([(None, 1), ("b", 2)]) == {"unknown": 1, "b": 2}


def test_count_empty_rows():
    """空序列返回空字典。"""
    assert _count_by_key([]) == {}
