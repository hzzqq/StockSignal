"""visualizer 图表函数「缺失列 / 畸形输入」兜底回归测试（无网依赖）。

覆盖：
- 新能力 empty_figure（通用空图兜底，供所有图表复用）
- 隐式 bug 修复：backtest_curve / drawdown_curve / portfolio_pnl / sector_heatmap /
  correlation_matrix / signal_radar 原先直接 df[列] 取值，缺列即抛 KeyError 炸页；
  现统一返回友好空图。
"""
import pandas as pd
import plotly.graph_objects as go

import modules.visualizer as V


def _bt_df():
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "cumulative_return": [0.0, 1.5, 2.1],
        "drawdown": [0.0, -0.5, -0.3],
    })


def _portfolio_df():
    return pd.DataFrame({
        "name": ["A", "B"],
        "pnl_pct": [3.2, -1.1],
    })


def _sector_df():
    return pd.DataFrame({
        "sector": ["银行", "白酒"],
        "change_pct": [1.2, -0.8],
    })


def test_empty_figure_basic():
    fig = V.empty_figure("标题", "无数据")
    assert isinstance(fig, go.Figure)
    assert fig.layout.height == 400


def test_empty_kline_figure_delegates():
    fig = V._empty_kline_figure("K", "无K线")
    assert isinstance(fig, go.Figure)
    assert fig.layout.height == 550


# ── 各图表缺列兜底 ────────────────────────────────────────
def test_backtest_curve_missing_cols():
    fig = V.Visualizer.backtest_curve(pd.DataFrame({"x": [1]}))
    assert isinstance(fig, go.Figure)


def test_backtest_curve_none():
    fig = V.Visualizer.backtest_curve(None)
    assert isinstance(fig, go.Figure)


def test_backtest_curve_valid_has_trace():
    fig = V.Visualizer.backtest_curve(_bt_df())
    assert len(fig.data) >= 1


def test_drawdown_curve_missing_cols():
    fig = V.Visualizer.drawdown_curve(pd.DataFrame({"x": [1]}))
    assert isinstance(fig, go.Figure)


def test_drawdown_curve_valid():
    fig = V.Visualizer.drawdown_curve(_bt_df())
    assert len(fig.data) == 1


def test_portfolio_pnl_missing_cols():
    fig = V.Visualizer.portfolio_pnl(pd.DataFrame({"x": [1]}))
    assert isinstance(fig, go.Figure)


def test_portfolio_pnl_valid():
    fig = V.Visualizer.portfolio_pnl(_portfolio_df())
    assert len(fig.data) == 1


def test_sector_heatmap_missing_cols():
    fig = V.Visualizer.sector_heatmap(pd.DataFrame({"x": [1]}))
    assert isinstance(fig, go.Figure)


def test_sector_heatmap_valid():
    fig = V.Visualizer.sector_heatmap(_sector_df())
    assert len(fig.data) == 1


def test_correlation_matrix_no_valid():
    fig = V.Visualizer.correlation_matrix({"600519": pd.DataFrame({"close": [1, 2]})})  # 仅 1 列
    assert isinstance(fig, go.Figure)
    fig2 = V.Visualizer.correlation_matrix({})
    assert isinstance(fig2, go.Figure)
    # 非 DataFrame 输入不崩溃
    fig3 = V.Visualizer.correlation_matrix({"x": "not-a-df"})
    assert isinstance(fig3, go.Figure)


def test_correlation_matrix_valid():
    daily = {
        "600519": pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                                "close": [100, 102, 101]}),
        "000858": pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                                "close": [50, 51, 52]}),
    }
    fig = V.Visualizer.correlation_matrix(daily)
    assert isinstance(fig, go.Figure)
    assert fig.data  # imshow 产出热力图


def test_signal_radar_invalid():
    fig = V.Visualizer.signal_radar(None)
    assert isinstance(fig, go.Figure)
    fig2 = V.Visualizer.signal_radar({"price_score": 70})
    assert isinstance(fig2, go.Figure)
    assert fig2.data
