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
    _market_temp, _temp_level, _score_one_dim, _DIR, _MARKET_TEMP_DEFAULT,
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
    # 绕过 _cached 缓存优先：降级逻辑必须在本次调用内真实执行，
    # 否则会读到同进程其他用例（如 merge_and_meta）写入的缓存，使断言失真。
    monkeypatch.setattr(m, "_cached", lambda ttl, key, fn: fn())
    def fake_fetch(ind, days):
        return [], "mock 抓取失败"
    monkeypatch.setattr(m, "_fetch_src", fake_fetch)
    # 参考线也失败
    monkeypatch.setattr(m, "_get_index_close", lambda days: None)
    # 同时屏蔽 SQLite 持久缓存兜底，确保降级路径返回的是「空 df」而非历史缓存
    import modules.market_cache as _mc
    monkeypatch.setattr(_mc, "load_drivers_from_cache", lambda days: (None, None))

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
    # 绕过 _cached：确保 _build 本次真实执行并触发异常降级路径
    monkeypatch.setattr(m, "_cached", lambda ttl, key, fn: fn())
    def boom(ind, days):
        raise RuntimeError("boom")
    monkeypatch.setattr(m, "_fetch_src", boom)
    # 同时屏蔽 SQLite 持久缓存兜底，确保异常降级路径返回的是「空 df」而非历史缓存
    import modules.market_cache as _mc
    monkeypatch.setattr(_mc, "load_drivers_from_cache", lambda days: (None, None))
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


# ───────────────────────── 6. 市场温度评分（退化输入安全） ─────────────────────────
def test_market_temp_normal_finite_score():
    """正常输入 → 有限、在 0-100 区间的温度分。"""
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "margin_balance": 15000 + np.cumsum(rng.normal(0, 50, 30)),
        "vix": rng.uniform(12, 30, 30),
        "pe_pct": rng.uniform(20, 80, 30),
        "rsi": rng.uniform(20, 80, 30),
        "north_net": rng.normal(0, 30, 30),
        "m2_yoy": rng.uniform(8, 12, 30),
    })
    t = _market_temp(df)
    assert t is not None
    assert np.isfinite(t)
    assert 0.0 <= t <= 100.0


def test_market_temp_empty_df_safe_default():
    """空 DataFrame → 不抛错，返回安全中性默认。"""
    df = pd.DataFrame()
    t = _market_temp(df)
    assert np.isfinite(t)
    assert t == _MARKET_TEMP_DEFAULT


def test_market_temp_none_input_safe():
    """df 为 None → 不抛错，返回安全默认。"""
    t = _market_temp(None)
    assert np.isfinite(t)
    assert t == _MARKET_TEMP_DEFAULT


def test_market_temp_all_nan_safe():
    """全 NaN 列 → 不抛错，返回有限默认（无 NaN/inf 传播）。"""
    df = pd.DataFrame({
        "margin_balance": [np.nan] * 10,
        "vix": [np.nan] * 10,
        "pe_pct": [np.nan] * 10,
        "rsi": [np.nan] * 10,
    })
    t = _market_temp(df)
    assert np.isfinite(t)
    assert 0.0 <= t <= 100.0


def test_market_temp_missing_columns_safe():
    """_DIR 中的列全部缺失 → 不抛错，返回安全默认。"""
    df = pd.DataFrame({"unrelated": np.arange(20, dtype=float)})
    t = _market_temp(df)
    assert np.isfinite(t)
    assert t == _MARKET_TEMP_DEFAULT


def test_market_temp_very_short_series_safe():
    """每列仅 2 个样本(<3) → 不抛错，返回安全默认。"""
    df = pd.DataFrame({
        "margin_balance": [1.0, 2.0],
        "vix": [15.0, 16.0],
        "pe_pct": [30.0, 31.0],
    })
    t = _market_temp(df)
    assert np.isfinite(t)
    assert 0.0 <= t <= 100.0


def test_score_one_dim_short_series_returns_none():
    """隔离 helper：样本不足返回 None（不抛错）。"""
    assert _score_one_dim(pd.Series([1.0, 2.0]), 1) is None


def test_score_one_dim_full_nan_returns_none():
    """隔离 helper：全 NaN 返回 None。"""
    assert _score_one_dim(pd.Series([np.nan, np.nan, np.nan]), 1) is None


def test_score_one_dim_valid_direction_positive():
    """方向为正：最新值处于历史高位 → 高分。"""
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sc = _score_one_dim(s, 1)
    assert sc is not None and sc > 80.0  # 最新值=最高 → 分位近 100


def test_score_one_dim_valid_direction_negative():
    """方向为负：最新值处于历史高位(更冷) → 低分。"""
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sc = _score_one_dim(s, -1)
    assert sc is not None and sc < 20.0


def test_temp_level_normal_levels():
    """_temp_level 合法输入映射正确，行为与原实现一致。"""
    assert _temp_level(80) == ("过热", "🚨", "#ee2a2a")
    assert _temp_level(65) == ("偏热", "🔥", "#f59e0b")
    assert _temp_level(50) == ("中性", "⚖️", "#2b8aef")
    assert _temp_level(30) == ("偏冷", "🌡️", "#16c2c2")
    assert _temp_level(5) == ("冰点", "🥶", "#3b82f6")


def test_temp_level_nan_safe_default():
    """_temp_level 接收 NaN/None → 不抛错，返回安全中性标记。"""
    lvl, emoji, color = _temp_level(np.nan)
    assert emoji == "—"
    assert color == "#888888"
    lvl2, _, _ = _temp_level(None)
    assert lvl2 == "未知"


def test_market_temp_then_temp_level_pipeline_safe_on_empty():
    """端到端：空 df → 温度安全 → 等级安全，整链不抛错。"""
    t = _market_temp(pd.DataFrame())
    assert np.isfinite(t)
    level, emoji, color = _temp_level(t)
    assert isinstance(level, str)
    assert emoji != ""


class TestSrcDiv:
    """R93：_src_div 股息率第 5 路「PE 反推股息率」纯本地兜底。

    根因：legu stock_market_pe_lg 只返回【日期/总市值/市盈率】，不含股息率列；
    前面 4 路（legu 主/沪深300 PE/东财 spot/申万 sw）在沙箱/弱网下易连环失败。
    第 5 路只用 legu PE 历史 + payout_ratio 经验公式，0 网络依赖——保证
    div_yield 字段在沙箱/弱网下也有数据（payout=0.35 / PE=13 → 2.69%，
    与沪深 300 历史均值 ~2.5% 吻合）。
    """

    def test_div_via_pe_formula_runs_locally(self, monkeypatch):
        """模拟 legu 返回的数据（有 PE/日期但无股息率列），验证 PE 反推路径生效。"""
        import pandas as pd
        from datetime import datetime, timedelta

        # 构造 legu 假数据：仅 日期/总市值/市盈率 三列
        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(30)]
        fake_legu = pd.DataFrame({
            "日期": dates,
            "总市值": [100.0] * 30,
            "市盈率": [13.0, 13.2, 13.5, 13.3, 12.8, 12.5, 12.7, 13.1, 13.4, 13.0,
                     13.6, 13.5, 13.3, 13.0, 12.9, 12.7, 12.5, 12.3, 12.6, 12.9,
                     13.1, 13.4, 13.5, 13.3, 13.0, 12.8, 12.6, 12.9, 13.2, 13.4],
        })

        # 模拟：让 1-4 路全部失败/返回无效数据（沙箱场景），第 5 路走 PE 反推
        # 思路：mock 所有失败路径（raise 或空 df）+ stub 第 5 路内部调用的 ak 接口
        import modules.market_drivers as m

        # 让所有 legu 主路失败
        def _fail(*a, **k):
            raise ConnectionError("legu unavailable")

        # stub 强制让 stock_market_pe_lg 返回 fake_legu
        # 注：R89 修了参数 + R93 加了第 5 路，第 1 路 _col 失败+第 2-4 路全失败→
        # 落到第 5 路再次调 stock_market_pe_lg，此时需它返回数据。
        monkeypatch.setattr("akshare.stock_market_pe_lg", lambda *a, **k: fake_legu.copy())
        monkeypatch.setattr("akshare.stock_index_pe_lg", _fail)
        monkeypatch.setattr("akshare.stock_zh_a_spot_em", _fail)
        monkeypatch.setattr("akshare.sw_index_third_info", _fail)
        # 让 _cached 在 mock 下每次重算（清缓存）
        if hasattr(m, '_CACHE'):
            m._CACHE.clear()

        rows = m._src_div(days=180)
        assert len(rows) == 1, f"应有一条 div_yield，实际 {len(rows)}"
        key, name, series = rows[0]
        assert key == "div_yield"
        assert name == "股息率(PE反推)"
        # 时间序列（非单点）
        assert len(series) >= 20, f"应有 ~30 根时间序列，实际 {len(series)}"
        # 公式：div = 0.35 * 100 / PE = 35 / 13.4 ≈ 2.61%
        last = float(series.iloc[-1])
        assert 2.0 < last < 4.0, f"反推股息率应在 2-4% 区间（PE 12-17 范围），实际 {last:.2f}%"

    def test_div_returns_empty_when_all_paths_fail(self, monkeypatch):
        """所有路径都失败（ak 抛异常且第 5 路 PE 也失败）→ 返回 []，不崩。"""
        import modules.market_drivers as m

        def _fail(*a, **k):
            raise ConnectionError("all sources down")

        monkeypatch.setattr("akshare.stock_market_pe_lg", _fail)
        monkeypatch.setattr("akshare.stock_index_pe_lg", _fail)
        monkeypatch.setattr("akshare.stock_zh_a_spot_em", _fail)
        monkeypatch.setattr("akshare.sw_index_third_info", _fail)
        if hasattr(m, '_CACHE'):
            m._CACHE.clear()

        rows = m._src_div(days=180)
        # 5 路全失败 → 空列表（页面展示「数据源暂未接入」提示）
        assert rows == []


class TestSrcDiv:
    """R93：_src_div 股息率第 5 路「PE 反推股息率」纯本地兜底。

    根因：legu stock_market_pe_lg 只返回【日期/总市值/市盈率】，不含股息率列；
    前面 4 路（legu 主/沪深300 PE/东财 spot/申万 sw）在沙箱/弱网下易连环失败。
    第 5 路只用 legu PE 历史 + payout_ratio 经验公式，0 网络依赖——保证
    div_yield 字段在沙箱/弱网下也有数据（payout=0.35 / PE=13 → 2.69%，
    与沪深 300 历史均值 ~2.5% 吻合）。
    """

    def test_div_via_pe_formula_runs_locally(self, monkeypatch):
        """模拟 legu 返回的数据（有 PE/日期但无股息率列），验证 PE 反推路径生效。"""
        import pandas as pd
        from datetime import datetime, timedelta

        # 构造 legu 假数据：仅 日期/总市值/市盈率 三列
        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(30)]
        fake_legu = pd.DataFrame({
            "日期": dates,
            "总市值": [100.0] * 30,
            "市盈率": [13.0, 13.2, 13.5, 13.3, 12.8, 12.5, 12.7, 13.1, 13.4, 13.0,
                     13.6, 13.5, 13.3, 13.0, 12.9, 12.7, 12.5, 12.3, 12.6, 12.9,
                     13.1, 13.4, 13.5, 13.3, 13.0, 12.8, 12.6, 12.9, 13.2, 13.4],
        })

        # 模拟：让 1-4 路全部失败/返回无效数据（沙箱场景），第 5 路走 PE 反推
        # 思路：mock 所有失败路径（raise 或空 df）+ stub 第 5 路内部调用的 ak 接口
        import modules.market_drivers as m

        # 让所有 legu 主路失败
        def _fail(*a, **k):
            raise ConnectionError("legu unavailable")

        # stub 强制让 stock_market_pe_lg 返回 fake_legu
        # 注：R89 修了参数 + R93 加了第 5 路，第 1 路 _col 失败+第 2-4 路全失败→
        # 落到第 5 路再次调 stock_market_pe_lg，此时需它返回数据。
        monkeypatch.setattr("akshare.stock_market_pe_lg", lambda *a, **k: fake_legu.copy())
        monkeypatch.setattr("akshare.stock_index_pe_lg", _fail)
        monkeypatch.setattr("akshare.stock_zh_a_spot_em", _fail)
        monkeypatch.setattr("akshare.sw_index_third_info", _fail)
        # 让 _cached 在 mock 下每次重算（清缓存）
        if hasattr(m, '_CACHE'):
            m._CACHE.clear()

        rows = m._src_div(days=180)
        assert len(rows) == 1, f"应有一条 div_yield，实际 {len(rows)}"
        key, name, series = rows[0]
        assert key == "div_yield"
        assert name == "股息率(PE反推)"
        # 时间序列（非单点）
        assert len(series) >= 20, f"应有 ~30 根时间序列，实际 {len(series)}"
        # 公式：div = 0.35 * 100 / PE = 35 / 13.4 ≈ 2.61%
        last = float(series.iloc[-1])
        assert 2.0 < last < 4.0, f"反推股息率应在 2-4% 区间（PE 12-17 范围），实际 {last:.2f}%"

    def test_div_returns_empty_when_all_paths_fail(self, monkeypatch):
        """所有路径都失败（ak 抛异常且第 5 路 PE 也失败）→ 返回 []，不崩。"""
        import modules.market_drivers as m

        def _fail(*a, **k):
            raise ConnectionError("all sources down")

        monkeypatch.setattr("akshare.stock_market_pe_lg", _fail)
        monkeypatch.setattr("akshare.stock_index_pe_lg", _fail)
        monkeypatch.setattr("akshare.stock_zh_a_spot_em", _fail)
        monkeypatch.setattr("akshare.sw_index_third_info", _fail)
        if hasattr(m, '_CACHE'):
            m._CACHE.clear()

        rows = m._src_div(days=180)
        # 5 路全失败 → 空列表（页面展示「数据源暂未接入」提示）
        assert rows == []
