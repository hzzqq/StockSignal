"""回测模块「数据对错」契约断言（离线、确定性、独立重算对账，非安慰剂）。

锁住 #152 关心的回测数据正确性：
- MACD / Bollinger / ATR：与标准定义独立重算一致（公式被改坏会立即红）
- RSI：落在 [0,100] 且单调序列趋近极值（公式错乱必暴露）
- BacktestResult 指标：final_value/total_return/exposure/win_rate/profit_factor/
  annualized 的内部一致性（定义锁，防止指标公式回归）
全部不依赖网络、不运行回测引擎，纯数学契约。
"""
import math

import numpy as np
import pandas as pd

from modules.backtest import Backtester, BacktestResult


def _price_df(n=120, seed=11):
    rng = np.random.default_rng(seed)
    closes = 10 + np.cumsum(rng.normal(0, 0.3, n))
    highs = closes + np.abs(rng.normal(0, 0.2, n))
    lows = closes - np.abs(rng.normal(0, 0.2, n))
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({
        "date": dates, "open": closes, "high": highs,
        "low": lows, "close": closes,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    })


def test_macd_matches_canonical():
    """MACD 必须与标准定义一致：dif=EMA12-EMA26，dea=EMA9(dif)，hist=dif-dea。"""
    df = _price_df()
    dif, dea, hist = Backtester._macd(df)
    exp_dif = df["close"].ewm(span=12, adjust=False).mean() - df["close"].ewm(span=26, adjust=False).mean()
    exp_dea = exp_dif.ewm(span=9, adjust=False).mean()
    pd.testing.assert_series_equal(dif, exp_dif, check_names=False, rtol=1e-9)
    pd.testing.assert_series_equal(dea, exp_dea, check_names=False, rtol=1e-9)
    pd.testing.assert_series_equal(hist, (exp_dif - exp_dea), check_names=False, rtol=1e-9)


def test_bollinger_matches_canonical():
    """布林带必须与标准定义一致：ma=rolling mean，upper/lower=ma±2σ。"""
    df = _price_df()
    upper, lower, ma = Backtester._bollinger(df)
    exp_ma = df["close"].rolling(20).mean()
    exp_std = df["close"].rolling(20).std()
    pd.testing.assert_series_equal(ma, exp_ma, check_names=False, rtol=1e-9)
    pd.testing.assert_series_equal(upper, exp_ma + exp_std * 2, check_names=False, rtol=1e-9)
    pd.testing.assert_series_equal(lower, exp_ma - exp_std * 2, check_names=False, rtol=1e-9)


def test_rsi_bounds_and_extremes():
    """RSI 必须落在 [0,100]；单调上行→趋近 100，单调下行→趋近 0（公式错乱必暴露）。"""
    df = _price_df()
    rsi = Backtester._rsi(df["close"])
    valid = rsi.notna()
    assert (rsi[valid] >= 0).all() and (rsi[valid] <= 100).all(), "RSI 越界"
    up = pd.Series(np.linspace(10, 50, 60))
    assert Backtester._rsi(up).iloc[-1] > 99, "单调上行 RSI 应趋近 100"
    down = pd.Series(np.linspace(50, 10, 60))
    assert Backtester._rsi(down).iloc[-1] < 1, "单调下行 RSI 应趋近 0"


def test_atr_non_negative_and_matches_tr():
    """ATR 必须非负，且等于标准 TR（max(h-l,|h-c_prev|,|l-c_prev|)）的滚动均值。"""
    df = _price_df()
    atr = Backtester._atr(df)
    assert (atr.dropna() >= 0).all(), "ATR 不应为负"
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    exp = tr.rolling(14).mean()
    pd.testing.assert_series_equal(atr, exp, check_names=False, rtol=1e-9)


def _result(cum, asset, daily, pos, dd):
    return pd.DataFrame({
        "cumulative_return": cum, "total_asset": asset,
        "daily_return": daily, "position": pos, "drawdown": dd,
    })


def test_backtest_result_metric_consistency():
    """BacktestResult 指标内部一致性：读取列与定义一致，年化按几何年化公式。"""
    cum = [0.0, 5.0, 10.0, 8.0, 12.0]
    asset = [100000, 105000, 110000, 108000, 112000]
    daily = [0.0, 5.0, 4.76, -1.82, 3.70]
    pos = [0, 1, 1, 1, 0]
    dd = [0.0, 0.0, 0.0, -1.82, -1.82]
    df = _result(cum, asset, daily, pos, dd)
    r = BacktestResult("X", "ma_cross", df, 100000)
    assert r.final_value == 112000
    assert r.total_return == 12.0
    assert r.max_drawdown <= 0
    assert r.trade_count == 0
    assert r.exposure_pct == round(3 / 5 * 100, 2)
    exp_ann = round((1.12 ** (252 / 5) - 1) * 100, 2)
    assert r.annualized_return_pct == exp_ann


def test_backtest_result_win_profit_factor():
    """win_rate / profit_factor / avg_trade_return 必须由 trades 正确聚合。"""
    trades = [
        {"profit_pct": 5.0}, {"profit_pct": -2.0},
        {"profit_pct": 3.0}, {"profit_pct": -1.0},
    ]
    df = _result([0.0], [100000], [0.0], [0], [0.0])
    r = BacktestResult("X", "s", df, 100000, trades=trades)
    assert r.win_rate == 50.0
    assert r.profit_factor == round((5 + 3) / abs(-2 - 1), 2)
    assert r.avg_trade_return == round((5 - 2 + 3 - 1) / 4, 2)


def test_backtest_result_empty_safe():
    """空结果必须安全返回 0（不抛），保证前端无数据时不崩。"""
    r = BacktestResult("X", "s", pd.DataFrame(), 100000)
    assert r.final_value == 100000
    assert r.total_return == 0
    assert r.sharpe_ratio == 0
    assert r.win_rate == 0
