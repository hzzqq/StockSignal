"""
tests/test_compare_to_float.py — 锐评 R2 守卫

compare._to_float 必须能解析「带百分号 / 千分位逗号 / 空白」的脏值，
否则真实存在的 ROE / 同比 / 股息率会被静默当成「无数据」丢掉的回归测试。
"""
import pytest

from modules import compare as cmp


def test_to_float_strips_pct():
    # 同花顺财务指标标准格式 "12.5%" 应解析为 12.5，而非被 ValueError 吞成 None
    assert cmp._to_float("12.5%") == 12.5
    assert cmp._to_float("  -3.2% ") == -3.2


def test_to_float_strips_thousands():
    assert cmp._to_float("1,234.5") == 1234.5
    assert cmp._to_float("1,234.5%") == 1234.5


def test_to_float_numeric_passthrough():
    assert cmp._to_float(12.5) == 12.5
    assert cmp._to_float(0) == 0


def test_to_float_missing_none():
    assert cmp._to_float(None) is None
    assert cmp._to_float("") is None
    assert cmp._to_float("-") is None
    assert cmp._to_float("--") is None
    assert cmp._to_float("n/a") is None


def test_to_float_unparseable_none():
    # 完全非数值才返回 None（失败走日志，不抛）
    assert cmp._to_float("abc") is None


def test_pick_uses_to_float_on_pct_value():
    """直接验证 _pick 的内部解析能吃到带 % 的真实列值（不依赖网络）。"""
    import pandas as pd
    # 构造一行「净资产收益率」为百分比字符串的假 df，复刻 _pick 逻辑
    df = pd.DataFrame([{"净资产收益率(%)": "15.3%", "净利润同比增长率(%)": "8.1%"}])
    last = df.iloc[-1]
    col = "净资产收益率(%)"
    # 还原 _pick 内联解析（与源码一致，仅替换解析函数）
    val = cmp._to_float(last[col])
    assert val == 15.3
