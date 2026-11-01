# -*- coding: utf-8 -*-
"""visualizer_curves — 回测曲线 / 回撤曲线 / 组合盈亏（visualizer 拆分·绩效域）。

零业务逻辑改动：源码自 modules/visualizer.py 机械提取（dedent + 去 @staticmethod）。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from modules.colors import DOWN_COLOR, UP_COLOR
from modules.perf import downsample
from modules.visualizer_core import (
    SF_BORDER,
    SF_GRID,
    SF_TXT,
    SF_TXT2,
    _is_dark,
    empty_figure,
)

logger = logging.getLogger(__name__)


def backtest_curve(result_df, benchmark=None,         title="策略回测收益曲线"):
    """
    绘制回测累计收益曲线。
    :param result_df: 回测结果，需含 date, cumulative_return
    :param benchmark: 基准收益 Series（可选）
    :return: plotly Figure
    """
    if (not isinstance(result_df, pd.DataFrame)
            or "date" not in result_df.columns
            or "cumulative_return" not in result_df.columns):
        return empty_figure(title, "回测数据缺失：需要 date / cumulative_return 列")
    # 超长回测区间（如日线多年）做均匀降采样，降低 Plotly JSON 体积与渲染开销
    combined = result_df[["date", "cumulative_return"]].copy()
    if benchmark is not None:
        try:
            combined["__bench__"] = np.asarray(benchmark)
        except Exception:
            benchmark = None
    combined = downsample(combined, max_points=600)
    result_df = combined
    benchmark = combined.get("__bench__") if "__bench__" in combined.columns else None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result_df["date"], y=result_df["cumulative_return"],
        mode="lines", name="策略收益",
        line=dict(color=UP_COLOR, width=2)
    ))
    if benchmark is not None:
        fig.add_trace(go.Scatter(
            x=result_df["date"], y=benchmark,
            mode="lines", name="基准收益",
            line=dict(color="#94a3b8", width=1.5, dash="dash")
        ))
    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=0.5)
    if _is_dark():
        fig.update_layout(
            title={"text": title, "font": {"color": SF_TXT, "size": 14}},
            template="starfield_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": SF_TXT2},
            xaxis_title="日期", yaxis_title="累计收益率 (%)",
            height=450, margin=dict(l=50, r=20, t=50, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                       tickfont={"color": SF_TXT2}),
            yaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                       tickfont={"color": SF_TXT2}),
        )
    else:
        fig.update_layout(
            title=title, template="plotly_white",
            xaxis_title="日期", yaxis_title="累计收益率 (%)",
            height=450, margin=dict(l=50, r=20, t=50, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
    return fig

def drawdown_curve(result_df,         title="最大回撤曲线"):
    """
    绘制回撤曲线。
    :param result_df: 需含 date, drawdown 列
    """
    if (not isinstance(result_df, pd.DataFrame)
            or "date" not in result_df.columns
            or "drawdown" not in result_df.columns):
        return empty_figure(title, "回测数据缺失：需要 date / drawdown 列")
    result_df = downsample(result_df, max_points=600)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result_df["date"], y=result_df["drawdown"],
        mode="lines", name="回撤",
        line=dict(color=DOWN_COLOR, width=1.5),
        fill="tozeroy", fillcolor="rgba(0, 212, 134, 0.15)"
    ))
    if _is_dark():
        fig.update_layout(
            title={"text": title, "font": {"color": SF_TXT, "size": 14}},
            template="starfield_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": SF_TXT2},
            xaxis_title="日期", yaxis_title="回撤 (%)",
            height=300, margin=dict(l=50, r=20, t=50, b=40),
            xaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                       tickfont={"color": SF_TXT2}),
            yaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                       tickfont={"color": SF_TXT2}),
        )
    else:
        fig.update_layout(
            title=title, template="plotly_white",
            xaxis_title="日期", yaxis_title="回撤 (%)",
            height=300, margin=dict(l=50, r=20, t=50, b=40)
        )
    return fig

def portfolio_pnl(portfolio_df,         title="持仓盈亏一览"):
    """
    持仓盈亏柱状图。
    :param portfolio_df: 需含 ticker, name, pnl_pct 列
    """
    if (not isinstance(portfolio_df, pd.DataFrame)
            or "name" not in portfolio_df.columns
            or "pnl_pct" not in portfolio_df.columns):
        return empty_figure(title, "持仓数据缺失：需要 name / pnl_pct 列")
    df = portfolio_df.copy()
    colors = np.where(df["pnl_pct"] >= 0, UP_COLOR, DOWN_COLOR)
    fig = go.Figure(go.Bar(
        x=df["name"], y=df["pnl_pct"],
        marker_color=colors,
        text=df["pnl_pct"].round(2).astype(str) + "%",
        textposition="outside"
    ))
    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=0.5)
    if _is_dark():
        fig.update_layout(
            title={"text": title, "font": {"color": SF_TXT, "size": 14}},
            template="starfield_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": SF_TXT2},
            xaxis_title="", yaxis_title="盈亏 (%)",
            height=400, margin=dict(l=50, r=20, t=50, b=40),
            xaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                       tickfont={"color": SF_TXT2}),
            yaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                       tickfont={"color": SF_TXT2}),
        )
    else:
        fig.update_layout(
            title=title, template="plotly_white",
            xaxis_title="", yaxis_title="盈亏 (%)",
            height=400, margin=dict(l=50, r=20, t=50, b=40)
        )
    return fig
