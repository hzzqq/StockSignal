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

from modules.format_helpers import to_float, safe_div, format_amount, format_pct, safe_int, safe_float, extract_pct

from pathlib import Path  # noqa: E402


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


def test_safe_int():
    # None / 空串 / 非数字 → 默认 0
    assert safe_int(None) == 0
    assert safe_int("") == 0
    assert safe_int("abc") == 0
    # 正常转换
    assert safe_int("12") == 12
    assert safe_int(12.9) == 12
    # float('inf') 无法转 int → 默认 0
    assert safe_int(float("inf")) == 0
    # missing 入参（无 key）→ 默认 0
    assert safe_int(None, default=-1) == -1


def test_safe_float():
    assert safe_float(None) == 0.0
    assert safe_float("") == 0.0
    assert safe_float("abc") == 0.0
    assert safe_float("12.5") == 12.5
    assert safe_float(7) == 7.0
    # 按规范实现，float('inf') 经 float() 不抛异常，返回 inf（屏蔽 inf 由调用方决定）
    assert math.isinf(safe_float(float("inf")))
    # 缺省 default 生效
    assert safe_float(None, default=-1.0) == -1.0


def test_extract_pct_normal():
    assert extract_pct("贵州茅台(600519) 大涨 +3.45%") == 3.45
    assert extract_pct("某某 大跌 -5.2%") == -5.2
    # 取第一个 "%" 前的数字（真实异动标题通常只有一个）
    assert extract_pct("区间 +1.1% 收盘 +2.5%") == 1.1


def test_extract_pct_no_number_returns_default():
    # 社区帖 / 系统消息标题无涨跌幅 → 返回默认 -inf，便于排序沉底
    assert math.isinf(extract_pct("💬 无标题"))
    assert math.isinf(extract_pct("⚠️ 部分数据源不可用"))
    assert extract_pct(None) == float("-inf")
    # 含 "%" 但 "%" 前无数字（如 "涨跌幅 % 未知"）→ -inf
    assert math.isinf(extract_pct("涨跌幅 % 未知"))


def test_extract_pct_used_in_message_center_import():
    # 源码级防回退：消息中心排序/上色已改用 extract_pct，不再用脆弱的 split+float
    src = (Path(__file__).resolve().parents[1] / "pages" / "94_消息中心.py").read_text(encoding="utf-8")
    assert 'extract_pct(m["title"])' in src
    assert 'float(m["title"].split' not in src
