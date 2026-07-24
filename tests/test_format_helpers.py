"""
tests/test_format_helpers.py
===========================
校验 modules.format_helpers 的安全格式化与运算：
- 屏蔽 NaN / inf / None / 空串；
- 除零安全；
- 金额/百分比格式化与历史行为一致。
"""
from __future__ import annotations

import math

from modules.format_helpers import to_float, safe_div, format_amount, format_pct


def test_to_float_valid():
    assert to_float("1.5") == 1.5
    assert to_float(100) == 100.0
    assert to_float("1e3") == 1000.0
    assert to_float(" 2 ") == 2.0


def test_to_float_invalid_returns_default():
    assert to_float(None) is None
    assert to_float("") is None
    assert to_float("   ") is None
    assert to_float("abc") is None
    assert to_float(float("nan")) is None
    assert to_float(float("inf")) is None
    assert to_float(None, default=-1.0) == -1.0


def test_safe_div():
    assert safe_div(10, 2) == 5.0
    assert safe_div("6", "3") == 2.0
    # 除零 / None / NaN / inf → 默认 0.0
    assert safe_div(10, 0) == 0.0
    assert safe_div(None, 2) == 0.0
    assert safe_div(10, None) == 0.0
    assert safe_div(0, 0) == 0.0
    assert safe_div(float("inf"), 1) == 0.0
    assert safe_div(10, 0, default=-1.0) == -1.0


def test_format_amount():
    assert format_amount(1e8) == "1.00亿"
    assert format_amount(1.5e8) == "1.50亿"
    assert format_amount(1e4) == "1.0万"
    assert format_amount(2.5e4) == "2.5万"
    assert format_amount(1234) == "1234"
    assert format_amount(0) == "0"
    # 非法值一律 “—”
    assert format_amount(None) == "—"
    assert format_amount("") == "—"
    assert format_amount(float("nan")) == "—"
    assert format_amount(float("inf")) == "—"
    assert format_amount("abc") == "—"


def test_format_pct():
    # 输入为「百分点」数值（与资金流 main_net_pct 等同口径）
    assert format_pct(12.34) == "12.34%"
    assert format_pct(1) == "1.00%"
    assert format_pct(None) == "—"
    assert format_pct(float("nan")) == "—"
    assert format_pct(0.5, dp=1) == "0.5%"


def test_fundflow_wan_yi_delegates():
    """回归：fundflow._to_wan_yi 委托给 format_amount，屏蔽 NaN/inf/None。"""
    from modules.fundflow import _to_wan_yi

    assert _to_wan_yi(1e8) == "1.00亿"
    assert _to_wan_yi(float("nan")) == "—"
    assert _to_wan_yi(None) == "—"
    assert _to_wan_yi(float("inf")) == "—"
