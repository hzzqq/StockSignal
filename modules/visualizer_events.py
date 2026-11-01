# -*- coding: utf-8 -*-
"""visualizer_events — 事件时间轴（visualizer 拆分·事件域）。

零业务逻辑改动：源码自 modules/visualizer.py 机械提取（dedent + 去 @staticmethod）。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.colors import DOWN_COLOR, UP_COLOR
from modules.visualizer_core import (
    SF_BORDER,
    SF_GRID,
    SF_TXT,
    SF_TXT2,
    _is_dark,
)

logger = logging.getLogger(__name__)


def event_timeline(df, events_df, title="事件时间轴", start_idx=0, n_show=60,
                   event_type_col=None, event_title_col="title"):
    """
    在 K 线图上标注事件，支持窗口化浏览、动态 Y 轴范围、事件上下方标注。

    显示逻辑：
    - 每次只显示 [start_idx, start_idx + n_show) 范围内的 K 线，避免整体缩小时
      因价格跨度大而把 K 线压成横线。
    - 价格 Y 轴按可见窗口的 high/low 自动计算合理量程，并根据当前价位自动选择
      不同 padding（低价股用较小 padding，高价股用较大 padding）。
    - 成交量 Y 轴固定从 0 开始，上限取可见窗口最大成交量的 1.1 倍，避免负区间。
    - 事件根据情感类型在 K 线上方（利好）或下方（利空）标注，不遮挡 K 线主体。

    :param df: 行情数据，需含 date, open, close, high, low, volume
    :param events_df: 事件数据，需含 date, title,（可选 type/sentiment）
    :param start_idx: 窗口起始索引
    :param n_show: 窗口显示 K 线数量（默认 60）
    :param event_type_col: 事件类型列名（如 "type" 或 "sentiment"），不填则自动识别
    :param event_title_col: 事件标题列名，默认 "title"
    :return: plotly Figure
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    n = len(df)
    if n == 0:
        fig = go.Figure()
        if _is_dark():
            fig.update_layout(
                title={"text": title, "font": {"color": SF_TXT, "size": 14}},
                template="starfield_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={"color": SF_TXT2},
                height=400,
            )
        else:
            fig.update_layout(title=title, template="plotly_white", height=400)
        return fig

    # 窗口参数安全裁剪
    n_show = max(10, min(int(n_show), n))
    start_idx = max(0, min(int(start_idx), n - n_show))
    end_idx = start_idx + n_show
    visible = df.iloc[start_idx:end_idx].copy().reset_index(drop=True)
    m = len(visible)

    x_idx = list(range(m))
    date_labels = visible["date"].dt.strftime("%m月%d日").tolist()
    date_strs = visible["date"].dt.strftime("%Y-%m-%d").tolist()
    rising = visible["close"].values >= visible["open"].values
    up_color = UP_COLOR
    down_color = DOWN_COLOR

    rows = 2 if "volume" in visible.columns else 1
    row_heights = [0.7, 0.3] if rows == 2 else [1.0]
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.05, row_heights=row_heights,
        subplot_titles=(None, "成交量") if rows == 2 else (title,)
    )

    # ── 手绘 K 线实体（Bar：open→close）──
    fig.add_trace(go.Bar(
        x=x_idx,
        y=np.where(rising,
                   visible["close"].values - visible["open"].values,
                   visible["open"].values - visible["close"].values),
        base=visible["open"].values,
        marker_color=np.where(rising, up_color, down_color),
        width=0.75,
        name="K线",
        customdata=np.stack([date_strs,
                             visible["high"].round(2).values,
                             visible["low"].round(2).values], axis=-1),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "开盘: ¥%{base:.2f}<br>"
            "收盘: ¥%{y:.2f}<br>"
            "最高: ¥%{customdata[1]:.2f}<br>"
            "最低: ¥%{customdata[2]:.2f}<br>"
            "<extra></extra>"
        ),
    ), row=1, col=1)

    # ── 上下影线 ──
    for i in range(m):
        color = up_color if rising[i] else down_color
        # 上影线
        y_top = visible["high"].iloc[i]
        y_bottom = max(visible["open"].iloc[i], visible["close"].iloc[i])
        if y_top > y_bottom + 0.001:
            fig.add_shape(
                type="line", x0=i, y0=y_bottom, x1=i, y1=y_top,
                line=dict(color=color, width=1),
                xref="x", yref="y", row=1, col=1,
            )
        # 下影线
        y_top2 = min(visible["open"].iloc[i], visible["close"].iloc[i])
        y_bottom2 = visible["low"].iloc[i]
        if y_top2 > y_bottom2 + 0.001:
            fig.add_shape(
                type="line", x0=i, y0=y_top2, x1=i, y1=y_bottom2,
                line=dict(color=color, width=1),
                xref="x", yref="y", row=1, col=1,
            )

    # ── 成交量（固定从 0 开始）──
    if rows == 2:
        colors = np.where(rising, up_color, down_color)
        max_vol = visible["volume"].max() if len(visible) > 0 else 1
        max_vol = max(1, max_vol)
        fig.add_trace(go.Bar(
            x=x_idx, y=visible["volume"], name="成交量",
            marker_color=colors, opacity=0.7,
            customdata=date_strs,
            hovertemplate="%{customdata}<br>成交量: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

    # ── 价格 Y 轴量程：按可见数据 + 当前价位动态 padding ──
    min_low = visible["low"].min()
    max_high = visible["high"].max()
    price_mid = (min_low + max_high) / 2.0

    # 根据当前价位段选择不同 padding，保证低价股和高价股都清晰
    if price_mid <= 10:
        padding = 0.5
    elif price_mid <= 50:
        padding = 1.0
    elif price_mid <= 100:
        padding = 2.0
    elif price_mid <= 500:
        padding = 5.0
    elif price_mid <= 1000:
        padding = 10.0
    else:
        padding = price_mid * 0.02

    y_min = max(0, min_low - padding)
    y_max = max_high + padding

    # ── 事件标注：利好上方、利空下方 ──
    idx_counter = {}  # 记录同一根 K 线上已绘制的标注数量，用于分散布局（即使无事件也需初始化，供末尾 Y 轴扩展判断）
    if not events_df.empty:
        # 自动识别事件类型列
        if event_type_col is None:
            for cand in ["sentiment", "type", "event_type", "情感"]:
                if cand in events_df.columns:
                    event_type_col = cand
                    break

        type_col = event_type_col if event_type_col in events_df.columns else None

        for _, evt in events_df.iterrows():
            evt_dt = pd.to_datetime(evt["date"])
            # 只标注落在可见窗口内的事件
            if not (visible["date"].min() <= evt_dt <= visible["date"].max()):
                continue

            mask = visible["date"] <= evt_dt
            if not mask.any():
                continue
            idx = int(visible.loc[mask].index[-1])
            day_high = float(visible.loc[idx, "high"])
            day_low = float(visible.loc[idx, "low"])
            evt_text = str(evt.get(event_title_col, ""))[:12]
            if not evt_text:
                continue

            # 判断利好/利空/中性（中国市场：红=利好/涨，绿=利空/跌）
            evt_type = ""
            if type_col:
                raw_type = str(evt[type_col]).strip().lower()
                # 统一映射各种可能的情感标签
                if raw_type in ("利好", "正面", "positive", "看涨", "bullish", "买入"):
                    evt_type = "利好"
                elif raw_type in ("利空", "负面", "negative", "看跌", "bearish", "卖出"):
                    evt_type = "利空"
                else:
                    evt_type = "中性"
            else:
                # 没有类型列时，尝试从标题关键词判断
                title_lower = evt_text.lower()
                if any(w in title_lower for w in ["利好", "大涨", "上涨", "增长", "突破", "收购", "回购", "分红"]):
                    evt_type = "利好"
                elif any(w in title_lower for w in ["利空", "大跌", "下跌", "亏损", "减持", "处罚", "退市", "暴雷"]):
                    evt_type = "利空"
                else:
                    evt_type = "中性"

            # 颜色映射：利好=红，利空=绿，中性跳过
            if evt_type == "利好":
                color = UP_COLOR
                anchor_y = day_high       # 从 K 线最高价出发
                direction = 1             # 整体向上
            elif evt_type == "利空":
                color = DOWN_COLOR
                anchor_y = day_low        # 从 K 线最低价出发
                direction = -1            # 整体向下
            else:
                # 跳过中性事件
                continue

            # 给标注加上日期，并截断标题避免过长
            evt_date_label = str(evt.get("date", ""))[:10]
            display_text = f"{evt_date_label}<br>{evt_text}"

            # 同一根 K 线上多个事件时的分散布局
            idx_count = idx_counter.get(idx, 0)
            idx_counter[idx] = idx_count + 1
            global_count = sum(idx_counter.values()) - 1
            layer = idx_count
            stagger = 1 if (idx + layer + global_count) % 2 == 0 else -1
            level = (layer // 2) + 1

            # 垂直偏移：文本框离 K 线主体越来越远（按层数）
            y_offset = direction * padding * (1.8 + 0.6 * level)
            text_y = anchor_y + y_offset

            # 水平偏移：利好偏右、利空偏左，相邻层错开
            type_bias = {"利好": 22, "利空": -22}[evt_type]
            ax_offset = type_bias + (stagger * 36) * level

            # 箭头长度：从文本框指向 K 线柱子边缘
            # 利好：箭头向下（文本框在箭头上方）
            # 利空：箭头向上（文本框在箭头下方）
            ay_offset = direction * (45 + 18 * level)

            fig.add_annotation(
                x=int(idx),
                y=text_y,
                text=display_text,
                showarrow=True,
                arrowhead=3,
                arrowsize=1.0,
                arrowcolor=color,
                font=dict(size=10, color="white", family="sans-serif"),
                ax=ax_offset,
                ay=ay_offset,
                xref="x",
                yref="y",
                align="center",
                bgcolor="rgba(11,14,20,0.78)",
                bordercolor=color,
                borderwidth=1,
                borderpad=3,
            )

    # 根据实际标注层数扩展 Y 轴，确保分散的标注可见
    if idx_counter:
        max_layer = max((c // 2) + 1 for c in idx_counter.values())
        y_min = max(0, min_low - padding * (1 + 0.4 * max_layer))
        y_max = max_high + padding * (1 + 0.4 * max_layer)
        fig.update_yaxes(range=[y_min, y_max], row=1, col=1)

    # ── X 轴刻度：局部放大（<=30根K线）时显示全部日期，否则自动稀疏 ──
    if m <= 30:
        tick_indices = list(range(m))
    else:
        nticks = min(max(5, m // 10), 12)
        tick_indices = np.linspace(0, m - 1, nticks).astype(int)

    # 当 K 线数量 <= 60 时，用完整日期格式（含年月），避免跨年混淆
    if m <= 60:
        date_labels_full = visible["date"].dt.strftime("%m-%d").tolist()
    else:
        date_labels_full = date_labels

    if _is_dark():
        grid_color = SF_GRID
        border_color = SF_BORDER
        tick_color = SF_TXT2
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template="starfield_dark",
            height=550,
            margin=dict(l=40, r=20, t=50, b=80),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,
                xanchor="center",
                x=0.5,
                font=dict(color=SF_TXT2),
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": SF_TXT2},
            title={"text": title, "font": {"color": SF_TXT, "size": 14}},
            xaxis=dict(
                tickmode="array",
                tickvals=tick_indices,
                ticktext=[date_labels_full[i] for i in tick_indices],
                tickangle=-45,
                range=[-0.5, m - 0.5],
                showgrid=True,
                gridcolor=grid_color,
                linecolor=border_color,
                tickfont={"color": tick_color},
            ),
            yaxis=dict(
                range=[y_min, y_max],
                fixedrange=False,
                showgrid=True,
                gridcolor=grid_color,
                linecolor=border_color,
                tickfont={"color": tick_color},
            ),
            dragmode="pan",
        )
    else:
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template="plotly_white",
            height=550,
            margin=dict(l=40, r=20, t=50, b=80),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,
                xanchor="center",
                x=0.5,
            ),                plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            xaxis=dict(
                tickmode="array",
                tickvals=tick_indices,
                ticktext=[date_labels_full[i] for i in tick_indices],
                tickangle=-45,
                range=[-0.5, m - 0.5],
                showgrid=True,
                gridcolor="#E5E7EB",  # 可见网格线（TradingView Paper Light 级别）
            ),
            yaxis=dict(
                range=[y_min, y_max],
                fixedrange=False,
                showgrid=True,
                gridcolor="#E5E7EB",  # 可见网格线（TradingView Paper Light 级别）
            ),
            dragmode="pan",
        )

    if rows == 2:
        fig.update_xaxes(
            tickmode="array",
            tickvals=tick_indices,
            ticktext=[date_labels_full[i] for i in tick_indices],
            tickangle=-45,
            row=2, col=1,
        )
        fig.update_yaxes(
            range=[0, max_vol * 1.1],
            fixedrange=False,
            showgrid=True,
            gridcolor=SF_GRID if _is_dark() else "#E5E7EB",
            linecolor=SF_BORDER if _is_dark() else "#E5E7EB",
            tickfont={"color": SF_TXT2 if _is_dark() else "#6B7280"},
            row=2, col=1,
        )

    return fig
