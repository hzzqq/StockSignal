"""
tests/test_cleaner_robust.py
===========================
回归：DataCleaner.full_pipeline 在真实脏数据下不得崩溃。

历史 bug：OHLCV 列混入非数字脏值（接口偶发坏值 / 手工 CSV 笔误，如 'x'、'n/a'、
空串、None）时，列保持 object dtype，calc_returns 的 pct_change 内部
`str / int` 除法抛 `TypeError: unsupported operand type(s) for /: 'str' and 'int'`，
导致该股票的 K线+技术分析整条管线崩溃。
修复：full_pipeline 与 calc_returns/calc_ma 先 `pd.to_numeric(errors='coerce')`，
脏值收敛为 NaN，管线照常产出。
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from modules.cleaner import DataCleaner


def _dirty_df():
    return pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04"],
        "open": [10, 11, 11, 12, "n/a"],
        "high": [10.5, 11.5, 11.5, 12.5, 13.0],
        "low": [9.5, 10.5, 10.5, 11.5, 12.0],
        "close": [10, "x", 11, 12, 13],
        "volume": [1000, 1100, 1100, 1200, 1300],
    })


def test_full_pipeline_dirty_no_crash():
    out = DataCleaner.full_pipeline(_dirty_df())
    assert len(out) == 5
    # 数值列被强制为 float64，脏值收敛为 NaN（此处 'x' 经 ffill 取前值、'n/a' 经 bfill 取后值）
    assert out["close"].dtype == np.float64
    assert out["return_1d"].notna().any()  # 至少部分收益率可计算
    # 不应抛异常即视为通过；额外断言产出了均线列
    for w in (5, 10, 20, 60):
        assert f"ma{w}" in out.columns


def test_full_pipeline_all_string_column_no_crash():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "open": ["a", "b", "c"],
        "high": ["x", "y", "z"],
        "low": ["p", "q", "r"],
        "close": ["1", "2", "3"],  # 纯数字字符串，应可被 coerce
        "volume": ["10", "20", "30"],
    })
    out = DataCleaner.full_pipeline(df)
    # 关键不变量：数值列被强制为数值类型（int/float），不再是 object，
    # 否则后续 pct_change/rolling 会在字符串上抛 TypeError。
    assert pd.api.types.is_numeric_dtype(out["close"])
    # return_1d 首行恒为 NaN（无前一日）；其后必须可计算
    assert out["return_1d"].iloc[1:].notna().all()


def test_calc_returns_dirty_column_no_crash():
    df = pd.DataFrame({"close": [10, "x", 12, 13]})
    out = DataCleaner.calc_returns(df)
    assert "return_1d" in out.columns
    assert out["return_1d"].dtype == np.float64


def test_calc_ma_dirty_column_no_crash():
    df = pd.DataFrame({"close": [10, "bad", 12, 13, 14]})
    out = DataCleaner.calc_ma(df, windows=[3])
    assert "ma3" in out.columns


def test_clean_input_still_works():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "open": [10, 11, 12],
        "high": [10.5, 11.5, 12.5],
        "low": [9.5, 10.5, 11.5],
        "close": [10, 11, 12],
        "volume": [1000, 1100, 1200],
    })
    out = DataCleaner.full_pipeline(df)
    assert out["return_1d"].iloc[-1] == pytest.approx(100.0 * (12 - 11) / 11)
    # 默认均线窗口 5/10/20/60 均已生成（3 行数据下值全为 NaN 但列存在）
    assert all(f"ma{w}" in out.columns for w in (5, 10, 20, 60))


def test_full_pipeline_none_and_empty_safe():
    """R82 回归：full_pipeline 对 None/空 DF/缺 close 列原样返回，不抛异常。

    此前 None 传进来 df.copy() AttributeError、空 DF calc_returns KeyError('close')，
    多数调用方靠 try/except 或前置守卫兜底；作为公共管线入口应自保
    （B_形态选股等曾依赖吞异常降级，属隐性契约）。
    """
    assert DataCleaner.full_pipeline(None) is None
    assert DataCleaner.full_pipeline(pd.DataFrame()).empty
    miss = DataCleaner.full_pipeline(pd.DataFrame({"date": ["2024-01-01"]}))
    assert "date" in miss.columns and "close" not in miss.columns
