# -*- coding: utf-8 -*-
"""visualizer_charts — 板块热力图 / 相关性矩阵 / 信号雷达（visualizer 拆分·分析域）。

零业务逻辑改动：源码自 modules/visualizer.py 机械提取（dedent + 去 @staticmethod）。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from modules.colors import DOWN_COLOR, UP_COLOR
from modules.visualizer_core import (
    SF_BORDER,
    SF_GRID,
    SF_TXT,
    SF_TXT2,
    _is_dark,
    empty_figure,
)

logger = logging.getLogger(__name__)


def sector_heatmap(sector_df,         title="行业板块涨跌热力图"):
    """
    生成行业板块涨跌幅热力图。
    :param sector_df: DataFrame[sector, change_pct]
    :return: plotly Figure
    """
    if (not isinstance(sector_df, pd.DataFrame)
            or "sector" not in sector_df.columns
            or "change_pct" not in sector_df.columns):
        return empty_figure(title, "板块数据缺失：需要 sector / change_pct 列")
    df = sector_df.copy()
    df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0)

    # 按涨跌幅排序
    df = df.sort_values("change_pct", ascending=False)

    colors = np.where(df["change_pct"] > 0, UP_COLOR, DOWN_COLOR)
    fig = go.Figure(go.Bar(
        x=df["change_pct"], y=df["sector"],
        orientation="h",
        marker_color=colors,
        text=df["change_pct"].round(2).astype(str) + "%",
        textposition="outside"
    ))
    if _is_dark():
        fig.update_layout(
            title={"text": title, "font": {"color": SF_TXT, "size": 14}},
            template="starfield_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": SF_TXT2},
            height=max(400, len(df) * 28),
            margin=dict(l=120, r=60, t=50, b=40),
            xaxis_title="涨跌幅 (%)", yaxis_title="",
        )
    else:
        fig.update_layout(
            title=title, template="plotly_white",
            height=max(400, len(df) * 28),
            margin=dict(l=120, r=60, t=50, b=40),
            xaxis_title="涨跌幅 (%)", yaxis_title=""
        )
    return fig

def correlation_matrix(daily_dict, method="pearson"):
    """
    生成多只股票收益率相关性矩阵热力图。
    :param daily_dict: {"600519": df, "000858": df, ...}
    :param method: pearson / spearman
    :return: plotly Figure
    """
    # 构建收益率 DataFrame（仅接受有效 DataFrame 且含 close、长度 >1）
    returns = {}
    for ticker, df in daily_dict.items():
        if (isinstance(df, pd.DataFrame) and "date" in df.columns
                and "close" in df.columns and len(df) > 1):
            returns[ticker] = df.set_index("date")["close"].pct_change()
    if not returns:
        return empty_figure("个股收益率相关性矩阵", "无可用收益率数据")
    ret_df = pd.DataFrame(returns).dropna()
    if ret_df.shape[1] < 2:
        return empty_figure("个股收益率相关性矩阵", "标的不足，无法计算相关性")
    corr = ret_df.corr(method=method)

    fig = px.imshow(
        corr, text_auto=".2f",
        color_continuous_scale="RdYlGn_r",
        zmin=-1, zmax=1,
        title="个股收益率相关性矩阵"
    )
    if _is_dark():
        fig.update_layout(
            template="starfield_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": SF_TXT2},
            height=500,
            margin=dict(l=60, r=40, t=50, b=40),
        )
    else:
        fig.update_layout(
            template="plotly_white", height=500,
            margin=dict(l=60, r=40, t=50, b=40)
        )
    return fig

def signal_radar(scores,         title="信号评分雷达图"):
    """
    生成信号评分雷达图。
    :param scores: {"price_score": 72, "event_score": 85, "macro_score": 60}
    :return: plotly Figure
    """
    if not isinstance(scores, dict):
        return empty_figure(title, "信号评分数据缺失")
    categories = ["价格信号", "事件信号", "宏观信号"]
    values = [scores.get("price_score", 0),
              scores.get("event_score", 0),
              scores.get("macro_score", 0)]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill="toself",
        name="得分",
        line=dict(color="#667eea", width=2),
        fillcolor="rgba(102, 126, 234, 0.2)"
    ))
    if _is_dark():
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True, range=[0, 100],
                    gridcolor=SF_GRID, linecolor=SF_BORDER,
                    tickfont={"color": SF_TXT2},
                    angle=90,
                ),
                angularaxis=dict(
                    gridcolor=SF_GRID, linecolor=SF_BORDER,
                    tickfont={"color": SF_TXT2},
                ),
                bgcolor="rgba(0,0,0,0)",
            ),
            title={"text": title, "font": {"color": SF_TXT, "size": 14}},
            template="starfield_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": SF_TXT2},
            height=400, margin=dict(l=40, r=40, t=50, b=40)
        )
    else:
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title=title, template="plotly_white",
            height=400, margin=dict(l=40, r=40, t=50, b=40)
        )
    return fig
