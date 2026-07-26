"""
纯逻辑单元测试（无网络、无数据库）。

覆盖 modules/technical.rsi_series 在退化输入下的健壮性：
  - 正常输入 -> 有限数值、落在 [0,100]
  - 空 DataFrame -> 空 Series（不抛异常）
  - 全 NaN 序列 -> 空 Series（不抛异常、不爆 NaN）
  - 极短序列（< period）-> 空 Series（不抛异常）
  - 单调涨/跌 -> 100 / 0
同时验证既有 compute_rsi / compute_atr 在空输入下同样安全。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.technical import compute_atr, compute_rsi, rsi_series


# ------------------------------------------------------------
# rsi_series: 正常输入
# ------------------------------------------------------------
def test_rsi_series_normal_is_finite_and_bounded():
    close = pd.Series([10, 11, 12, 11, 13, 14, 13, 15, 16, 17,
                       16, 18, 19, 18, 20, 21, 20, 22, 23, 24], dtype="float64")
    df = pd.DataFrame({"close": close})
    out = rsi_series(df, period=14)
    # 前 period 根为 NaN（SMA 初始化），之后为有限值
    assert isinstance(out, pd.Series)
    valid = out.dropna()
    assert len(valid) > 0
    assert valid.notna().all()
    assert (valid >= 0.0).all() and (valid <= 100.0).all()


def test_rsi_series_monotonic_up_is_100():
    close = pd.Series(np.arange(1, 40, dtype="float64"))  # 一直涨
    df = pd.DataFrame({"close": close})
    out = rsi_series(df, period=14)
    assert (out.dropna() == 100.0).all()


def test_rsi_series_monotonic_down_is_0():
    close = pd.Series(np.arange(40, 1, -1, dtype="float64"))  # 一直跌
    df = pd.DataFrame({"close": close})
    out = rsi_series(df, period=14)
    assert (out.dropna() == 0.0).all()


# ------------------------------------------------------------
# rsi_series: 退化输入（必须安全，不抛异常、不爆 NaN 序列）
# ------------------------------------------------------------
def test_rsi_series_empty_dataframe_returns_empty_series():
    out = rsi_series(pd.DataFrame(), period=14)
    assert isinstance(out, pd.Series)
    assert out.empty


def test_rsi_series_none_returns_empty_series():
    out = rsi_series(None, period=14)  # type: ignore[arg-type]
    assert isinstance(out, pd.Series)
    assert out.empty


def test_rsi_series_all_nan_returns_empty_series():
    df = pd.DataFrame({"close": [np.nan, np.nan, np.nan]})
    out = rsi_series(df, period=14)
    assert isinstance(out, pd.Series)
    assert out.empty


def test_rsi_series_all_nan_long_returns_empty_series():
    df = pd.DataFrame({"close": [np.nan] * 50})
    out = rsi_series(df, period=14)
    assert isinstance(out, pd.Series)
    assert out.empty


def test_rsi_series_too_short_returns_empty_series():
    # 长度 < period + 1，无法计算任何有效 RSI
    df = pd.DataFrame({"close": [10.0, 11.0, 12.0, 11.0, 13.0]})
    out = rsi_series(df, period=14)
    assert isinstance(out, pd.Series)
    assert out.empty


def test_rsi_series_short_but_valid_partial_not_nan_explosion():
    # 刚够 period+1，确认输出里没有任何非预期的 NaN 爆炸：
    # 只有一个有效值（首根窗口后），且为有限值
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0,
                       17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0])
    df = pd.DataFrame({"close": close})
    out = rsi_series(df, period=14)
    assert not out.empty
    assert out.dropna().notna().all()
    assert (out.dropna() >= 0.0).all() and (out.dropna() <= 100.0).all()


def test_rsi_series_missing_close_column_returns_empty_series():
    df = pd.DataFrame({"open": [1, 2, 3]})
    out = rsi_series(df, period=14)
    assert isinstance(out, pd.Series)
    assert out.empty


def test_rsi_series_bad_period_returns_empty_series():
    df = pd.DataFrame({"close": np.arange(1, 40, dtype="float64")})
    out = rsi_series(df, period=0)
    assert isinstance(out, pd.Series)
    assert out.empty


def test_rsi_series_non_dataframe_input_returns_empty_series():
    out = rsi_series("not a frame", period=14)  # type: ignore[arg-type]
    assert isinstance(out, pd.Series)
    assert out.empty


# ------------------------------------------------------------
# 既有标量指标在退化输入下同样安全（不抛异常）
# ------------------------------------------------------------
def test_compute_rsi_empty_returns_none():
    assert compute_rsi(pd.DataFrame(), period=14) is None
    assert compute_rsi(None, period=14) is None  # type: ignore[arg-type]


def test_compute_rsi_all_nan_returns_none():
    df = pd.DataFrame({"close": [np.nan, np.nan, np.nan]})
    assert compute_rsi(df, period=14) is None


def test_compute_atr_empty_returns_none():
    assert compute_atr(pd.DataFrame(), period=14) is None
    assert compute_atr(None, period=14) is None  # type: ignore[arg-type]


def test_compute_atr_missing_columns_returns_none():
    df = pd.DataFrame({"close": [1.0, 2.0]})
    assert compute_atr(df, period=14) is None


@pytest.mark.parametrize(
    "fn",
    [compute_rsi, compute_atr],
)
def test_scalar_indicators_never_raise_on_degenerate(fn):
    # 任意退化输入都不应抛出
    fn(pd.DataFrame(), 14)
    fn(pd.DataFrame({"close": [np.nan] * 5}), 14)
    fn(pd.DataFrame({"close": [1.0, 2.0]}), 14)
