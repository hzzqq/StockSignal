"""modules/technical 新增 RSI 原语 + 趋势 NaN 守卫回归测试（无网依赖）。

覆盖：
- compute_rsi：全涨→100 / 全跌→0 / 持平→50 / 范围 0-100 / 数据不足→None / 缺列→None
- analyze_trend：close 为 NaN 时返回 error（修复 NaN 静默误判排列的隐性 bug）
"""
import math

import numpy as np
import pandas as pd

import modules.technical as T


def _df(closes, with_ma=True):
    n = len(closes)
    d = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1000] * n,
    })
    if with_ma:
        for w in (5, 10, 20, 60):
            d[f"ma{w}"] = pd.Series(closes).rolling(w).mean()
    return d


def test_rsi_all_up_is_100():
    df = _df(list(range(1, 20)))  # 19 点，全涨
    assert T.compute_rsi(df, 14) == 100.0


def test_rsi_all_down_is_0():
    df = _df(list(range(19, 0, -1)))  # 全跌
    assert T.compute_rsi(df, 14) == 0.0


def test_rsi_flat_is_50():
    df = _df([10] * 20)
    assert T.compute_rsi(df, 14) == 50.0


def test_rsi_in_range():
    # 涨跌交替，RSI 应落在 (0,100) 之间
    closes = [10, 11, 10, 12, 9, 13, 8, 14, 7, 15, 6, 16, 5, 17, 4, 18, 3, 19, 2, 20]
    rsi = T.compute_rsi(_df(closes), 14)
    assert rsi is not None
    assert 0 < rsi < 100


def test_rsi_insufficient_data():
    df = _df([1, 2, 3, 4, 5])  # < period+1
    assert T.compute_rsi(df, 14) is None


def test_rsi_missing_close_col():
    df = pd.DataFrame({"open": [1, 2], "high": [1, 2], "low": [1, 2]})
    assert T.compute_rsi(df, 14) is None


def test_rsi_rising_then_falling_lower():
    # 先涨后跌，RSI 应低于全涨情形
    up = list(range(1, 16))
    down = list(range(15, 5, -1))
    rsi = T.compute_rsi(_df(up + down), 14)
    assert rsi is not None and rsi < 100.0


def test_analyze_trend_nan_close_returns_error():
    df = _df([10.0] * 10)
    df.loc[df.index[-1], "close"] = np.nan  # 最新收盘为 NaN
    res = T.analyze_trend(df)
    assert "error" in res
    assert "NaN" in res["error"]


def test_analyze_trend_normal_no_error():
    df = _df(list(range(1, 30)))  # 多头排列
    res = T.analyze_trend(df)
    assert "error" not in res
    assert res["arrangement"] == "多头排列"
