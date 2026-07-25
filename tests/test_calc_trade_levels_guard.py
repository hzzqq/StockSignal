"""R17：统一重复 _calc_trade_levels（单一来源）+ 缺列 KeyError 防护。

- modules.analysis_engine._calc_trade_levels 现委托给 stock_analysis_helpers（单一来源）；
- 两者对「正常 df」与「缺列 df」行为必须完全一致；
- 缺 high/low/close 列时退化为 ATR 近似，不再抛 KeyError。
"""
import pandas as pd

from modules.analysis_engine import _calc_trade_levels as ae_ctl
from modules.stock_analysis_helpers import _calc_trade_levels as sh_ctl


def _normal_df():
    n = 20
    closes = [100.0 + i for i in range(n)]
    return pd.DataFrame({
        "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes],
        "close": closes,
    })


def test_unified_behavior_normal_df():
    df = _normal_df()
    a = ae_ctl(100.0, df, 95.0, 115.0)
    b = sh_ctl(100.0, df, 95.0, 115.0)
    assert a == b
    # 4 元组且均为有限值
    assert len(a) == 4
    assert all(isinstance(x, float) for x in a)


def test_missing_columns_no_keyerror_and_unified():
    # 缺 high/low/close 的精简行情
    df = pd.DataFrame({"open": [1.0], "volume": [1.0]})
    a = ae_ctl(100.0, df, 95.0, 110.0)
    b = sh_ctl(100.0, df, 95.0, 110.0)
    assert a == b
    assert len(a) == 4
    assert all(isinstance(x, float) for x in a)
    # 止损不应高于入场（基本合理区间）
    entry, target, stop, atr = a
    assert stop <= entry <= target


def test_none_df_no_keyerror():
    a = ae_ctl(100.0, None, 95.0, 110.0)
    b = sh_ctl(100.0, None, 95.0, 110.0)
    assert a == b
    assert len(a) == 4
