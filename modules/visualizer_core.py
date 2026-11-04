# -*- coding: utf-8 -*-  # noqa: UP009
"""visualizer_core — 图表令牌 / 暗色模板 / 布局与空态基元（visualizer 拆分·纯函数层）。

零业务逻辑改动：源码自 modules/visualizer.py 机械提取（dedent + 去 @staticmethod），
仅做职责归位。对外调用方继续 `from modules.visualizer import ...`（主入口 re-export）。
"""
from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import numpy as np  # noqa: F401
import pandas as pd  # noqa: F401
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# 涨跌配色（A股：红涨绿跌）统一从 modules.colors 引入，避免重复定义
from modules.colors import DOWN_COLOR, UP_COLOR, hex_to_rgba  # noqa: F401
from modules.perf import downsample  # noqa: F401

logger = logging.getLogger(__name__)

# 确保自定义暗色模板存在：若页面未经过 ui_theme.apply_theme，visualizer 自己兜底注册
# 使用 plotly_dark 作为基底色，避免 "Invalid value of type 'builtins.str'" 的 template 异常
if "starfield_dark" not in pio.templates:
    try:
        pio.templates["starfield_dark"] = go.layout.Template(layout=pio.templates["plotly_dark"].layout)
    except Exception as e:
        logger.warning(f"[visualizer] 处理异常: {e}")


# 星辰暗色图表令牌
SF_TXT = "#e2e8f0"
SF_TXT2 = "#94a3b8"
SF_GRID = "#23233c"
SF_BORDER = "#2d2d44"
SF_CARD = "#1a1a2e"
SF_BG = "#0f0f23"

# 均线配色循环（截图风格：MA5 红 / MA10 橙 / MA20 蓝 / 后续依次）
MA_COLORS = ["#ff4d4f", "#ffa502", "#667eea", "#00d4aa", "#764ba2"]

# 中文字体配置
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def _ma_color(i: int) -> str:
    return MA_COLORS[i % len(MA_COLORS)]

def kline_legend_html(ma_windows=None, up_color="#ff4d4f",
                    down_color="#00d486", ma_colors=None):
    """生成截图风格的自定义图例 HTML（K线 / MA / 成交量）。
    up_color/down_color：涨跌柱配色（默认 A 股红涨绿跌）。
    ma_colors：均线配色列表，默认 MA_COLORS。"""
    if ma_windows is None:
        ma_windows = [5, 10, 20]
    if ma_colors is None:
        ma_colors = MA_COLORS
    parts = [
        '<span style="display:inline-flex;align-items:center;gap:3px;">',
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:var(--ss-radius-xs);background:{up_color};"></span>',
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:var(--ss-radius-xs);background:{down_color};margin-left:-2px;"></span>',
        '<span style="font-size:12px;color:#94a3b8;">K线(涨/跌)</span></span>',
    ]
    for i, w in enumerate(ma_windows):
        color = ma_colors[i % len(ma_colors)]
        parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:4px;">'
            f'<span style="display:inline-block;width:18px;height:2px;background:{color};"></span>'
            f'<span style="font-size:12px;color:#94a3b8;">MA{w}</span></span>'
        )
    parts.append(
        '<span style="display:inline-flex;align-items:center;gap:4px;">'
        f'<span style="display:inline-block;width:18px;height:8px;background:{up_color};"></span>'
        '<span style="font-size:12px;color:#94a3b8;">成交量</span></span>'
    )
    return '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:6px 0 10px;">' + ''.join(parts) + '</div>'

def _is_dark() -> bool:
    """返回当前是否为暗色模式（含「个股分析」页面强制暗色作用域）。"""
    try:
        from modules.ui_theme import _theme_is_dark
        return _theme_is_dark()
    except Exception as e:
        logger.warning(f"[visualizer] 处理异常: {e}")
        try:
            return st.session_state.get("theme_mode", "dark") == "dark"
        except Exception as e:
            logger.warning(f"[visualizer] 处理异常: {e}")
            return False

def _plotly_layout_kwargs(title: str = "", height: int = 400) -> dict:
    """根据当前主题返回 Plotly layout 参数字典。"""
    if _is_dark():
        return {
            "title": {"text": title, "font": {"color": SF_TXT, "size": 14}} if title else None,
            "template": "starfield_dark",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": SF_TXT2, "family": "system-ui, -apple-system, 'PingFang SC', sans-serif"},
            "height": height,
            "margin": dict(l=40, r=20, t=50, b=40),
        }
    return {
        "title": title,
        "template": "plotly_white",
        "paper_bgcolor": "#FFFFFF",
        "plot_bgcolor": "#FFFFFF",
        "height": height,
        "margin": dict(l=40, r=20, t=50, b=40),
    }

def empty_figure(title: str = "", msg: str = "暂无数据", height: int = 400) -> "go.Figure":  # noqa: UP037
    """通用空 / 异常数据兜底图（新能力，R3 DRY）：居中显示友好提示，不报错。

    原 _empty_kline_figure 仅服务 K 线；这里抽出统一入口，供回测/回撤/持仓/板块/
    相关性等所有图表在输入缺失或畸形时复用，避免各自重复兜底逻辑、也避免 KeyError
    炸页（R2 隐式 bug：这些函数原先直接 df[列] 取值，缺列即抛异常）。
    """
    fig = go.Figure()
    fig.update_layout(**_plotly_layout_kwargs(title=title, height=height))
    fig.add_annotation(
        text=msg,
        x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=16, color=SF_TXT2 if _is_dark() else "#6B7280"),
    )
    return fig

def _empty_kline_figure(title: str, msg: str) -> "go.Figure":  # noqa: UP037
    """空 / 异常数据的优雅兜底图：居中显示友好提示，不报错。"""
    return empty_figure(title, msg, height=550)
