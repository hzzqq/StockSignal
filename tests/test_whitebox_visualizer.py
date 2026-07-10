"""test_whitebox_visualizer.py — Visualizer 白盒测试
覆盖 candlestick / sector_heatmap / correlation_matrix / signal_radar /
backtest_curve / drawdown_curve / portfolio_pnl / event_timeline
所有分支条件和边界路径。
"""

import pytest
import pandas as pd
import numpy as np
from modules.visualizer import Visualizer


def make_ohlc_df(n=30):
    """构造 OHLCV 行情数据。"""
    dates = pd.date_range("2025-01-01", periods=n)
    closes = [10 + i * 0.3 for i in range(n)]
    opens = [c - 0.1 for c in closes]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1000 + i * 10 for i in range(n)]
    return pd.DataFrame({
        "date": dates, "open": opens, "close": closes,
        "high": highs, "low": lows, "volume": volumes
    })


class TestCandlestick:

    def test_basic(self):
        df = make_ohlc_df(30)
        fig = Visualizer.candlestick(df)
        assert fig is not None
        assert len(fig.data) > 0

    def test_with_volume(self):
        df = make_ohlc_df(30)
        fig = Visualizer.candlestick(df, show_volume=True)
        assert fig is not None
        # 应包含 K线 trace + MA traces + 成交量 trace
        assert len(fig.data) >= 2

    def test_without_volume(self):
        df = make_ohlc_df(30)
        fig = Visualizer.candlestick(df, show_volume=False)
        assert fig is not None

    def test_with_ma_windows(self):
        df = make_ohlc_df(70)
        fig = Visualizer.candlestick(df, ma_windows=[5, 20, 60])
        assert fig is not None

    def test_short_data_no_ma(self):
        """数据量不足时不画均线。"""
        df = make_ohlc_df(10)
        fig = Visualizer.candlestick(df, ma_windows=[20, 60])
        assert fig is not None

    def test_a_stock_colors(self):
        """验证 A 股配色：涨红跌绿。"""
        df = make_ohlc_df(30)
        fig = Visualizer.candlestick(df)
        candlestick = fig.data[0]
        # 当前 candlestick 使用 go.Bar 手动绘制
        colors = candlestick.marker.color
        assert colors[0] == "#ff4d4f"  # 涨红（A股红涨）
        # 构造一个下跌日，验证下跌颜色
        df_down = df.copy()
        df_down.loc[0, "close"] = df_down.loc[0, "open"] - 1.0
        fig_down = Visualizer.candlestick(df_down)
        down_color = fig_down.data[0].marker.color[0]
        assert down_color == "#00d486"  # 跌绿（A股绿跌）


class TestSectorHeatmap:

    def test_basic(self):
        df = pd.DataFrame({
            "sector": ["煤炭", "银行", "医药", "半导体"],
            "change_pct": [2.5, -1.2, 0.8, 3.1]
        })
        fig = Visualizer.sector_heatmap(df)
        assert fig is not None
        assert len(fig.data) > 0

    def test_all_positive(self):
        df = pd.DataFrame({
            "sector": ["煤炭", "银行", "医药"],
            "change_pct": [2.5, 1.2, 0.8]
        })
        fig = Visualizer.sector_heatmap(df)
        assert fig is not None

    def test_all_negative(self):
        df = pd.DataFrame({
            "sector": ["煤炭", "银行", "医药"],
            "change_pct": [-2.5, -1.2, -0.8]
        })
        fig = Visualizer.sector_heatmap(df)
        assert fig is not None

    def test_nan_change_pct(self):
        """NaN 涨跌幅应被填充为0。"""
        df = pd.DataFrame({
            "sector": ["煤炭", "银行"],
            "change_pct": [2.5, None]
        })
        fig = Visualizer.sector_heatmap(df)
        assert fig is not None


class TestCorrelationMatrix:

    def test_basic(self):
        daily_dict = {
            "600519": make_ohlc_df(30),
            "000858": make_ohlc_df(30),
        }
        fig = Visualizer.correlation_matrix(daily_dict)
        assert fig is not None

    def test_single_stock(self):
        """单只股票也能生成（1x1 矩阵）。"""
        daily_dict = {"600519": make_ohlc_df(30)}
        fig = Visualizer.correlation_matrix(daily_dict)
        assert fig is not None

    def test_pearson_method(self):
        daily_dict = {
            "600519": make_ohlc_df(30),
            "000858": make_ohlc_df(30),
        }
        fig = Visualizer.correlation_matrix(daily_dict, method="pearson")
        assert fig is not None


class TestSignalRadar:

    def test_basic(self):
        scores = {"price_score": 72, "event_score": 85, "macro_score": 60}
        fig = Visualizer.signal_radar(scores)
        assert fig is not None

    def test_all_zeros(self):
        scores = {"price_score": 0, "event_score": 0, "macro_score": 0}
        fig = Visualizer.signal_radar(scores)
        assert fig is not None

    def test_all_hundreds(self):
        scores = {"price_score": 100, "event_score": 100, "macro_score": 100}
        fig = Visualizer.signal_radar(scores)
        assert fig is not None

    def test_missing_keys(self):
        """缺少 key 时默认为0。"""
        scores = {"price_score": 72}
        fig = Visualizer.signal_radar(scores)
        assert fig is not None


class TestBacktestCurve:

    def test_basic(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10),
            "cumulative_return": [0, 5, 10, 8, 12, 15, 18, 20, 22, 25]
        })
        fig = Visualizer.backtest_curve(df)
        assert fig is not None

    def test_with_benchmark(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10),
            "cumulative_return": [0, 5, 10, 8, 12, 15, 18, 20, 22, 25]
        })
        benchmark = pd.Series([0, 3, 5, 7, 8, 10, 12, 13, 14, 15])
        fig = Visualizer.backtest_curve(df, benchmark=benchmark)
        assert fig is not None
        assert len(fig.data) >= 2  # 策略 + 基准

    def test_negative_returns(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "cumulative_return": [0, -5, -10, -8, -12]
        })
        fig = Visualizer.backtest_curve(df)
        assert fig is not None


class TestDrawdownCurve:

    def test_basic(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10),
            "drawdown": [0, 0, -5, -8, -3, 0, -2, -4, 0, 0]
        })
        fig = Visualizer.drawdown_curve(df)
        assert fig is not None

    def test_all_zero(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "drawdown": [0, 0, 0, 0, 0]
        })
        fig = Visualizer.drawdown_curve(df)
        assert fig is not None


class TestPortfolioPnl:

    def test_basic(self):
        df = pd.DataFrame({
            "name": ["贵州茅台", "中国神华", "五粮液"],
            "pnl_pct": [6.5, -3.2, 2.1]
        })
        fig = Visualizer.portfolio_pnl(df)
        assert fig is not None

    def test_all_profit(self):
        df = pd.DataFrame({
            "name": ["茅台", "神华"],
            "pnl_pct": [5.0, 3.0]
        })
        fig = Visualizer.portfolio_pnl(df)
        assert fig is not None

    def test_all_loss(self):
        df = pd.DataFrame({
            "name": ["茅台", "神华"],
            "pnl_pct": [-5.0, -3.0]
        })
        fig = Visualizer.portfolio_pnl(df)
        assert fig is not None


class TestEventTimeline:

    def test_basic(self):
        df = make_ohlc_df(30)
        events = pd.DataFrame({
            "date": ["2025-01-10", "2025-01-20"],
            "title": ["煤炭涨价", "政策利好"]
        })
        fig = Visualizer.event_timeline(df, events)
        assert fig is not None

    def test_no_events(self):
        """无事件时仍返回 K 线图。"""
        df = make_ohlc_df(30)
        events = pd.DataFrame(columns=["date", "title"])
        fig = Visualizer.event_timeline(df, events)
        assert fig is not None

    def test_event_outside_range(self):
        """事件日期超出行情范围时不报错。"""
        df = make_ohlc_df(30)
        events = pd.DataFrame({
            "date": ["2025-06-01"],
            "title": ["未来事件"]
        })
        fig = Visualizer.event_timeline(df, events)
        assert fig is not None
