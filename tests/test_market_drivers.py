"""
市场驱动力五维面板单元测试（离线 mock，不触网）。

覆盖：
- 指标注册表结构（5 维覆盖、22 条线、必填字段、KNOWN_UNAVAILABLE 一致）
- 工具函数：_norm100 归一化、_col 模糊列匹配
- get_market_drivers：正常合并 / 全源失败优雅降级
- plot_drivers_panel：子图数=维度数、上证参考线存在、selected 过滤、区间切片、
  空 DataFrame 兜底、meta 标注未接入维度不崩溃
- 复用线性模块 to_trend_csv / plot_correlation_heatmap 消费驱动力宽表
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import modules.market_drivers as m
from modules.market_drivers import (
    INDICATORS, DIMS, KNOWN_UNAVAILABLE, _norm100, _col,
    get_market_drivers, plot_drivers_panel,
)

# 供复用测试：线性模块 helper
import modules.linear_trends as lt


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个用例前清空市场驱动力 TTL 缓存，避免跨用例命中残留。"""
    m._CACHE.clear()
    yield
    m._CACHE.clear()


@pytest.fixture
def syn_dates():
    return pd.date_range("2024-01-01", periods=20, freq="D")


@pytest.fixture
def driver_df(syn_dates):
    """合成五维驱动力宽表（每个维度至少 1 个可用 key + 上证参考线）。"""
    rng = np.random.default_rng(42)
    base_sh = 3000 + np.cumsum(rng.normal(0, 10, 20))
    return pd.DataFrame({
        "date": syn_dates,
        # 资金
        "margin_balance": 15000 + np.cumsum(rng.normal(0, 50, 20)),   # 亿元级
        "north_net": rng.normal(0, 30, 20),                            # 亿元级
        # 情绪
        "vix": rng.uniform(12, 30, 20),
        # 估值
        "pe_pct": rng.uniform(20, 80, 20),
        # 宏观
        "m2_yoy": rng.uniform(8, 12, 20),
        # 技术（应为 0-100 量纲，验证不会因量纲被压扁）
        "rsi": rng.uniform(20, 80, 20),
        # 上证参考
        "ref": base_sh,
    })


# ───────────────────────── 1. 注册表结构 ─────────────────────────
def test_indicators_count_is_22():
    # CSV 21 指标，MA 含 5/20 双周期 → 22 条线
    assert len(INDICATORS) == 22


def test_indicators_cover_all_five_dims():
    dims_present = {ind["dim"] for ind in INDICATORS}
    assert dims_present == set(DIMS)


def test_each_indicator_has_required_fields():
    for ind in INDICATORS:
        for f in ("key", "dim", "name", "unit", "src"):
            assert f in ind, f"指标 {ind.get('key')} 缺字段 {f}"
        assert ind["dim"] in DIMS


def test_each_dim_has_at_least_one_indicator():
    per_dim = {d: 0 for d in DIMS}
    for ind in INDICATORS:
        per_dim[ind["dim"]] += 1
    assert all(v > 0 for v in per_dim.values())


def test_known_unavailable_keys_present_in_registry():
    reg_keys = {ind["key"] for ind in INDICATORS}
    for k in KNOWN_UNAVAILABLE:
        assert k in reg_keys, f"{k} 在注册表缺失但标注为暂未接入"


def test_csv_21_indicators_mapped_to_dims():
    # CSV 分 9 类，本面板并成 5 维（资金/情绪/估值/宏观/技术）
    # 校验 5 维均非空且总量=22（含 MA 双周期）
    counts = {d: sum(1 for i in INDICATORS if i["dim"] == d) for d in DIMS}
    assert counts["资金"] == 8
    assert counts["情绪"] == 3
    assert counts["估值"] == 2
    assert counts["宏观"] == 4
    assert counts["技术"] == 5
    assert sum(counts.values()) == 22


# ───────────────────────── 2. 工具函数 ─────────────────────────
def test_norm100_normalizes_first_value_to_100():
    s = pd.Series([10.0, 20.0, 30.0, 5.0])
    out = _norm100(s)
    assert abs(out.iloc[0] - 100.0) < 1e-9
    # 形状保持比例
    assert abs(out.iloc[1] - 200.0) < 1e-9
    assert abs(out.iloc[2] - 300.0) < 1e-9


def test_norm100_handles_zero_base():
    # 起点为 0 时无法归一化，应原样返回（不抛错、不出现 inf）
    s = pd.Series([0.0, 1.0, 2.0])
    out = _norm100(s)
    assert np.isfinite(out).all()
    assert list(out.values) == [0.0, 1.0, 2.0]


def test_norm100_empty_returns_empty():
    out = _norm100(pd.Series([], dtype=float))
    assert out.empty


def test_norm100_drops_na():
    s = pd.Series([5.0, np.nan, 10.0])
    out = _norm100(s)
    assert out.iloc[0] == 100.0
    assert len(out) == 2


def test_col_fuzzy_match_case_insensitive():
    df = pd.DataFrame({"当日成交净买额": [1], "日期": [2]})
    assert _col(df, "净买额") == "当日成交净买额"
    assert _col(df, "期") == "日期"


def test_col_returns_none_when_no_match():
    df = pd.DataFrame({"foo": [1]})
    assert _col(df, "bar", "baz") is None


# ───────────────────────── 3. get_market_drivers ─────────────────────────
def test_get_market_drivers_all_fail_graceful(monkeypatch):
    """所有源失败 → 返回空 df（仅 date 列）+ 全维度 unavailable，绝不抛红错。"""
    def fake_fetch(ind, days):
        return [], "mock 抓取失败"
    monkeypatch.setattr(m, "_fetch_src", fake_fetch)
    # 参考线也失败
    monkeypatch.setattr(m, "_get_index_close", lambda days: None)

    df, meta = get_market_drivers(days=30)
    assert list(df.columns) == ["date"]
    for d in DIMS:
        assert meta[d]["available"] == []
        assert len(meta[d]["unavailable"]) > 0


def test_get_market_drivers_merge_and_meta(monkeypatch):
    """合成各源成功 → 宽表含各 key + 参考线逻辑、meta 可用列表被填充。"""
    def fake_fetch(ind, days):
        key = ind["key"]
        if key in KNOWN_UNAVAILABLE:
            return [], KNOWN_UNAVAILABLE[key]
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        s = pd.Series(np.arange(10, 20, dtype=float), index=dates)
        return [(key, ind["name"], s)], None
    monkeypatch.setattr(m, "_fetch_src", fake_fetch)
    monkeypatch.setattr(m, "_get_index_close", lambda days: pd.Series(
        np.arange(3000, 3010, dtype=float),
        index=pd.date_range("2024-01-01", periods=10, freq="D")))

    df, meta = get_market_drivers(days=10)
    assert "date" in df.columns
    # 非暂未接入的 key 都应出现在宽表
    expected = {ind["key"] for ind in INDICATORS if ind["key"] not in KNOWN_UNAVAILABLE}
    expected.add("ref")
    for k in expected:
        assert k in df.columns, f"合成数据缺失列 {k}"
    # 暂未接入维度 meta 标记
    for k in KNOWN_UNAVAILABLE:
        dim = next(i["dim"] for i in INDICATORS if i["key"] == k)
        assert (k, KNOWN_UNAVAILABLE[k]) in meta[dim]["unavailable"]


def test_get_market_drivers_top_level_no_raise(monkeypatch):
    """即使 _build 抛异常，也应降级返回空 df + 全 unavailable。"""
    def boom(ind, days):
        raise RuntimeError("boom")
    monkeypatch.setattr(m, "_fetch_src", boom)
    df, meta = get_market_drivers(days=10)
    assert list(df.columns) == ["date"]
    for d in DIMS:
        assert meta[d]["available"] == []


# ───────────────────────── 4. plot_drivers_panel ─────────────────────────
def test_panel_empty_df_returns_figure_with_placeholder_title():
    fig = plot_drivers_panel(pd.DataFrame(columns=["date"]), None)
    assert isinstance(fig, go.Figure)
    assert "暂无" in (fig.layout.title.text or "")


def test_panel_subplot_count_equals_dims(driver_df):
    fig = plot_drivers_panel(driver_df, None)
    # 5 个维度 → 5 行子图
    assert fig._grid_ref is not None
    n_rows = len(fig._grid_ref)
    assert n_rows == len(DIMS)


def test_panel_subset_dims_subplot_count(driver_df):
    fig = plot_drivers_panel(driver_df, None, dims=["资金", "技术"])
    assert len(fig._grid_ref) == 2


def test_panel_invalid_dim_filtered_out(driver_df):
    fig = plot_drivers_panel(driver_df, None, dims=["资金", "不存在维"])
    assert len(fig._grid_ref) == 1


def test_panel_ref_line_present_in_each_subplot(driver_df):
    """每个子图都应包含上证(参考)线，便于看领先/背离。"""
    fig = plot_drivers_panel(driver_df, None)
    ref_traces = [t for t in fig.data if "上证" in (t.name or "")]
    # 5 个子图各一条参考线
    assert len(ref_traces) == len(DIMS)


def test_panel_dimension_normalized_not_raw_scaled(driver_df):
    """同一子图内量纲不同的指标共存，归一化后应可见且无全 0/全 NaN。"""
    fig = plot_drivers_panel(driver_df, None, dims=["资金"])
    # 资金子图含 margin_balance(亿元级) + north_net + ref
    names = [t.name for t in fig.data]
    assert "margin_balance" in names or "north_net" in names
    # 归一化后每个 trace 的首值应≈100
    for t in fig.data:
        if t.name and t.y is not None and len(t.y) > 0:
            assert abs(t.y[0] - 100.0) < 1e-6


def test_panel_selected_filters_keys(driver_df):
    fig = plot_drivers_panel(driver_df, None, dims=["资金"], selected=["north_net"])
    names = {t.name for t in fig.data}
    # 仅 north_net 与 ref(上证) 应出现
    assert "margin_balance" not in names
    assert "north_net" in names


def test_panel_date_range_slices(driver_df):
    dr = (datetime(2024, 1, 5), datetime(2024, 1, 10))
    fig = plot_drivers_panel(driver_df, None, date_range=dr)
    # 所有 trace 的 x 应落在切片区间内
    for t in fig.data:
        if t.x is not None and len(t.x) > 0:
            xs = pd.to_datetime(t.x)
            assert xs.min() >= pd.Timestamp("2024-01-05")
            assert xs.max() <= pd.Timestamp("2024-01-10")


def test_panel_meta_unavailable_dim_no_crash(driver_df):
    """meta 标注某维度无可用数据 → 该子图加注解，整体不崩。"""
    meta = {d: {"available": [], "unavailable": []} for d in DIMS}
    meta["情绪"] = {"available": [], "unavailable": [("vix", "暂未接入")]}
    fig = plot_drivers_panel(driver_df, meta, dims=["情绪", "技术"])
    assert isinstance(fig, go.Figure)
    assert len(fig._grid_ref) == 2


def test_panel_no_data_in_range_placeholder(driver_df):
    fig = plot_drivers_panel(driver_df, None,
                             date_range=(datetime(2030, 1, 1), datetime(2030, 1, 2)))
    assert "所选区间无数据" in (fig.layout.title.text or "")


def test_panel_light_and_dark_mode_return_figure(driver_df):
    f_light = plot_drivers_panel(driver_df, None, dark_mode=False)
    f_dark = plot_drivers_panel(driver_df, None, dark_mode=True)
    assert isinstance(f_light, go.Figure) and isinstance(f_dark, go.Figure)
    # 暗色字体应为浅色
    assert f_dark.layout.font.color == "#e6e6e6"


def test_panel_title_override(driver_df):
    fig = plot_drivers_panel(driver_df, None, title="自定义标题")
    assert fig.layout.title.text == "自定义标题"


# ───────────────────────── 5. 复用线性模块 helper ─────────────────────────
def test_reuse_to_trend_csv_on_driver_df(driver_df):
    csv = lt.to_trend_csv(driver_df, names_map=None, selected=None, date_range=None)
    assert isinstance(csv, str) and csv.strip() != ""
    assert "date" in csv


def test_reuse_correlation_heatmap_on_driver_df(driver_df):
    fig = lt.plot_correlation_heatmap(driver_df, names_map=None, selected=None,
                                      date_range=None, title="驱动力相关性")
    assert isinstance(fig, go.Figure)
    # 至少有 2 个有效序列，应含 heatmap trace
    assert len(fig.data) >= 1
