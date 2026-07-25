"""R16：modules.technical 新增 compute_atr + 修复 NaN 均线排列误判。

- compute_atr 返回正确 ATR（数据不足/列缺失/NaN 返回 None）；
- analyze_trend 在 ma60 为 NaN 时仍应正确判定多头/空头排列。
"""
import numpy as np
import pandas as pd

from modules.technical import compute_atr, analyze_trend


def _make_ohlc(n=20, start=100.0, step=1.0):
    closes = [start + step * i for i in range(n)]
    return pd.DataFrame({
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
        "close": closes,
    })


def test_compute_atr_known_value():
    df = _make_ohlc(20)
    # 每根 K 线 TR 恒为 2（见 _make_ohlc），ATR(14) 必为 2.0
    atr = compute_atr(df, period=14)
    assert atr is not None
    assert abs(atr - 2.0) < 1e-9


def test_compute_atr_insufficient_data():
    df = _make_ohlc(5)
    assert compute_atr(df, period=14) is None


def test_compute_atr_missing_columns():
    df = pd.DataFrame({"close": [1, 2, 3]})
    assert compute_atr(df) is None


def test_compute_atr_empty():
    assert compute_atr(pd.DataFrame()) is None


def test_analyze_trend_ignores_nan_ma():
    # ma5>ma10>ma20 且 close>ma5，但 ma60 为 NaN：
    # 修复前 nan 会破坏排列判断（恒为"纠缠"）；修复后应为多头排列。
    row = {
        "close": 120.0,
        "ma5": 118.0,
        "ma10": 115.0,
        "ma20": 110.0,
        "ma60": np.nan,
    }
    df = pd.DataFrame([row])
    res = analyze_trend(df)
    assert res.get("arrangement") == "多头排列"
    assert res.get("trend_score") == 85


def test_analyze_trend_bearish_with_nan_ma():
    row = {
        "close": 90.0,
        "ma5": 95.0,
        "ma10": 98.0,
        "ma20": 102.0,
        "ma60": np.nan,
    }
    df = pd.DataFrame([row])
    res = analyze_trend(df)
    assert res.get("arrangement") == "空头排列"
    assert res.get("trend_score") == 15
