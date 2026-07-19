"""R12：modules/analysis_engine 研判映射测试。

R8 把配色集中到 modules.colors；analysis_engine._verdict_color 是 stock_analysis_helpers
中同名函数的复本，二者必须保持「研判阈值 + 配色」完全一致，否则会出现「个股分析页」与
「深度分析引擎」研判结论/配色不一致。本测试锁定该不变量，防配色重构回归。
"""

import pandas as pd
import pytest

from modules.colors import RED, GREEN, AMBER
from modules.analysis_engine import _verdict_color, _calc_trade_levels
from modules.stock_analysis_helpers import _verdict_color as _sh_verdict_color


@pytest.mark.parametrize("score,exp_text,exp_color,exp_cls", [
    (80, "看多", RED, "win"),
    (70, "看多", RED, "win"),     # 边界含等
    (69, "持有", AMBER, "mid"),
    (55, "持有", AMBER, "mid"),
    (41, "持有", AMBER, "mid"),
    (40, "看空", GREEN, "weak"),  # 边界含等
    (39, "看空", GREEN, "weak"),
    (0, "看空", GREEN, "weak"),
])
def test_verdict_color_thresholds(score, exp_text, exp_color, exp_cls):
    text, color, cls = _verdict_color(score)
    assert text == exp_text
    assert color is exp_color        # 必须是 modules.colors 的同一对象（非本地重定义）
    assert cls == exp_cls


def test_verdict_color_matches_helpers_duplicate():
    """analysis_engine 与 stock_analysis_helpers 的同名函数必须逐输入一致。"""
    for s in [-10, 0, 30, 40, 41, 55, 69, 70, 85, 100, 999]:
        assert _verdict_color(s) == _sh_verdict_color(s), f"评分 {s} 两处研判不一致"


def test_calc_trade_levels_matches_helpers():
    """两个模块的 _calc_trade_levels 行为必须一致（同源逻辑）。"""
    from modules.stock_analysis_helpers import _calc_trade_levels as _sh_ctl
    df = pd.DataFrame({"high": [100.0] * 20, "low": [100.0] * 20, "close": [100.0] * 20})
    a = _calc_trade_levels(100.0, df, 95.0, 115.0)
    b = _sh_ctl(100.0, df, 95.0, 115.0)
    assert a == b


def test_calc_trade_levels_guard_against_negative_price():
    """非正现价应安全返回 (当前价, 压力, 支撑, 0.0) 而不抛异常。"""
    res = _calc_trade_levels(0.0, pd.DataFrame({"high": [1.0], "low": [1.0], "close": [1.0]}), 0.5, 2.0)
    assert res == (0.0, 2.0, 0.5, 0.0)
