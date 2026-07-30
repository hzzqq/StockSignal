"""backtest 静态指标函数 + stock_screener 列归一 边界健壮性回归测试。

修复前：Backtester._rsi/_atr/_macd/_bollinger/_adx 与 stock_screener._norm_col 在
None 或空 DataFrame(缺列) 输入下会抛 AttributeError/TypeError/KeyError，回测取数失败
（空数据）时整段回测链路崩溃。
"""
import pandas as pd

import modules.backtest as BT
import modules.stock_screener as SS


def test_backtester_indicators_none_safe():
    empty = pd.Series(dtype=float)
    empty_df = pd.DataFrame()
    # 全部静态指标在 None / 空 DataFrame 下必须优雅返回空 Series / 三元组，不得崩溃
    assert len(BT.Backtester._rsi(None)) == 0
    assert len(BT.Backtester._rsi(empty)) == 0
    assert len(BT.Backtester._atr(None)) == 0
    assert len(BT.Backtester._atr(empty_df)) == 0
    macd = BT.Backtester._macd(None)
    assert all(len(x) == 0 for x in macd)
    boll = BT.Backtester._bollinger(None)
    assert all(len(x) == 0 for x in boll)
    assert len(BT.Backtester._adx(None)) == 0
    assert len(BT.Backtester._adx(empty_df)) == 0


def test_backtester_indicators_normal():
    df = pd.DataFrame({
        "close": [float(i) for i in range(1, 40)],
        "high": [float(i) + 1 for i in range(1, 40)],
        "low": [float(i) - 1 for i in range(1, 40)],
    })
    assert len(BT.Backtester._rsi(df["close"])) == 39
    assert len(BT.Backtester._atr(df)) == 39
    dif, dea, hist = BT.Backtester._macd(df)
    assert len(dif) == 39
    up, low, ma = BT.Backtester._bollinger(df)
    assert len(up) == 39
    assert len(BT.Backtester._adx(df)) == 39


def test_norm_col_none_safe():
    # _norm_col(None) 必须原样返回 None，不得抛 AttributeError
    assert SS._norm_col(None, {"a": ["b"]}) is None
    # 空 DataFrame 不崩
    out = SS._norm_col(pd.DataFrame(), {"a": ["b"]})
    assert isinstance(out, pd.DataFrame)
