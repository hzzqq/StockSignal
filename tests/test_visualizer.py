"""
tests/test_visualizer.py
=========================
Visualizer 纯逻辑测试 + 可变默认参数回归守护。

守护点：kline_legend_html(ma_windows=[5,10,20]) / candlestick(ma_windows=[5,20,60])
默认参数为 None（每次调用新建列表），杜绝模块级共享可变列表被污染。
"""
import inspect

import pandas as pd
import pytest

import modules.visualizer as viz_mod
from modules.visualizer import Visualizer


def test_kline_legend_default_windows():
    html = Visualizer.kline_legend_html()
    assert "MA5" in html and "MA10" in html and "MA20" in html
    # A 股默认红涨
    assert "#ff4d4f" in html


def test_kline_legend_custom_windows():
    html = Visualizer.kline_legend_html(ma_windows=[3, 7])
    assert "MA3" in html and "MA7" in html
    assert "MA5" not in html


def test_kline_legend_default_is_none_not_shared_list():
    sig = inspect.signature(Visualizer.kline_legend_html)
    assert sig.parameters["ma_windows"].default is None


def _kline_df():
    import numpy as np
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    rng = np.random.default_rng(0)
    close = 100 + rng.random(30).cumsum()
    return pd.DataFrame({
        "date": dates,
        "open": close + rng.normal(0, 0.5, 30),
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": rng.integers(1000, 5000, 30),
    })


def test_candlestick_returns_figure_default_windows():
    import plotly.graph_objects as go
    fig = Visualizer.candlestick(_kline_df())
    assert isinstance(fig, go.Figure)
    # 默认三条均线 → 至少有 1 根 K 线 + 成交量 + 3 条 MA trace
    assert len(fig.data) >= 5


def test_candlestick_custom_windows():
    import plotly.graph_objects as go
    fig = Visualizer.candlestick(_kline_df(), ma_windows=[10])
    assert isinstance(fig, go.Figure)


def test_candlestick_default_is_none_not_shared_list():
    sig = inspect.signature(Visualizer.candlestick)
    assert sig.parameters["ma_windows"].default is None


def test_candlestick_uses_real_date_axis():
    """回归：K 线 X 轴必须为真实日期轴（type='date'），周末/节假日留白，而非 category。"""
    fig = Visualizer.candlestick(_kline_df())
    assert fig.layout.xaxis.type == "date", "X 轴应为真实日期轴"
    assert fig.layout.xaxis2 is None or fig.layout.xaxis2.type == "date"


def test_candlestick_empty_df_returns_figure():
    import plotly.graph_objects as go
    fig = Visualizer.candlestick(None)
    assert isinstance(fig, go.Figure)
