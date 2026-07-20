"""
线性表达组件单元测试（mock akshare / StockFetcher / fundflow）。
验证 4 组数据层 getter 与 4 个绘图函数：空输入兜底、正常数据解析、主题适配、attrs 标记。
"""
import sys
import os
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go

import pytest

# 确保项目根目录在 sys.path（tests 目录的上级）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from unittest import mock

import modules.fundflow as ff
import modules.linear_trends as lt


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个用例前清空 fundflow 的 TTL 缓存，避免跨用例命中 mock 残留。"""
    ff._CACHE.clear()
    yield
    ff._CACHE.clear()


# ───────────────────────── 1. 北向资金历史序列 ─────────────────────────
def _nb_raw_df():
    dates = [datetime(2024, 1, i * 2 + 1) for i in range(5)]
    return pd.DataFrame({
        "日期": pd.to_datetime(dates),
        "当日成交净买额": [1e8, -5e7, 2e8, 0.0, 1.2e8],
        "历史累计净买额": [1.0e10, 1.05e10, 1.07e10, 1.07e10, 1.08e10],
    })


def test_northbound_history_series_ok():
    with mock.patch("akshare.stock_hsgt_hist_em", return_value=_nb_raw_df()):
        df = lt.get_northbound_history_series()
    assert not df.empty
    assert list(df.columns) == ["date", "net_buy_yi", "cumulative_yi"]
    assert df["net_buy_yi"].iloc[0] == pytest.approx(1.0)         # 1e8 / 1e8 = 1.0 亿
    assert df["cumulative_yi"].iloc[0] == pytest.approx(100.0)    # 1e10 / 1e8 = 100 亿
    assert df["date"].iloc[0] == "2024-01-01"


def test_northbound_history_series_empty_on_fail():
    with mock.patch("akshare.stock_hsgt_hist_em", side_effect=RuntimeError("boom")):
        df = lt.get_northbound_history_series()
    assert df.empty


def test_plot_northbound_history_empty():
    fig = lt.plot_northbound_history(pd.DataFrame(), dark_mode=False)
    assert isinstance(fig, go.Figure)


def test_plot_northbound_history_traces():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "net_buy_yi": [1.0, -0.5],
        "cumulative_yi": [10.0, 9.5],
    })
    fig = lt.plot_northbound_history(df, dark_mode=True)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # 净买额面积线 + 累计线


# ───────────────────────── 2. 个股主力资金逐日趋势 ─────────────────────────
def _ind_real_df():
    dates = [datetime(2024, 3, d) for d in range(1, 4)]
    return pd.DataFrame({
        "日期": pd.to_datetime(dates),
        "主力净流入-净额": [1e8, -2e8, 3e8],
        "超大单净流入-净额": [6e7, -1e8, 2e8],
        "大单净流入-净额": [4e7, -1e8, 1e8],
    })


def test_individual_series_real():
    with mock.patch("akshare.stock_individual_fund_flow", return_value=_ind_real_df()):
        df = lt.get_individual_fund_flow_series("600519", days=60)
    assert not df.empty
    assert df.attrs.get("source") == "akshare"
    assert list(df.columns)[:4] == ["date", "main_net", "super_net", "big_net"]
    assert df["date"].iloc[0] == "2024-03-01"


def test_individual_series_estimate_fallback():
    # 真实接口失败 → 走量价估算
    daily = pd.DataFrame({
        "date": pd.to_datetime([datetime(2024, 3, d) for d in range(1, 4)]),
        "open": [10, 11, 12], "high": [11, 12, 13],
        "low": [9, 10, 11], "close": [10.5, 11.5, 12.5],
        "volume": [1000, 1100, 1200],
    })

    with mock.patch("akshare.stock_individual_fund_flow",
                   side_effect=RuntimeError("no real")):
        with mock.patch("modules.fetcher.StockFetcher.get_daily", return_value=daily):
            df = lt.get_individual_fund_flow_series("600519", days=60)
    assert not df.empty
    assert df.attrs.get("source") == "estimate"
    # 估算：收盘价走高 → 主力净流入为正
    assert (df["main_net"] > 0).all()
    # 超大单 + 大单 与 主力 同号，且为 0.35/0.65 拆分
    assert df["super_net"].abs().sum() == pytest.approx(df["main_net"].abs().sum() * 0.35, rel=1e-6)
    assert df["big_net"].abs().sum() == pytest.approx(df["main_net"].abs().sum() * 0.65, rel=1e-6)


def test_individual_series_none_when_both_fail():
    with mock.patch("akshare.stock_individual_fund_flow",
                   side_effect=RuntimeError("no real")):
        with mock.patch("modules.fetcher.StockFetcher.get_daily",
                        return_value=pd.DataFrame()):
            df = lt.get_individual_fund_flow_series("600519", days=60)
    assert df.attrs.get("source") == "none"


def test_plot_individual_series_empty():
    fig = lt.plot_individual_series(pd.DataFrame(), dark_mode=False)
    assert isinstance(fig, go.Figure)


def test_plot_individual_series_traces():
    df = pd.DataFrame({
        "date": ["2024-03-01", "2024-03-02"],
        "main_net": [1e8, -2e8],
        "super_net": [6e7, -1e8],
        "big_net": [4e7, -1e8],
    })
    df.attrs["source"] = "akshare"
    fig = lt.plot_individual_series(df, name="贵州茅台", code="600519", dark_mode=False)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3  # 主力 + 超大单 + 大单


# ───────────────────────── 3. 三大指数走势对比 ─────────────────────────
def _idx_df(sym, vals):
    # 模拟 akshare 原始返回：含 "close" 列（重命名在 _fetch_index 内完成）
    dates = [datetime(2024, 1, d) for d in range(1, 1 + len(vals))]
    return pd.DataFrame({"date": pd.to_datetime(dates), "close": vals})


def test_index_series_ok():
    with mock.patch("akshare.stock_zh_index_daily",
                    side_effect=lambda symbol: _idx_df(symbol, [3000, 3050, 3100])):
        df = lt.get_index_series(days=180)
    assert not df.empty
    for c in ("sh000001", "sz399001", "sz399006"):
        assert c in df.columns
    assert len(df) == 3


def test_index_series_empty_on_fail():
    with mock.patch("akshare.stock_zh_index_daily", side_effect=RuntimeError("x")):
        df = lt.get_index_series(days=180)
    assert df.empty


def test_plot_index_series_normalized():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "sh000001": [3000, 3060, 3090],
        "sz399001": [10000, 10100, 9900],
        "sz399006": [2000, 2040, 2080],
    })
    fig = lt.plot_index_series(df, dark_mode=False)
    assert isinstance(fig, go.Figure)
    # 三个指数 → 三条线
    assert len(fig.data) == 3
    # 归一化起点=100
    assert fig.data[0].y[0] == pytest.approx(100.0)


def test_plot_index_series_empty():
    fig = lt.plot_index_series(pd.DataFrame(), dark_mode=True)
    assert isinstance(fig, go.Figure)


# ───────────────────────── 4. 大盘主力资金累计净流入 ─────────────────────────
def _market_ff_df():
    dates = [datetime(2024, 5, d) for d in range(1, 4)]
    return pd.DataFrame({
        "日期": pd.to_datetime(dates),
        "主力净流入-净额": [100.0, -50.0, 80.0],
        "上证-涨跌幅": [0.5, -0.3, 0.8],
    })


def test_market_cumulative_series():
    with mock.patch("modules.fundflow.get_market_fund_flow",
                    return_value=_market_ff_df()):
        df = lt.get_market_cumulative_series(days=60)
    assert not df.empty
    assert list(df.columns) == ["date", "main_net", "cumulative"]
    assert df["cumulative"].tolist() == [100.0, 50.0, 130.0]


def test_market_cumulative_series_empty():
    with mock.patch("modules.fundflow.get_market_fund_flow",
                    return_value=pd.DataFrame()):
        df = lt.get_market_cumulative_series(days=60)
    assert df.empty


def test_plot_market_cumulative_empty():
    fig = lt.plot_market_cumulative(pd.DataFrame(), dark_mode=False)
    assert isinstance(fig, go.Figure)


def test_plot_market_cumulative_traces():
    df = pd.DataFrame({
        "date": ["2024-05-01", "2024-05-02", "2024-05-03"],
        "main_net": [100.0, -50.0, 80.0],
        "cumulative": [100.0, 50.0, 130.0],
    })
    fig = lt.plot_market_cumulative(df, dark_mode=True)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # 累计面积线 + 当日细线
    # 累计末尾为正 → 红色
    assert fig.data[0].line.color == lt.UP


# ───────────────────────── 5. 行业板块指数价格趋势 ─────────────────────────
def _hist_df(vals):
    dates = [datetime(2024, 1, d) for d in range(1, 1 + len(vals))]
    return pd.DataFrame({
        "日期": pd.to_datetime(dates),
        "开盘": vals, "收盘": vals, "最高": vals, "最低": vals,
        "成交量": [1e6] * len(vals),
    })


def test_get_industry_index_series_ok():
    names = ["半导体", "银行", "白酒", "医药", "新能源", "汽车"]
    with mock.patch("akshare.stock_board_industry_name_em", return_value=names):
        with mock.patch("akshare.stock_board_industry_hist_em",
                        side_effect=lambda symbol, **kw: _hist_df([10, 11, 12])):
            df = lt.get_industry_index_series(top_n=8, days=120)
    assert not df.empty
    assert "date" in df.columns
    for nm in names:
        assert nm in df.columns
    assert len(df) == 3  # 3 个交易日


def test_get_industry_index_series_empty_on_fail():
    with mock.patch("akshare.stock_board_industry_name_em", side_effect=RuntimeError("x")):
        with mock.patch("akshare.stock_board_industry_hist_em", side_effect=RuntimeError("y")):
            df = lt.get_industry_index_series(top_n=8, days=120)
    assert df.empty


# ───────────────────────── 6. ETF 价格趋势 ─────────────────────────
def test_get_etf_series_ok():
    with mock.patch("akshare.fund_etf_hist_em",
                    side_effect=lambda symbol, **kw: _hist_df([5, 6, 7])):
        df = lt.get_etf_series(days=180)
    assert not df.empty
    assert "date" in df.columns
    for code, _nm in lt._ETF_LIST:
        assert code in df.columns


def test_get_etf_series_empty_on_fail():
    with mock.patch("akshare.fund_etf_hist_em", side_effect=RuntimeError("x")):
        df = lt.get_etf_series(days=180)
    assert df.empty


# ───────────────────────── 共享：plot_normalized_multi（区间 + 均线） ─────────────────────────
def _wide_df(dates, series):
    out = {"date": dates}
    out.update(series)
    return pd.DataFrame(out)


def test_plot_normalized_multi_basic():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        {"A": [100, 110, 121], "B": [200, 190, 180]},
    )
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # 两条基线
    # 归一化起点=100
    assert fig.data[0].y[0] == pytest.approx(100.0)
    assert fig.data[1].y[0] == pytest.approx(100.0)
    # 第二条线下降 → 末值 < 100
    assert fig.data[1].y[-1] < 100.0


def test_plot_normalized_multi_date_range():
    dates = [f"2024-01-0{i}" for i in range(1, 7)]  # 01..06
    df = _wide_df(dates, {"A": [100, 102, 104, 106, 108, 110]})
    fig = lt.plot_normalized_multi(
        df, title="t", dark_mode=False, date_range=("2024-01-03", "2024-01-06"))
    assert fig.data[0].x[0] == "2024-01-03"
    assert fig.data[0].y[0] == pytest.approx(100.0)  # 区间内首值归一
    assert len(fig.data[0].x) == 4


def test_plot_normalized_multi_ma_visible_when_few():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        {"A": [100, 110, 121], "B": [200, 190, 180]},
    )
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, ma_periods=(2,))
    # 2 基线 + 2 MA（≤3 序列，MA 默认可见，与基线交错排列）
    assert len(fig.data) == 4
    ma_traces = [t for t in fig.data if t.name.endswith("·MA2")]
    assert len(ma_traces) == 2
    # 默认可见（非 legendonly）
    assert all(t.visible != "legendonly" for t in ma_traces)


def test_plot_normalized_multi_ma_legendonly_when_many():
    series = {f"S{i}": [100 + i * 10 + j for j in range(3)] for i in range(8)}
    dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
    df = _wide_df(dates, series)
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, ma_periods=(2,))
    # 8 基线 + 8 MA（>3 序列，MA 默认 legendonly）
    assert len(fig.data) == 16
    ma_traces = [t for t in fig.data if t.name.endswith("·MA2")]
    assert len(ma_traces) == 8
    # >3 序列时 MA 默认进图例（legendonly）
    assert all(t.visible == "legendonly" for t in ma_traces)


def test_plot_normalized_multi_empty():
    fig = lt.plot_normalized_multi(pd.DataFrame(), dark_mode=True)
    assert isinstance(fig, go.Figure)


# ───────────────────────── 现有图：date_range / ma_periods 交互参数 ─────────────────────────
def test_plot_northbound_history_with_ma():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "net_buy_yi": [1.0, -0.5, 2.0],
        "cumulative_yi": [10.0, 9.5, 11.5],
    })
    fig = lt.plot_northbound_history(df, dark_mode=False, ma_periods=(2,))
    assert isinstance(fig, go.Figure)
    # 净买额基线 + 净买额 MA + 累计线 = 3
    assert len(fig.data) == 3
    ma_traces = [t for t in fig.data if t.name.endswith("·MA2")]
    assert len(ma_traces) == 1
    assert ma_traces[0].name == "当日净买额(亿)·MA2"


def test_plot_index_series_with_date_range():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "sh000001": [3000, 3060, 3090, 3120],
        "sz399001": [10000, 10100, 9900, 10200],
        "sz399006": [2000, 2040, 2080, 2100],
    })
    fig = lt.plot_index_series(df, dark_mode=False, date_range=("2024-01-02", "2024-01-04"))
    assert fig.data[0].x[0] == "2024-01-02"
    assert fig.data[0].y[0] == pytest.approx(100.0)
    assert len(fig.data[0].x) == 3


def test_plot_individual_series_with_ma():
    df = pd.DataFrame({
        "date": ["2024-03-01", "2024-03-02", "2024-03-03"],
        "main_net": [1e8, -2e8, 3e8],
        "super_net": [6e7, -1e8, 2e8],
        "big_net": [4e7, -1e8, 1e8],
    })
    df.attrs["source"] = "akshare"
    fig = lt.plot_individual_series(df, dark_mode=False, ma_periods=(2,))
    assert isinstance(fig, go.Figure)
    # 主力 + 超大单 + 大单 + 1 MA = 4
    assert len(fig.data) == 4


def test_plot_market_cumulative_with_date_range():
    df = pd.DataFrame({
        "date": ["2024-05-01", "2024-05-02", "2024-05-03", "2024-05-04"],
        "main_net": [100.0, -50.0, 80.0, 20.0],
        "cumulative": [100.0, 50.0, 130.0, 150.0],
    })
    fig = lt.plot_market_cumulative(df, dark_mode=False, date_range=("2024-05-03", "2024-05-04"))
    assert fig.data[0].x[0] == "2024-05-03"
    assert fig.data[0].y[0] == pytest.approx(130.0)  # 区间内首值


# ───────────────────────── Iter1 序列多选（selected） ─────────────────────────
def test_plot_normalized_multi_selected_filters_columns():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        {"A": [100, 110, 121], "B": [200, 190, 180], "C": [50, 55, 60]},
    )
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, selected=["A", "C"])
    names = [t.name for t in fig.data if not t.name.endswith("MA")]
    assert set(names) == {"A", "C"}


def test_plot_normalized_multi_selected_allows_empty():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        {"A": [100, 110, 121]},
    )
    # selected 为空列表 → 无基线（仅兜底图）
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, selected=[])
    assert isinstance(fig, go.Figure)


# ───────────────────────── Iter3 归一化 / 原始切换（mode） ─────────────────────────
def test_plot_normalized_multi_raw_mode_uses_actual_values():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        {"A": [100, 110, 121]},
    )
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, mode="raw")
    assert fig.data[0].y[0] == pytest.approx(100.0)   # 原始值，非 100
    assert fig.data[0].y[-1] == pytest.approx(121.0)
    assert fig.layout.yaxis.title.text == "价格（元）"


# ───────────────────────── Iter4 EMA 切换（ma_type） ─────────────────────────
def test_plot_normalized_multi_ema_naming():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        {"A": [100, 110, 121, 130], "B": [200, 190, 180, 170]},
    )
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, ma_periods=(2,), ma_type="ema")
    ema_traces = [t for t in fig.data if t.name.endswith("·EMA2")]
    assert len(ema_traces) == 2
    # EMA 非 NaN（至少末端有值）
    assert ema_traces[0].y[-1] is not None


# ───────────────────────── Iter5 基准线（show_baseline） ─────────────────────────
def test_plot_normalized_multi_baseline_shape():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        {"A": [100, 110, 121]},
    )
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, show_baseline=True)
    # add_hline 注入一条 type='line' 的 shape
    lines = [s for s in (fig.layout.shapes or []) if getattr(s, "type", None) == "line"]
    assert len(lines) == 1
    assert lines[0].y0 == 100


def test_plot_northbound_history_zero_baseline():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "net_buy_yi": [1.0, -0.5],
        "cumulative_yi": [10.0, 9.5],
    })
    fig = lt.plot_northbound_history(df, dark_mode=False, show_baseline=True)
    lines = [s for s in (fig.layout.shapes or []) if getattr(s, "type", None) == "line"]
    assert len(lines) == 1
    assert lines[0].y0 == 0


# ───────────────────────── Iter6 金叉/死叉标注（show_cross） ─────────────────────────
def test_plot_normalized_multi_cross_markers():
    df = _wide_df(
        ["2024-01-0%d" % i for i in range(1, 7)],
        {"UP": [10, 11, 12, 13, 14, 15], "DN": [15, 14, 13, 12, 11, 10]},
    )
    fig = lt.plot_normalized_multi(
        df, title="t", dark_mode=False, ma_periods=(2, 3), show_cross=True)
    cross_traces = [t for t in fig.data
                    if getattr(t, "marker", None) and str(getattr(t.marker, "symbol", "")).startswith("triangle")]
    # 上行序列产生金叉、下行序列产生死叉 → 至少各一
    ups = [t for t in cross_traces if t.marker.symbol == "triangle-up"]
    dns = [t for t in cross_traces if t.marker.symbol == "triangle-down"]
    assert len(ups) >= 1
    assert len(dns) >= 1


def test_golden_death_cross_helper():
    xs = pd.Series(["2024-01-0%d" % i for i in range(1, 7)])
    y = pd.Series([10, 11, 12, 13, 14, 15])  # 单调上行 → 金叉
    golden, death = lt._golden_death_cross(xs, y, 2, 3)
    assert isinstance(golden, list)
    assert isinstance(death, list)
    # 至少检测到一次金叉
    assert len(golden) >= 1
    assert len(death) == 0


def test_max_drawdown_idx_helper():
    s = pd.Series([10.0, 12.0, 9.0, 11.0])  # 峰12(idx1) 谷9(idx2)
    res = lt._max_drawdown_idx(s)
    assert res is not None
    peak_i, trough_i, mdd = res
    assert peak_i == 1
    assert trough_i == 2
    assert mdd < 0
    assert mdd == pytest.approx((9.0 - 12.0) / 12.0, rel=1e-6)


def test_max_drawdown_idx_none_when_monotonic_up():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert lt._max_drawdown_idx(s) is None


# ───────────────────────── Iter7 最大回撤标注（show_drawdown） ─────────────────────────
def test_plot_normalized_multi_drawdown_annotation():
    df = _wide_df(
        ["2024-01-0%d" % i for i in range(1, 5)],
        {"A": [10, 12, 9, 11]},
    )
    fig = lt.plot_normalized_multi(df, title="t", dark_mode=False, show_drawdown=True)
    # add_vrect 注入 type='rect' 的 shape
    rects = [s for s in (fig.layout.shapes or []) if getattr(s, "type", None) == "rect"]
    assert len(rects) == 1
    # 回撤标注以 annotation 形式呈现
    assert len(fig.layout.annotations or []) >= 1
    assert "最大回撤" in (fig.layout.annotations[0].text or "")


# ───────────────────────── Iter9 导出 CSV（to_trend_csv） ─────────────────────────
def test_to_trend_csv_basic_and_filter():
    df = _wide_df(
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        {"A": [100, 110, 121], "B": [200, 190, 180], "C": [50, 55, 60]},
    )
    csv_all = lt.to_trend_csv(df)
    assert "date" in csv_all
    assert "A" in csv_all and "B" in csv_all and "C" in csv_all
    # 区间 + 序列过滤
    csv_f = lt.to_trend_csv(df, selected=["A", "C"], date_range=("2024-01-02", "2024-01-03"))
    assert "B" not in csv_f
    # 仅含区间内两行 + 表头
    assert csv_f.count("\n") == 3


def test_to_trend_csv_empty():
    assert lt.to_trend_csv(pd.DataFrame()) == ""


# ───────────────────────── Iter10 相关性热力图（plot_correlation_heatmap） ─────────────────────────
def test_plot_correlation_heatmap_basic():
    df = _wide_df(
        ["2024-01-0%d" % i for i in range(1, 6)],
        {"A": [100, 102, 104, 106, 108],
         "B": [200, 202, 204, 206, 208],
         "C": [50, 60, 55, 65, 70]},
    )
    names_map = {"A": "序列A", "B": "序列B", "C": "序列C"}
    fig = lt.plot_correlation_heatmap(df, names_map=names_map, dark_mode=False)
    assert isinstance(fig, go.Figure)
    heat = fig.data[0]
    assert isinstance(heat, go.Heatmap)
    # 3 序列 → 3x3 相关矩阵
    assert heat.z.shape == (3, 3)
    # A 与 B 高度正相关 → 接近 1
    assert heat.z[0][1] == pytest.approx(1.0, abs=1e-2)


def test_plot_correlation_heatmap_too_few_series():
    df = _wide_df(["2024-01-01", "2024-01-02"], {"A": [100, 110]})
    fig = lt.plot_correlation_heatmap(df, dark_mode=False)
    assert isinstance(fig, go.Figure)
    # 不足 2 序列 → 无热力图 trace
    assert len(fig.data) == 0



