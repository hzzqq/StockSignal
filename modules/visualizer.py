# -*- coding: utf-8 -*-
"""可视化模块（拆分后主入口：对外 API 零变化的 re-export 层 + Visualizer 命名空间壳）。

R-05 续（2026-11-02）：原 1406 行单文件按职责拆为
- ``visualizer_core``  ：颜色令牌 / 暗色模板注册 / 布局与空态基元 / 均线图例
- ``visualizer_kline`` ：``candlestick`` / ``intraday``
- ``visualizer_charts``：``sector_heatmap`` / ``correlation_matrix`` / ``signal_radar``
- ``visualizer_curves``：``backtest_curve`` / ``drawdown_curve`` / ``portfolio_pnl``
- ``visualizer_events``：``event_timeline``

既有调用零改动：``from modules.visualizer import Visualizer, SF_TXT, _is_dark, UP_COLOR``
以及 ``Visualizer.candlestick(...)`` 等静态方法调用全部保持可用（下方 staticmethod 挂载）。
基于 Plotly + Matplotlib，适配 Streamlit 展示。
"""
from __future__ import annotations

from modules.visualizer_core import (
    DOWN_COLOR,
    SF_BG,
    SF_BORDER,
    SF_CARD,
    SF_GRID,
    SF_TXT,
    SF_TXT2,
    UP_COLOR,
    _empty_kline_figure,
    _is_dark,
    _ma_color,
    _plotly_layout_kwargs,
    downsample,
    empty_figure,
    hex_to_rgba,
    kline_legend_html,
)
from modules.visualizer_core import MA_COLORS as _MA_COLORS_DEFAULT
from modules.visualizer_kline import candlestick, intraday
from modules.visualizer_charts import correlation_matrix, sector_heatmap, signal_radar
from modules.visualizer_curves import backtest_curve, drawdown_curve, portfolio_pnl
from modules.visualizer_events import event_timeline

MA_COLORS = _MA_COLORS_DEFAULT

__all__ = [
    "Visualizer",
    "SF_TXT", "SF_TXT2", "SF_GRID", "SF_BORDER", "SF_CARD", "SF_BG",
    "UP_COLOR", "DOWN_COLOR", "hex_to_rgba", "downsample",
    "empty_figure", "kline_legend_html", "MA_COLORS",
    "candlestick", "intraday", "sector_heatmap", "correlation_matrix",
    "signal_radar", "backtest_curve", "drawdown_curve", "portfolio_pnl",
    "event_timeline",
]


class Visualizer:
    """图表生成器（拆分后为命名空间壳，实现见 ``modules/visualizer_*``）。

    V4: 手动Bar+Scatter绘制K线，彻底避免Candlestick内部日期逻辑。
    """
    _VERSION = "v4-manual-bar"
    MA_COLORS = _MA_COLORS_DEFAULT


# 静态方法兼容性挂载：`Visualizer.xxx(...)` 等既有调用零改动
Visualizer._ma_color = staticmethod(_ma_color)
Visualizer.kline_legend_html = staticmethod(kline_legend_html)
Visualizer.candlestick = staticmethod(candlestick)
Visualizer.intraday = staticmethod(intraday)
Visualizer.sector_heatmap = staticmethod(sector_heatmap)
Visualizer.correlation_matrix = staticmethod(correlation_matrix)
Visualizer.signal_radar = staticmethod(signal_radar)
Visualizer.backtest_curve = staticmethod(backtest_curve)
Visualizer.drawdown_curve = staticmethod(drawdown_curve)
Visualizer.portfolio_pnl = staticmethod(portfolio_pnl)
Visualizer.event_timeline = staticmethod(event_timeline)
