"""
tests/test_market_routes.py
===========================
对 backend.api.market_routes 中复权参数校验纯函数的离线单测（无需 Flask / DB）。

仅验证 _is_valid_adjust 的纯逻辑：仅允许 'qfq' / 'hfq' / '' / None，
其余一律非法，避免非法复权参数被透传到行情拉取层引发不可预期行为。
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.api.market_routes import _is_valid_adjust  # noqa: E402


def test_valid_qfq():
    assert _is_valid_adjust("qfq") is True


def test_valid_hfq():
    assert _is_valid_adjust("hfq") is True


def test_valid_empty_string():
    assert _is_valid_adjust("") is True


def test_valid_none_default():
    assert _is_valid_adjust(None) is True


def test_invalid_unknown():
    assert _is_valid_adjust("xyz") is False


def test_invalid_bfq():
    assert _is_valid_adjust("bfq") is False


def test_invalid_numeric_string():
    assert _is_valid_adjust("123") is False
