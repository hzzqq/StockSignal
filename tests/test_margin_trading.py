"""margin_trading.py 单元自测：纯逻辑层（不触网）。

覆盖：
- safe_yuan_to_yi / _to_yi：NaN/inf/None/''/非法 -> 0.0（有限兜底，杜绝图表 "nan"，防 None 算术）
- _delta_pct：环比百分比（除零 / NaN / None 防护，守卫分支返回 0.0）
- _safe_delta_yi：None/NaN 不再崩溃，返回 0.0
- _parse_date：Timestamp / datetime / NA / 有效字符串 / 非法字符串 -> None（不抛 ValueError）
- _cached(skip_empty)：瞬时失败不被缓存
- get_latest_margin_summary：合成 DataFrame 验证绝对值 + 百分比 + NaN 兜底（有限值）
- plot_margin_trend(空 df)：无网返回空图
"""
import math
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import modules.margin_trading as mt


def test_safe_yuan_to_yi_basics():
    assert mt.safe_yuan_to_yi(1e8) == 1.0
    assert mt.safe_yuan_to_yi(5e8) == 5.0
    assert mt.safe_yuan_to_yi("1e8") == 1.0
    assert mt.safe_yuan_to_yi("-2e8") == -2.0


def test_safe_yuan_to_yi_guards():
    # 需求：None / NaN / inf / '' / 非法 -> 0.0（不崩溃）
    assert mt.safe_yuan_to_yi(None) == 0.0
    assert mt.safe_yuan_to_yi(float("nan")) == 0.0
    assert mt.safe_yuan_to_yi(float("inf")) == 0.0
    assert mt.safe_yuan_to_yi(float("-inf")) == 0.0
    assert mt.safe_yuan_to_yi("") == 0.0
    assert mt.safe_yuan_to_yi("abc") == 0.0
    assert mt.safe_yuan_to_yi(np.nan) == 0.0


def test_to_yi_delegates_to_safe():
    assert mt._to_yi(np.nan) == 0.0
    assert mt._to_yi(1e8) == 1.0
    assert mt._to_yi("bad") == 0.0
    assert mt._to_yi(None) == 0.0


def test_delta_pct():
    # 合法输入行为不变
    assert mt._delta_pct(110, 100) == 10.0
    assert mt._delta_pct(90, 100) == -10.0
    assert mt._delta_pct(100, 100) == 0.0
    # 守卫分支：除零 / NaN / None -> 0.0（不抛异常）
    assert mt._delta_pct(100, 0) == 0.0
    assert mt._delta_pct(np.nan, 100) == 0.0
    assert mt._delta_pct(100, np.nan) == 0.0
    assert mt._delta_pct(None, None) == 0.0
    # 显式需求用例
    assert mt._delta_pct(100, 0) == 0.0
    assert mt._delta_pct(110, 100) == 10.0


def test_safe_delta_yi_none_safe():
    # 之前：None - 100.0 触发 TypeError；现在返回有限兜底值，不崩溃
    assert mt._safe_delta_yi(np.nan, 100e8) == -100.0
    assert mt._safe_delta_yi(110e8, 100e8) == 10.0
    assert mt._safe_delta_yi(100e8, np.nan) == 100.0
    assert mt._safe_delta_yi(None, None) == 0.0


def test_parse_date():
    assert mt._parse_date(pd.Timestamp("2024-01-02")) == "2024-01-02"
    assert mt._parse_date(__import__("datetime").datetime(2024, 1, 2)) == "2024-01-02"
    assert mt._parse_date(pd.NaT) is None
    assert mt._parse_date(None) is None
    # 有效字符串 -> 原样 YYYY-MM-DD
    assert mt._parse_date("2024-01-01") == "2024-01-01"
    assert mt._parse_date("2024-03-04") == "2024-03-04"
    # 非法字符串 -> None（不抛 ValueError）
    assert mt._parse_date("garbage") is None


def test_cached_skip_empty_not_cached():
    # 第一次返回空（模拟网络失败），skip_empty 不应缓存
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            return pd.DataFrame()
        return pd.DataFrame({"日期": ["2024-01-01"]})

    key = "_test_skip_empty"
    mt._MARGIN_CACHE.pop(key, None)
    first = mt._cached(600, key, fn, skip_empty=True)
    assert first.empty
    # 第二次应绕过缓存，拿到非空结果
    second = mt._cached(600, key, fn, skip_empty=True)
    assert not second.empty
    assert calls["n"] == 2


def test_cached_normal_caches():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return pd.DataFrame({"x": [1]})

    key = "_test_normal_cache"
    mt._MARGIN_CACHE.pop(key, None)
    mt._cached(600, key, fn)
    mt._cached(600, key, fn)
    assert calls["n"] == 1


def test_get_latest_margin_summary_pct(monkeypatch):
    df = pd.DataFrame({
        "日期": ["2024-01-01", "2024-01-02"],
        "total_rzmr": [100e8, 110e8],     # +10%
        "total_rzye": [1000e8, 900e8],    # -10%
        "sh_rzmr": [60e8, 66e8],
        "sz_rzmr": [40e8, 44e8],
    })

    def fake(days=180):
        return df

    monkeypatch.setattr(mt, "get_margin_trading_data", fake)
    s = mt.get_latest_margin_summary()
    assert s["date"] == "2024-01-02"
    assert s["total_rzmr_yi"] == 110.0
    assert abs(s["rzmr_change_pct"] - 10.0) < 1e-9
    assert abs(s["rzye_change_pct"] - (-10.0)) < 1e-9
    assert abs(s["rzmr_change_yi"] - 10.0) < 1e-9


def test_get_latest_margin_summary_nan_safe(monkeypatch):
    df = pd.DataFrame({
        "日期": ["2024-01-01", "2024-01-02"],
        "total_rzmr": [100e8, np.nan],     # 最新一日 NaN
        "total_rzye": [1000e8, 900e8],
        "sh_rzmr": [60e8, 66e8],
        "sz_rzmr": [40e8, 44e8],
    })

    def fake(days=180):
        return df

    monkeypatch.setattr(mt, "get_margin_trading_data", fake)
    s = mt.get_latest_margin_summary()
    # NaN 单元：绝不出现 nan / 崩溃，回退为有限兜底值（0.0 / -100.0），而非 None
    assert s["rzmr_change_pct"] == 0.0
    assert s["rzmr_change_yi"] == -100.0
    assert math.isfinite(s["rzmr_change_pct"])
    assert not isinstance(s["rzmr_change_pct"], type(None))
    # 其余单元仍正常
    assert abs(s["rzye_change_pct"] - (-10.0)) < 1e-9


def test_plot_margin_trend_empty_no_network():
    fig = mt.plot_margin_trend(None)
    assert isinstance(fig, go.Figure)
    fig2 = mt.plot_margin_trend(pd.DataFrame())
    assert isinstance(fig2, go.Figure)
