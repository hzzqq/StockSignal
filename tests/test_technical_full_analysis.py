"""R23：technical.full_analysis 集成冒烟（无网）。

一键聚合函数 full_analysis(df) 应始终返回恰好 4 个键的 dict：
trend / momentum / volume / patterns。本测试锁定该聚合契约，并验证在
None / 空 df / 短 df（含必要列）等边界输入下都不崩溃，且短 df（不足形态
检测窗口）的 patterns 为空列表。有效 df 下确认子结果字段存在。
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from modules.technical import full_analysis


def _df(rows=30):
    idx = pd.date_range("2024-01-01", periods=rows, freq="D")
    closes = [100.0 + i for i in range(rows)]
    return pd.DataFrame({
        "date": idx,
        "open": [c - 1.0 for c in closes],
        "high": [c + 2.0 for c in closes],
        "low": [c - 2.0 for c in closes],
        "close": closes,
        "volume": [1000.0 + i * 10 for i in range(rows)],
    })


def test_full_analysis_returns_four_keys():
    res = full_analysis(_df(30))
    assert set(res.keys()) == {"trend", "momentum", "volume", "patterns"}


def test_full_analysis_patterns_is_list():
    res = full_analysis(_df(30))
    assert isinstance(res["patterns"], list)


def test_full_analysis_none_safe():
    res = full_analysis(None)
    assert set(res.keys()) == {"trend", "momentum", "volume", "patterns"}
    assert res["patterns"] == []


def test_full_analysis_empty_safe():
    res = full_analysis(pd.DataFrame())
    assert set(res.keys()) == {"trend", "momentum", "volume", "patterns"}


def test_full_analysis_short_df_patterns_empty():
    res = full_analysis(_df(3))
    assert set(res.keys()) == {"trend", "momentum", "volume", "patterns"}
    assert res["patterns"] == []


def test_full_analysis_valid_subresults_present():
    res = full_analysis(_df(30))
    assert "price" in res["trend"]
    assert "returns" in res["momentum"]
