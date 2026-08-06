"""
tests/test_starfield_theme.py
===========================
锁定 modules/starfield_theme.py 的纯函数与注入行为（项目内零测试覆盖，446 行）。

重点验证：
  - kline_option：纯函数，构建 ECharts K线 option；涨跌色必须走 UP_COLOR/DOWN_COLOR
    （A股红涨绿跌，这是全站 K线配色的单一来源，回归会静默破坏配色）
  - vs_box：verdict_kind 映射为 b/o class
  - KLINE_CHART_CONFIG / PLOTLY_DARK：暗色模板关键字段
  - inject_theme / inject_plotly_dark：注入不抛异常（plotly 缺失时静默跳过）
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
import modules.starfield_theme as sf
from modules.colors import UP_COLOR, DOWN_COLOR


def _stub_st(monkeypatch):
    calls = {}

    def fake_markdown(*a, **k):
        calls.setdefault("md", []).append(a[0] if a else "")

    def fake_html(*a, **k):
        calls.setdefault("html", []).append(a[0] if a else "")

    monkeypatch.setattr(st, "markdown", fake_markdown)
    monkeypatch.setattr(components, "html", fake_html)
    return calls


def test_kline_option_uses_up_down_colors():
    dates = ["06-01", "06-02"]
    ohlc = [[10, 10.6, 9.8, 10.8], [10.6, 10.2, 10.0, 10.9]]
    opt = sf.kline_option(dates, ohlc, volumes=[120, 98])
    # 关键：K线 itemStyle 涨跌色来自全局常量（红涨绿跌）
    kline = opt["series"][0]
    assert kline["type"] == "candlestick"
    assert kline["itemStyle"]["color"] == UP_COLOR      # 阳线（涨）
    assert kline["itemStyle"]["color0"] == DOWN_COLOR    # 阴线（跌）
    assert kline["itemStyle"]["borderColor"] == UP_COLOR
    assert kline["itemStyle"]["borderColor0"] == DOWN_COLOR
    # 成交量副图
    vol = opt["series"][1]
    assert vol["type"] == "bar"
    assert vol["data"] == [120, 98]


def test_kline_option_no_volumes_defaults_empty():
    dates = ["06-01"]
    ohlc = [[10, 10.6, 9.8, 10.8]]
    opt = sf.kline_option(dates, ohlc)
    assert opt["series"][1]["data"] == []
    # xAxis 两段数据一致
    assert opt["xAxis"][0]["data"] == dates
    assert opt["xAxis"][1]["data"] == dates


def test_kline_option_transparent_background():
    opt = sf.kline_option(["06-01"], [[10, 10.6, 9.8, 10.8]])
    assert opt["backgroundColor"] == "transparent"
    assert opt["animation"] is False


def test_vs_box_verdict_kind_mapping():
    html_b = sf.vs_box("标题B", "看多", "b", ["点1", "点2"])
    assert 'class="sf-verdict b"' in html_b
    assert "标题B" in html_b and "看多" in html_b
    assert "<li>点1</li>" in html_b and "<li>点2</li>" in html_b

    html_o = sf.vs_box("标题O", "观望", "anything-else", ["x"])
    assert 'class="sf-verdict o"' in html_o


def test_kline_chart_config_dark_toolbar():
    cfg = sf.KLINE_CHART_CONFIG
    assert cfg["displayModeBar"] == "hover"   # 默认隐藏，悬停才显示
    assert cfg["displaylogo"] is False
    assert "lasso2d" in cfg["modeBarButtonsToRemove"]
    assert "select2d" in cfg["modeBarButtonsToRemove"]


def test_plotly_dark_template_fields():
    dark = sf.PLOTLY_DARK
    assert dark["paper_bgcolor"] == "rgba(0,0,0,0)"
    assert dark["plot_bgcolor"] == "rgba(0,0,0,0)"
    assert dark["font"]["color"] == "#94a3b8"


def test_inject_theme_injects_css(monkeypatch):
    calls = _stub_st(monkeypatch)
    sf.inject_theme()
    assert calls.get("md"), "未注入 CSS"
    assert ":root" in calls["md"][0]


def test_inject_plotly_dark_does_not_raise(monkeypatch):
    _stub_st(monkeypatch)
    # 无论是否安装 plotly（缺则被 try/except 吞掉），都不应抛异常
    try:
        sf.inject_plotly_dark()
    except Exception as e:  # pragma: no cover
        raise AssertionError(f"inject_plotly_dark 不应抛异常: {e}")
