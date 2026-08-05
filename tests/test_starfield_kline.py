"""锁定 starfield_theme 的 K 线交互规范契约（防回归）。

确保全站 K 线图统一的「十字光标 + 隐藏工具栏图标 + 暗色模板」交互规范不被破坏：
- KLINE_CHART_CONFIG：displayModeBar=hover、scrollZoom、移除 lasso/select
- kline_plotly：返回含 Candlestick 的 Figure，且默认开启 hovermode=x + 十字光标 spikes
- inject_plotly_dark：注册 starfield_dark 模板并设为默认
"""
import plotly.graph_objects as go

import modules.starfield_theme as sf


def test_kline_chart_config_contract():
    c = sf.KLINE_CHART_CONFIG
    assert c["displayModeBar"] == "hover"          # 默认隐藏，悬停才显示
    assert c["displaylogo"] is False
    assert c["scrollZoom"] is True
    assert "lasso2d" in c["modeBarButtonsToRemove"]
    assert "select2d" in c["modeBarButtonsToRemove"]


def test_kline_plotly_structure():
    fig = sf.kline_plotly(
        dates=["2026-01-01", "2026-01-02"],
        opens=[1, 2], highs=[1.5, 2.5], lows=[0.5, 1.5],
        closes=[1.2, 2.2], volumes=[100, 200], title="测试K线",
    )
    assert isinstance(fig, go.Figure)
    kinds = {t.type for t in fig.data}
    assert "candlestick" in kinds
    # 十字光标：悬停显示垂直引线 + OHLC 数值
    assert fig.layout.hovermode == "x"
    assert fig.layout.xaxis.showspikes is True
    assert fig.layout.yaxis.showspikes is True
    # 量柱用次坐标轴
    assert fig.layout.yaxis2 is not None


def test_inject_plotly_dark_registers_template():
    import plotly.io as pio
    sf.inject_plotly_dark()
    assert "starfield_dark" in pio.templates
    assert pio.templates.default == "starfield_dark"
