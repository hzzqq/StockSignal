"""screener_indicators 技术指标计算库单元测试。

覆盖选股核心指标：MACD / RSI / Bollinger / 趋势 / 背离 / 量能 / 财务比率 / 成长率。
全部用合成数据，无外部 API 依赖，防止指标计算回归（直接影响选股结果正确性）。
"""
import numpy as np
import pandas as pd
import pytest

from modules.screener_indicators import (
    analyze_trend,
    calculate_bollinger_bands,
    calculate_financial_ratios,
    calculate_growth_rates,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    calculate_ema,
    check_volume_surge,
    detect_bottom_divergence,
    detect_top_divergence,
)


def _series(vals):
    return pd.Series(vals, dtype="float64")


# ───────────────────────── MACD ─────────────────────────
def test_macd_returns_three_series():
    close = _series(np.linspace(10, 20, 40) + np.random.RandomState(0).randn(40) * 0.1)
    macd, signal, hist = calculate_macd(close)
    assert macd is not None and signal is not None and hist is not None
    assert len(macd) == len(close)
    # 直方图 = 快线 - 慢线
    np.testing.assert_allclose((macd - signal).to_numpy(), hist.to_numpy(), atol=1e-9)


def test_macd_short_input_returns_none():
    close = _series([10, 11, 12])  # 长度 < slow(26)
    assert calculate_macd(close) == (None, None, None)


# ───────────────────────── RSI ─────────────────────────
def test_rsi_monotonic_up_near_100():
    close = _series(np.arange(1, 30, dtype="float64"))  # 全涨
    rsi = calculate_rsi(close)
    assert rsi is not None
    assert rsi.iloc[-1] > 99


def test_rsi_monotonic_down_near_0():
    close = _series(np.arange(30, 1, -1, dtype="float64"))  # 全跌
    rsi = calculate_rsi(close)
    assert rsi is not None
    assert rsi.iloc[-1] < 1


def test_rsi_short_input_returns_none():
    assert calculate_rsi(_series([1, 2])) is None


# ───────────────────────── Bollinger ─────────────────────────
def test_bollinger_band_order():
    close = _series(np.linspace(10, 20, 30))
    upper, middle, lower = calculate_bollinger_bands(close)
    assert upper is not None and middle is not None and lower is not None
    # 前 window-1 个点为 NaN（rolling 需要足够窗口），只比较有效部分
    valid = ~upper.isna()
    assert (upper[valid] >= middle[valid]).all()
    assert (middle[valid] >= lower[valid]).all()


# ───────────────────────── SMA / EMA ─────────────────────────
def test_sma_basic():
    s = _series([1, 2, 3, 4, 5])
    ma = calculate_sma(s, 3)
    assert ma is not None
    assert ma.iloc[-1] == pytest.approx(4.0)


def test_ema_basic():
    s = _series([1, 2, 3, 4, 5])
    ema = calculate_ema(s, 3)
    assert ema is not None
    assert ema.iloc[-1] > ema.iloc[0]


# ───────────────────────── 趋势分析 ─────────────────────────
def test_analyze_trend_uptrend():
    s = _series(np.linspace(1, 10, 20))
    slope, r2 = analyze_trend(s)
    assert slope is not None and r2 is not None
    assert slope > 0
    assert r2 > 0.99


def test_analyze_trend_short_input():
    assert analyze_trend(_series([1, 2]), min_points=10) == (None, None)


# ───────────────────────── 量能 ─────────────────────────
def test_volume_surge_detected():
    vol = _series([100] * 6 + [300])  # 最后一根放量
    surged, ratio = check_volume_surge(vol, weeks=5, threshold=1.5)
    assert surged is True
    assert ratio is not None and ratio > 1.5


def test_volume_surge_not_detected():
    vol = _series([100] * 7)
    surged, ratio = check_volume_surge(vol, weeks=5, threshold=1.5)
    assert surged is False


# ───────────────────────── 背离 ─────────────────────────
def test_bottom_divergence_false_on_short():
    close = _series([10, 9, 8])
    hist = _series([1, 0, -1])
    assert detect_bottom_divergence(close, hist) is False


def test_top_divergence_false_on_short():
    close = _series([8, 9, 10])
    hist = _series([-1, 0, 1])
    assert detect_top_divergence(close, hist) is False


# ───────────────────────── 财务比率 ─────────────────────────
def test_financial_ratios():
    df = pd.DataFrame([{
        "roe": 0.15, "roa": 0.08, "grossprofit_margin": 0.4,
        "netprofit_margin": 0.2, "debt_ratio": 0.5, "current_ratio": 1.5,
        "end_date": "2024-12-31", "ts_code": "600519",
    }])
    r = calculate_financial_ratios(df)
    assert r["roe"] == 0.15
    assert r["current_ratio"] == 1.5
    assert r["ts_code"] == "600519"


def test_financial_ratios_empty():
    assert calculate_financial_ratios(None) == {}
    assert calculate_financial_ratios(pd.DataFrame()) == {}


# ───────────────────────── 成长率 ─────────────────────────
def test_growth_rates():
    df = pd.DataFrame([
        {"total_revenue": 200, "netprofit": 40},
        {"total_revenue": 180, "netprofit": 30},
        {"total_revenue": 160, "netprofit": 20},
        {"total_revenue": 100, "netprofit": 10},
    ])
    g = calculate_growth_rates(df, periods=4)
    assert g["revenue_growth_yoy"] == pytest.approx(100.0)  # (200-100)/100*100
    assert g["profit_growth_yoy"] == pytest.approx(300.0)    # (40-10)/10*100


def test_growth_rates_short():
    assert calculate_growth_rates(pd.DataFrame([{"total_revenue": 1}])) == {}
