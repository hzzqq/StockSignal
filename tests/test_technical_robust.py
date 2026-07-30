"""技术面模块边界/健壮性回归测试。

覆盖探针发现的真实崩溃：`full_analysis` 在 DataFrame 缺 `open` 列时，
`detect_patterns` 直接下标访问 sub["open"] 抛 KeyError，拖垮整个技术面板块。
"""
import pandas as pd

import modules.technical as T


def test_full_analysis_missing_open_column_no_crash():
    # 仅含 close 列（上游取到缺列部分数据时）
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})
    out = T.full_analysis(df)
    assert isinstance(out, dict)
    for k in ("trend", "momentum", "volume", "patterns"):
        assert k in out
    # 缺列应安全降级，不抛异常
    assert isinstance(out["patterns"], list)  # detect_patterns 返回 []
    # 其它子分析即便部分失败也应是 dict（防御隔离）
    assert isinstance(out["trend"], dict)


def test_full_analysis_none_no_crash():
    out = T.full_analysis(None)
    assert isinstance(out, dict)
    assert "trend" in out


def test_full_analysis_empty_no_crash():
    out = T.full_analysis(pd.DataFrame())
    assert isinstance(out, dict)
    assert "patterns" in out


def test_full_analysis_single_row_missing_cols_no_crash():
    df = pd.DataFrame({"close": [10.0], "open": [9.0], "high": [11.0], "low": [8.0]})
    out = T.full_analysis(df)
    assert isinstance(out, dict)
    assert "trend" in out and "patterns" in out


def test_detect_patterns_missing_open_returns_empty():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0], "high": [1.0, 2.0, 3.0], "low": [1.0, 2.0, 3.0]})
    # 缺 open -> 无法识别形态，返回空列表而非 KeyError
    assert T.detect_patterns(df) == []


def test_full_analysis_normal_df_all_keys():
    import numpy as np
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=30),
        "open": np.linspace(10, 12, 30) + np.random.rand(30) * 0.1,
        "high": np.linspace(10.5, 12.5, 30) + np.random.rand(30) * 0.1,
        "low": np.linspace(9.5, 11.5, 30) + np.random.rand(30) * 0.1,
        "close": np.linspace(10, 12, 30),
        "volume": np.random.rand(30) * 1000 + 500,
        "return_1d": np.random.rand(30) * 0.02,
        "return_5d": np.random.rand(30) * 0.05,
        "return_20d": np.random.rand(30) * 0.1,
        "ma5": np.linspace(10, 12, 30),
        "ma10": np.linspace(10, 12, 30),
        "ma20": np.linspace(10, 12, 30),
        "ma60": np.linspace(10, 12, 30),
    })
    out = T.full_analysis(df)
    assert set(["trend", "momentum", "volume", "patterns"]).issubset(out.keys())
    assert "error" not in out["trend"]
