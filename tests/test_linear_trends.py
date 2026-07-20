"""
线性表达组件单元测试（mock akshare / StockFetcher / fundflow）。
验证 4 组数据层 getter 与 4 个绘图函数：空输入兜底、正常数据解析、主题适配、attrs 标记。
"""
import sys
import os
from datetime import datetime, timedelta
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
