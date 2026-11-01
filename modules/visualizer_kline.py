# -*- coding: utf-8 -*-
"""visualizer_kline — K 线与分时图（visualizer 拆分·K线域）。

零业务逻辑改动：源码自 modules/visualizer.py 机械提取（dedent + 去 @staticmethod）。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.colors import DOWN_COLOR, UP_COLOR, hex_to_rgba
from modules.visualizer_core import (
    MA_COLORS,
    SF_BORDER,
    SF_GRID,
    SF_TXT,
    SF_TXT2,
    _empty_kline_figure,
    _is_dark,
    _plotly_layout_kwargs,
)

logger = logging.getLogger(__name__)


def candlestick(df, title="K线图", show_volume=True, ma_windows=None,
               start_idx=0, n_show=None, annotations=None, support=None, resistance=None,
               up_color=None, down_color=None, ma_colors=None,
               dragmode="pan", show_range_levels=True, events=None,
               event_type_col=None, event_title_col=None):
    """
    生成交互式 K 线图（V5 截图风格）。
    - 统一悬停：单浮层显示日期 / 成交量 / OHLC / MA 值（模仿截图 tooltip）。
    - 横向虚线：支持传入 annotations / support / resistance 在图中画水平参考线。
    - 工具栏去掉十字准星；hover 使用竖直虚线。
    - 使用纯手动 Bar + Scatter 组合绘制，避免 Plotly Candlestick 的日期解析。

    支持窗口化浏览（配合「显示位置 / 显示 K 线数量」滑块）：
    - start_idx: 窗口起始索引
    - n_show: 窗口显示 K 线数量
    均线在完整 df 上计算后再切片，保证窗口左缘的均线值准确；
    Y 轴量程随可见窗口自适应。

    :param df: 行情数据，需含 date, open, close, high, low, volume
    :param start_idx: 窗口起始索引（默认 0，显示最旧一段）
    :param n_show: 窗口显示 K 线数量（默认 None，显示全部）
    :param annotations: 水平参考线列表，如 [{"price": 88.84, "label": "压力位", "color": "#ff4d4f", "dash": "dash"}]
    :param support: 支撑位，若提供则自动画绿色虚线
    :param resistance: 压力位，若提供则自动画红色虚线
    :param up_color: 上涨 K 线颜色（默认 UP_COLOR，A 股红涨）
    :param down_color: 下跌 K 线颜色（默认 DOWN_COLOR，A 股绿跌）
    :param ma_colors: 均线配色列表（默认 MA_COLORS），按 ma_windows 顺序取色
    :param dragmode: 鼠标拖拽行为，"pan"（平移，默认）或 "zoom"（区域缩放框选）
    :param show_range_levels: 是否在可见窗口画「区间最高 / 区间最低」参考线（默认开）
    :return: plotly Figure
    """
    if ma_windows is None:
        ma_windows = [5, 20, 60]
    # ── 空 / 异常数据优雅兜底 ──
    if df is None or not isinstance(df, pd.DataFrame):
        return _empty_kline_figure(title, "暂无 K 线数据")
    required_cols = ["date", "open", "high", "low", "close"]
    if not all(c in df.columns for c in required_cols):
        return _empty_kline_figure(title, "K 线字段缺失：" + "、".join(
            c for c in required_cols if c not in df.columns))

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # 数值守卫：非数值 / 异常值 coerce 为 NaN 并丢弃，避免绘图崩溃
    for _c in ["open", "high", "low", "close"]:
        df[_c] = pd.to_numeric(df[_c], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    n = len(df)
    if n < 2:
        return _empty_kline_figure(title, "数据不足，至少需要 2 根 K 线")

    # ── 窗口裁剪（支持「显示位置 / 显示 K 线数量」滑块）──
    # 在 FULL df 上计算后切片，保证窗口左缘的均线值准确
    if n_show is None:
        n_show = n
    n_show = max(10, min(int(n_show), n))
    start_idx = max(0, min(int(start_idx), n - n_show))
    end_idx = start_idx + n_show
    visible = df.iloc[start_idx:end_idx].copy().reset_index(drop=True)
    m = len(visible)

    # x_vals 用于 traces（日期类别）
    x_vals = visible["date"].dt.strftime("%Y-%m-%d").tolist()
    date_strs = x_vals
    date_labels = visible["date"].dt.strftime("%m月%d日").tolist()

    # 涨跌判断
    rising = visible["close"].values >= visible["open"].values
    if up_color is None:
        up_color = UP_COLOR
    if down_color is None:
        down_color = DOWN_COLOR
    if ma_colors is None:
        ma_colors = MA_COLORS

    rows = 2 if show_volume else 1
    row_heights = [0.7, 0.3] if show_volume else [1.0]
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.05, row_heights=row_heights,
        # 不在 subplot 层放标题：单/双行都统一用居中的主标题，
        # 避免 show_volume=False 时 subplot_titles=(title,) 在左上角再叠加一份
        # 与主标题相同的文字，暗色模式下造成「左上文字重合」
        subplot_titles=(None,) if rows == 1 else (None, None)
    )

    # ── 统一悬停数据：日期 / OHLC / 成交量 / 成交量颜色 / MA 值 ──
    hover_data = [
        date_strs,
        visible["open"].round(2).values,
        visible["high"].round(2).values,
        visible["low"].round(2).values,
        visible["close"].round(2).values,
        visible["volume"].round(0).values if "volume" in visible.columns else np.zeros(m),
        np.where(rising, up_color, down_color),  # 成交量/K线圆点颜色
    ]
    ma_values = []
    for w in ma_windows:
        if len(df) >= w:
            ma = df["close"].rolling(w).mean().iloc[start_idx:end_idx].values
            ma_values.append(ma)
            hover_data.append(np.round(ma, 2))
        else:
            ma_values.append(np.full(m, np.nan))
            hover_data.append(np.full(m, np.nan))

    hover_template = "<b>%{customdata[0]}</b><br>"
    hover_template += "<span style='color:%{customdata[6]}'>●</span> 成交量: %{customdata[5]:,.0f}<br>"
    hover_template += "<span style='color:%{customdata[6]}'>●</span> K线<br>"
    hover_template += "开盘: ¥%{customdata[1]:.2f}<br>"
    hover_template += "收盘: ¥%{customdata[4]:.2f}<br>"
    hover_template += "最低: ¥%{customdata[3]:.2f}<br>"
    hover_template += "最高: ¥%{customdata[2]:.2f}<br>"
    for i, w in enumerate(ma_windows):
        color = ma_colors[i % len(ma_colors)]
        hover_template += f"<span style='color:{color}'>●</span> MA{w}: ¥%{{customdata[{7 + i}]:.2f}}<br>"
    hover_template += "<extra></extra>"

    # 悬停代理点将在所有可见 trace 之后添加（保证 fig.data[0] 为 K 线实体，兼容白盒测试）

    # ── 手绘 K 线实体（Bar：open→close）──
    fig.add_trace(go.Bar(
        x=x_vals,
        y=np.where(rising,
                  visible["close"].values - visible["open"].values,   # 涨：从 open 到 close
                  visible["open"].values - visible["close"].values),   # 跌：从 close 到 open
        base=visible["open"].values,
        marker_color=np.where(rising, up_color, down_color),
        width=0.75,
        name="K线",
        hoverinfo="skip",
    ), row=1, col=1)

    # ── 上影线（high → max(open,close)）──
    for i in range(m):
        y_top = visible["high"].iloc[i]
        y_bottom = max(visible["open"].iloc[i], visible["close"].iloc[i])
        if y_top > y_bottom + 0.001:  # 有上影线才画
            fig.add_shape(
                type="line",
                x0=x_vals[i], y0=y_bottom, x1=x_vals[i], y1=y_top,
                line=dict(color=up_color if rising[i] else down_color, width=1),
                xref="x", yref="y",
                row=1, col=1,
            )

    # ── 下影线（min(open,close) → low）──
    for i in range(m):
        y_top = min(visible["open"].iloc[i], visible["close"].iloc[i])
        y_bottom = visible["low"].iloc[i]
        if y_top > y_bottom + 0.001:  # 有下影线才画
            fig.add_shape(
                type="line",
                x0=x_vals[i], y0=y_top, x1=x_vals[i], y1=y_bottom,
                line=dict(color=up_color if rising[i] else down_color, width=1),
                xref="x", yref="y",
                row=1, col=1,
            )

    # ── 均线（在 FULL df 上计算后切片，保证窗口左缘 MA 准确）──
    for i, w in enumerate(ma_windows):
        if len(df) >= w:
            ma = ma_values[i]
            fig.add_trace(go.Scatter(
                x=x_vals, y=ma, name=f"MA{w}",
                line=dict(color=ma_colors[i % len(ma_colors)], width=1.5),
                hoverinfo="skip",
            ), row=1, col=1)

    # ── 成交量 ──
    if show_volume and "volume" in visible.columns:
        colors = np.where(rising, up_color, down_color)
        fig.add_trace(go.Bar(
            x=x_vals, y=visible["volume"], name="成交量",
            marker_color=colors, opacity=0.7,
            hoverinfo="skip",
        ), row=2, col=1)

    # ── 悬停代理点（透明 scatter，仅用于触发统一 tooltip，置于末端）──
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=visible["close"].values,
        mode="markers",
        marker=dict(opacity=0, size=0),
        name="hover_proxy",
        showlegend=False,
        customdata=np.stack(hover_data, axis=-1),
        hovertemplate=hover_template,
    ), row=1, col=1)

    # ── 水平参考线：annotations / support / resistance ──
    all_annotations = []
    if isinstance(annotations, list):
        all_annotations.extend(annotations)
    if support is not None:
        all_annotations.append({"price": support, "label": "支撑", "color": DOWN_COLOR})
    if resistance is not None:
        all_annotations.append({"price": resistance, "label": "压力", "color": UP_COLOR})

    # 区间最高 / 区间最低参考线（基于当前可见窗口）
    if show_range_levels:
        all_annotations.append({"price": visible["high"].max(), "label": "区间最高", "color": UP_COLOR, "dash": "dot"})
        all_annotations.append({"price": visible["low"].min(), "label": "区间最低", "color": DOWN_COLOR, "dash": "dot"})

    # 价格接近的标注合并，避免右侧文字重叠
    if all_annotations:
        price_range = max(visible["high"].max() - visible["low"].min(), 1e-6)
        threshold = price_range * 0.015  # 1.5% 价差视为重叠
        # 保留有效价格并排序
        valid = []
        for ann in all_annotations:
            p = ann.get("price")
            if p is not None and not np.isnan(p):
                valid.append({
                    "price": float(p),
                    "label": str(ann.get("label", "")),
                    "color": ann.get("color", "#94a3b8"),
                    "dash": ann.get("dash", "dash"),
                })
        valid.sort(key=lambda x: x["price"])
        merged = []
        for ann in valid:
            if merged and abs(ann["price"] - merged[-1]["price"]) < threshold:
                prev = merged[-1]
                # 合并标签，保留颜色（若同组颜色不同，用第一个颜色并注明）
                if ann["label"] and ann["label"] not in prev["label"]:
                    prev["label"] = f"{prev['label']} / {ann['label']}"
                prev["price"] = (prev["price"] + ann["price"]) / 2.0
                prev["count"] = prev.get("count", 1) + 1
            else:
                merged.append(dict(ann, count=1))
        all_annotations = merged

    for i, ann in enumerate(all_annotations):
        price = ann.get("price")
        label = ann.get("label", "")
        color = ann.get("color", "#94a3b8")
        dash = ann.get("dash", "dash")
        if price is not None and not np.isnan(price):
            # 偶数在右侧，奇数在左侧，避免同侧文字堆叠
            pos = "right" if i % 2 == 0 else "left"
            fig.add_hline(
                y=price, line_dash=dash, line_color=color, line_width=1,
                annotation_text=f"{label}({price:.1f})" if label else f"{price:.1f}",
                annotation_position=pos,
                annotation_font=dict(color=color, size=10),
                row=1, col=1,
            )

    # ── X 轴刻度：局部放大（<=30根K线）时显示全部日期，否则自动稀疏 ──
    if m <= 30:
        tick_indices = list(range(m))
        nticks = m
    else:
        nticks = min(max(5, m // 30), 10)
        tick_indices = np.linspace(0, m - 1, nticks).astype(int)

    # 当 K 线数量 <= 60 时，用完整日期格式（含年月），避免跨年混淆
    if m <= 60:
        date_labels_full = visible["date"].dt.strftime("%m-%d").tolist()
    else:
        date_labels_full = date_labels

    # ── Y 轴量程：按可见窗口的 high/low 自适应 padding（与 event_timeline 一致）──
    min_low = visible["low"].min()
    max_high = visible["high"].max()
    price_mid = (min_low + max_high) / 2.0
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

    # ── 事件标注：利好上方(红) / 利空下方(绿)，事件日量能高亮 ──
    if events is not None and not getattr(events, "empty", True):
        try:
            ev = events.copy()
            if "date" in ev.columns:
                ev["_dt"] = pd.to_datetime(ev["date"])
                lo, hi = visible["date"].min(), visible["date"].max()
                ev = ev[(ev["_dt"] >= lo) & (ev["_dt"] <= hi)]
                if event_type_col is None:
                    for cand in ["type", "sentiment", "event_type", "情感"]:
                        if cand in ev.columns:
                            event_type_col = cand
                            break
                if event_title_col is None:
                    for cand in ["title", "标题", "name"]:
                        if cand in ev.columns:
                            event_title_col = cand
                            break
                type_col = event_type_col if (event_type_col and event_type_col in ev.columns) else None
                title_col = event_title_col if (event_title_col and event_title_col in ev.columns) else None
                evt_highlight = []
                for _, e in ev.iterrows():
                    evt_dt = e["_dt"]
                    mask = visible["date"] <= evt_dt
                    if not mask.any():
                        continue
                    idx = int(visible.loc[mask].index[-1])
                    day_high = float(visible.loc[idx, "high"])
                    day_low = float(visible.loc[idx, "low"])
                    evt_text = str(e[title_col])[:12] if title_col and pd.notna(e.get(title_col)) else ""
                    if not evt_text:
                        continue
                    raw = str(e[type_col]).strip().lower() if type_col and pd.notna(e.get(type_col)) else ""
                    if raw in ("利好", "正面", "positive", "看涨", "bullish", "买入"):
                        et = "利好"
                    elif raw in ("利空", "负面", "negative", "看跌", "bearish", "卖出"):
                        et = "利空"
                    else:
                        t = evt_text.lower()
                        if any(w in t for w in ["利好", "大涨", "上涨", "增长", "突破", "收购", "回购", "分红"]):
                            et = "利好"
                        elif any(w in t for w in ["利空", "大跌", "下跌", "亏损", "减持", "处罚", "退市", "暴雷"]):
                            et = "利空"
                        else:
                            et = None
                    if et is None:
                        continue
                    color = UP_COLOR if et == "利好" else DOWN_COLOR
                    anchor_y = day_high if et == "利好" else day_low
                    direction = 1 if et == "利好" else -1
                    date_label = str(e["date"])[:10]
                    xcat = x_vals[idx]
                    text_y = anchor_y + direction * padding * (1.8 + 0.6)
                    fig.add_annotation(
                        x=xcat, y=text_y, text=f"{date_label}<br>{evt_text}",
                        showarrow=True, arrowhead=3, arrowsize=1.0, arrowcolor=color,
                        font=dict(size=10, color="white"), ax=22 if et == "利好" else -22,
                        ay=direction * 45, xref="x", yref="y", align="center",
                        bgcolor="rgba(11,14,20,0.78)", bordercolor=color, borderwidth=1, borderpad=3,
                    )
                    if et == "利好":
                        y_max = max(y_max, text_y + padding * 0.6)
                    else:
                        y_min = min(y_min, text_y - padding * 0.6)
                    evt_highlight.append(idx)
                # 事件日量能高亮（row=2 加菱形描边标记）
                if evt_highlight and show_volume and "volume" in visible.columns:
                    xs = [x_vals[i] for i in evt_highlight]
                    ys = [float(visible["volume"].iloc[i]) * 1.04 for i in evt_highlight]
                    fig.add_trace(go.Scatter(
                        x=xs, y=ys, mode="markers",
                        marker=dict(symbol="diamond", size=9, color="rgba(255,255,255,0.0)",
                                    line=dict(color="#fbbf24", width=2)),
                        name="事件日", showlegend=False, hoverinfo="skip",
                    ), row=2, col=1)
        except Exception as e:
            logger.warning(f"[visualizer] 处理异常: {e}")
            pass

    # 主题适配：暗色用透明底+暗灰网格，亮色用白底+浅灰网格
    grid_color = SF_GRID if _is_dark() else "#E5E7EB"
    paper_bg = "rgba(0,0,0,0)" if _is_dark() else "#FFFFFF"
    plot_bg = "rgba(0,0,0,0)" if _is_dark() else "#FFFFFF"
    # 标题显式居中（x=0.5），避免暗色模板下与左上角图例/标注文字叠在一起
    title_kwargs = {
        "text": title,
        "x": 0.5,
        "xanchor": "center",
        "font": {"color": SF_TXT if _is_dark() else "#111827", "size": 14},
    }

    fig.update_layout(
        title=title_kwargs,
        xaxis_rangeslider_visible=False,
        template="starfield_dark" if _is_dark() else "plotly_white",
        height=550,
        margin=dict(l=40, r=50, t=80, b=80),
        showlegend=True,
        # 图例移到右上角（顶栏 modebar 仅在 hover 时浮现，不常驻），彻底避开
        # 暗夜模式下与左上角标题/事件标注的文字重合问题
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.02,
            xanchor="right",
            x=1.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=SF_TXT if _is_dark() else "#374151", size=12),
        ),
        hovermode="x",
        # modebar 收拢：仅保留导出图片(toImage) 与 重置缩放(resetScale2d)；
        # 平移/区域缩放由页面「鼠标拖拽」开关切换 dragmode 控制，不再占用工具栏
        modebar=dict(remove=["pan2d", "zoom2d", "select2d", "lasso2d", "autoScale2d"]),
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
        # 拖拽行为由参数控制：默认平移(pan)，页面可切区域缩放(zoom)
        dragmode=dragmode,
        hoverlabel=dict(
            bgcolor="#1a1a2e" if _is_dark() else "#ffffff",
            font=dict(color="#e2e8f0" if _is_dark() else "#1f2937"),
            bordercolor="#2d2d44" if _is_dark() else "#e5e7eb",
            namelength=-1,
        ),
        xaxis=dict(
            type="date",
            tickmode="array",
            tickvals=[x_vals[i] for i in tick_indices],
            ticktext=[date_labels_full[i] for i in tick_indices],
            tickangle=-45,
            range=[x_vals[0], x_vals[-1]],
            showgrid=True,
            gridcolor=grid_color,
            linecolor=SF_BORDER if _is_dark() else "#E5E7EB",
            tickfont={"color": SF_TXT2 if _is_dark() else "#6B7280"},
            # 默认开启 spikeline（垂直十字线），hover 标签显示日期类别
            showspikes=True,
            spikemode="across",
            spikedash="dot",
            spikecolor=grid_color,
            spikethickness=1,
            spikesnap="data",
        ),
        yaxis=dict(
            range=[y_min, y_max],
            fixedrange=False,
            showgrid=True,
            gridcolor=grid_color,
            linecolor=SF_BORDER if _is_dark() else "#E5E7EB",
            tickfont={"color": SF_TXT2 if _is_dark() else "#6B7280"},
            showspikes=True,
            spikemode="across",
            spikedash="dot",
            spikecolor=grid_color,
            spikethickness=1,
            spikesnap="data",
        ),
    )
    if show_volume:
        max_vol = visible["volume"].max() if len(visible) > 0 else 1
        max_vol = max(1, max_vol)
        fig.update_xaxes(
            type="date",
            tickmode="array",
            tickvals=[x_vals[i] for i in tick_indices],
            ticktext=[date_labels_full[i] for i in tick_indices],
            tickangle=-45,
            row=2, col=1,
        )
        fig.update_yaxes(
            range=[0, max_vol * 1.1],
            fixedrange=False,
            showgrid=True,
            gridcolor=grid_color,
            linecolor=SF_BORDER if _is_dark() else "#E5E7EB",
            tickfont={"color": SF_TXT2 if _is_dark() else "#6B7280"},
            row=2, col=1,
        )
    return fig

def intraday(df, prev_close=None, title="分时图", show_volume=True, height=420,
             up_color=UP_COLOR, down_color=DOWN_COLOR):
    """
    生成个股分时走势图：价格线（红涨绿跌）+ 均价线 + 昨收基准虚线 + 成交量副图。

    :param df: DataFrame[time, open, high, low, close, volume, amount]
               time 形如 '2026-07-24 15:00:00'
    :param prev_close: 昨收价（水平基准线）；为空则不画基准
    :param title: 图表标题
    :param show_volume: 是否显示成交量副图
    :param up_color / down_color: 涨跌配色（A股默认红涨绿跌；个股页可传绿涨红跌）
    :return: plotly Figure
    """
    if df is None or len(df) == 0:
        return _empty_kline_figure(title, "暂无分时数据")
    try:
        d = df.copy()
        d["_t"] = d["time"].astype(str)
        d["_label"] = d["_t"].str[11:16]
        x = list(range(len(d)))

        close_arr = d["close"].astype(float).to_numpy()
        cum_amount = np.cumsum(d["amount"].astype(float).to_numpy())
        cum_volume = np.cumsum(d["volume"].astype(float).to_numpy())
        with np.errstate(divide="ignore", invalid="ignore"):
            avg = np.where(cum_volume > 0, cum_amount / cum_volume, close_arr)
        close = close_arr.tolist()
        avg = avg.tolist()

        base = float(prev_close) if prev_close is not None else float(close[0])
        is_up = close[-1] >= base
        line_color = up_color if is_up else down_color

        fill_color = hex_to_rgba(up_color if is_up else down_color, 0.15)

        rows_n = 2 if show_volume else 1
        fig = make_subplots(
            rows=rows_n, cols=1, shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.78, 0.22] if show_volume else [1.0],
        )
        # 价格折线（含涨跌幅填充）
        fig.add_trace(
            go.Scatter(
                x=x, y=close, mode="lines", name="价格",
                line=dict(color=line_color, width=1.6),
                fill="tozeroy", fillcolor=fill_color,
                customdata=d["_label"].tolist(),
                hovertemplate="%{customdata}<br>价格: %{y:.2f}<extra></extra>",
            ),
            row=1, col=1,
        )
        # 均价线
        fig.add_trace(
            go.Scatter(
                x=x, y=avg, mode="lines", name="均价",
                line=dict(color="#ffa502", width=1.2, dash="dot"),
                hovertemplate="均价: %{y:.2f}<extra></extra>",
            ),
            row=1, col=1,
        )
        # 昨收基准线
        if prev_close is not None:
            fig.add_hline(
                y=float(prev_close), line=dict(color="#94a3b8", width=1, dash="dash"),
                row=1, col=1,
            )
        # 成交量副图
        if show_volume:
            vol_colors = [up_color if c >= base else down_color for c in close]
            fig.add_trace(
                go.Bar(
                    x=x, y=d["volume"].astype(float).tolist(), name="成交量",
                    marker_color=vol_colors,
                    customdata=d["_label"].tolist(),
                    hovertemplate="%{customdata}<br>量: %{y:,.0f}<extra></extra>",
                ),
                row=2, col=1,
            )

        # X 轴稀疏标签（约 6 个时间点）
        n = len(x)
        step = max(1, n // 6)
        tick_indices = list(range(0, n, step))
        if (n - 1) not in tick_indices:
            tick_indices.append(n - 1)
        labels = d["_label"].tolist()
        tick_labels = [labels[i] for i in tick_indices]

        layout = _plotly_layout_kwargs(title=title, height=height)
        fig.update_layout(**layout)
        _xkw = dict(
            type="category", categoryorder="array", categoryarray=x,
            tickmode="array", tickvals=tick_indices, ticktext=tick_labels,
            tickangle=0,
        )
        fig.update_xaxes(**_xkw, row=1, col=1)
        # ---- 价格轴：按当日实际波幅动态定范围（不再从 0 起步）----
        day_high = float(d["high"].max()) if "high" in d.columns else max(close)
        day_low = float(d["low"].min()) if "low" in d.columns else min(close)
        span = day_high - day_low
        # 至少保留 0.8% 的价格空间作上下留白；若当日几乎无波动则用昨收的 1%
        pad = max(span * 0.25, base * 0.008) if base > 0 else span * 0.25
        y_min = min(day_low, base) - pad
        y_max = max(day_high, base) + pad

        fig.update_yaxes(
            title_text="价格", row=1, col=1,
            range=[y_min, y_max],
            tickfont={"color": SF_TXT2 if _is_dark() else "#6B7280"},
        )
        if show_volume:
            fig.update_xaxes(**_xkw, row=2, col=1)
            fig.update_yaxes(
                title_text="量", row=2, col=1,
                tickfont={"color": SF_TXT2 if _is_dark() else "#6B7280"},
            )
        return fig
    except Exception as e:
        logger.warning(f"[visualizer] 处理异常: {e}")
        return _empty_kline_figure(title, "分时图渲染失败")
