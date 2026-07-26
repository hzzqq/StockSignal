"""
tests/test_cleaner.py
======================
DataCleaner 纯计算逻辑测试 + 可变默认参数回归守护。

守护点：calc_returns / calc_ma 的 periods / windows 默认参数必须是 None
（每次调用新建列表），而非模块级共享可变列表——否则一旦某处 mutate 默认，
所有后续调用都会被污染（经典 Python 可变默认参数陷阱）。
"""
import inspect

import pandas as pd
import pytest

import modules.cleaner as cleaner_mod
from modules.cleaner import DataCleaner


def _sample_df():
    return pd.DataFrame({
        "close": [10.0, 10.5, 11.0, 10.8, 11.2, 11.5, 11.3, 11.9, 12.1, 12.0],
        "vol": [100, 110, 95, 120, 130, 125, 140, 135, 150, 160],
    })


def test_calc_returns_columns():
    df = DataCleaner.calc_returns(_sample_df())
    for p in (1, 5, 20):
        assert f"return_{p}d" in df.columns


def test_calc_returns_first_is_nan():
    df = DataCleaner.calc_returns(_sample_df(), periods=[1])
    assert pd.isna(df["return_1d"].iloc[0])
    assert not pd.isna(df["return_1d"].iloc[1])


def test_calc_returns_custom_periods():
    df = DataCleaner.calc_returns(_sample_df(), periods=[2, 3])
    assert "return_2d" in df.columns
    assert "return_3d" in df.columns
    assert "return_1d" not in df.columns


def test_calc_ma_columns_and_nan_prefix():
    df = DataCleaner.calc_ma(_sample_df())
    for w in (5, 10, 20, 60):
        assert f"ma{w}" in df.columns
    # 窗口未满时应为 NaN
    assert pd.isna(df["ma5"].iloc[3])
    assert not pd.isna(df["ma5"].iloc[4])


def test_calc_ma_custom_windows():
    df = DataCleaner.calc_ma(_sample_df(), windows=[3])
    assert "ma3" in df.columns
    assert "ma5" not in df.columns


def test_default_periods_is_none_not_shared_list():
    """回归守护：默认参数必须是 None，确保每次调用拿到独立列表。"""
    sig = inspect.signature(DataCleaner.calc_returns)
    assert sig.parameters["periods"].default is None
    sig2 = inspect.signature(DataCleaner.calc_ma)
    assert sig2.parameters["windows"].default is None


def test_default_not_mutated_across_calls():
    """即使传入的列表被调用方后续修改，默认行为不受影响（独立副本）。"""
    custom = [1, 2]
    df = _sample_df()
    DataCleaner.calc_returns(df, periods=custom)
    custom.append(999)  # 调用方 mutate 传入列表
    df2 = DataCleaner.calc_returns(_sample_df())  # 用默认
    # 默认仍只产出 [1,5,20]，不受 custom 影响
    for p in (1, 5, 20):
        assert f"return_{p}d" in df2.columns


def test_full_pipeline_runs():
    df = DataCleaner.full_pipeline(_sample_df())
    for col in ("ma5", "ma20", "return_1d"):
        assert col in df.columns
