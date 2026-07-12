"""
可视化模块
生成 K 线图、行业热力图、相关性矩阵、信号评分雷达图等。
基于 Plotly + Matplotlib，适配 Streamlit 展示。
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import plotly.io as pio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

# 确保自定义暗色模板存在：若页面未经过 ui_theme.apply_theme，visualizer 自己兜底注册
# 使用 plotly_dark 作为基底色，避免 "Invalid value of type 'builtins.str'" 的 template 异常
if "starfield_dark" not in pio.templates:
    try:
        pio.templates["starfield_dark"] = go.layout.Template(layout=pio.templates["plotly_dark"].layout)
    except Exception:
        pass

# 涨跌配色（A股：红涨绿跌）
UP_COLOR = "#ff4d4f"
DOWN_COLOR = "#00d486"
HOLD_COLOR = "#ffa502"

# 星辰暗色图表令牌
SF_TXT = "#e2e8f0"
SF_TXT2 = "#94a3b8"
SF_GRID = "#23233c"
SF_BORDER = "#2d2d44"
SF_CARD = "#1a1a2e"
SF_BG = "#0f0f23"


def _is_dark() -> bool:
    """返回当前是否为暗色模式（含「个股分析」页面强制暗色作用域）。"""
    try:
        from modules.ui_theme import _theme_is_dark
        return _theme_is_dark()
    except Exception:
        try:
            return st.session_state.get("theme_mode", "light") == "dark"
        except Exception:
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

# 中文字体配置
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


class Visualizer:
    """图表生成器。V4: 手动Bar+Scatter绘制K线，彻底避免Candlestick内部日期逻辑。"""
    _VERSION = "v4-manual-bar"

    # 均线配色循环（截图风格：MA5 红 / MA10 橙 / MA20 蓝 / 后续依次）
    MA_COLORS = ["#ff4d4f", "#ffa502", "#667eea", "#00d4aa", "#764ba2"]

    @staticmethod
    def _ma_color(i: int) -> str:
        return Visualizer.MA_COLORS[i % len(Visualizer.MA_COLORS)]

    @staticmethod
    def kline_legend_html(ma_windows=[5, 10, 20], up_color="#ff4d4f",
                        down_color="#00d486", ma_colors=None):
        """生成截图风格的自定义图例 HTML（K线 / MA / 成交量）。
        up_color/down_color：涨跌柱配色（默认 A 股红涨绿跌）。
        ma_colors：均线配色列表，默认 MA_COLORS。"""
        if ma_colors is None:
            ma_colors = Visualizer.MA_COLORS
        parts = [
            '<span style="display:inline-flex;align-items:center;gap:3px;">',
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{up_color};"></span>',
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{down_color};margin-left:-2px;"></span>',
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

    # ------------------------------------------------------------------
    # K 线图（Plotly 交互式）
    # ------------------------------------------------------------------
    @staticmethod
    def candlestick(df, title="K线图", show_volume=True, ma_windows=[5, 20, 60],
                   start_idx=0, n_show=None, annotations=None, support=None, resistance=None,
                   up_color=None, down_color=None, ma_colors=None):
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
        :return: plotly Figure
        """
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        n = len(df)
        if n == 0:
            fig = go.Figure()
            fig.update_layout(**_plotly_layout_kwargs(title=title, height=550))
            return fig

        # ── 窗口裁剪（支持「显示位置 / 显示 K 线数量」滑块）──
        # 在 FULL df 上计算后切片，保证窗口左缘的均线值准确
        if n_show is None:
            n_show = n
        n_show = max(10, min(int(n_show), n))
        start_idx = max(0, min(int(start_idx), n - n_show))
        end_idx = start_idx + n_show
        visible = df.iloc[start_idx:end_idx].copy().reset_index(drop=True)
        m = len(visible)

        # x_idx 用于 shapes（category 轴的整数坐标），x_vals 用于 traces（日期类别）
        x_idx = list(range(m))
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
            ma_colors = Visualizer.MA_COLORS

        rows = 2 if show_volume else 1
        row_heights = [0.7, 0.3] if show_volume else [1.0]
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=True,
            vertical_spacing=0.05, row_heights=row_heights,
            subplot_titles=(None, None) if show_volume else (title,)
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
                    x0=i, y0=y_bottom, x1=i, y1=y_top,
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
                    x0=i, y0=y_top, x1=i, y1=y_bottom,
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

        for ann in all_annotations:
            price = ann.get("price")
            label = ann.get("label", "")
            color = ann.get("color", "#94a3b8")
            dash = ann.get("dash", "dash")
            if price is not None and not np.isnan(price):
                fig.add_hline(
                    y=price, line_dash=dash, line_color=color, line_width=1,
                    annotation_text=f"{label}({price:.1f})" if label else f"{price:.1f}",
                    annotation_position="right",
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

        # 主题适配：暗色用透明底+暗灰网格，亮色用白底+浅灰网格
        grid_color = SF_GRID if _is_dark() else "#E5E7EB"
        paper_bg = "rgba(0,0,0,0)" if _is_dark() else "#FFFFFF"
        plot_bg = "rgba(0,0,0,0)" if _is_dark() else "#FFFFFF"
        title_kwargs = {"text": title, "font": {"color": SF_TXT, "size": 14}} if _is_dark() else title

        fig.update_layout(
            title=title_kwargs,
            xaxis_rangeslider_visible=False,
            template="starfield_dark" if _is_dark() else "plotly_white",
            height=550,
            margin=dict(l=40, r=50, t=50, b=80),
            showlegend=False,
            hovermode="x",
            # 保留 zoom / reset / pan 按钮；仅移除 lasso / box-select / autoscale
            modebar=dict(remove=["select2d", "lasso2d", "autoScale2d"]),
            paper_bgcolor=paper_bg,
            plot_bgcolor=plot_bg,
            # 默认 drag 平移，避免一拉 K线就变成框选放大；框选放大保留在工具栏 🔍 中
            dragmode="pan",
            hoverlabel=dict(
                bgcolor="#1a1a2e" if _is_dark() else "#ffffff",
                font=dict(color="#e2e8f0" if _is_dark() else "#1f2937"),
                bordercolor="#2d2d44" if _is_dark() else "#e5e7eb",
                namelength=-1,
            ),
            xaxis=dict(
                type="category",
                categoryorder="array",
                categoryarray=x_vals,
                tickmode="array",
                tickvals=tick_indices,
                ticktext=[date_labels_full[i] for i in tick_indices],
                tickangle=-45,
                range=[-0.5, m - 0.5],
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
                type="category",
                categoryorder="array",
                categoryarray=x_vals,
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
                gridcolor=grid_color,
                linecolor=SF_BORDER if _is_dark() else "#E5E7EB",
                tickfont={"color": SF_TXT2 if _is_dark() else "#6B7280"},
                row=2, col=1,
            )
        return fig

    # ------------------------------------------------------------------
    # 行业板块热力图
    # ------------------------------------------------------------------
    @staticmethod
    def sector_heatmap(sector_df, title="行业板块涨跌热力图"):
        """
        生成行业板块涨跌幅热力图。
        :param sector_df: DataFrame[sector, change_pct]
        :return: plotly Figure
        """
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

    # ------------------------------------------------------------------
    # 相关性矩阵
    # ------------------------------------------------------------------
    @staticmethod
    def correlation_matrix(daily_dict, method="pearson"):
        """
        生成多只股票收益率相关性矩阵热力图。
        :param daily_dict: {"600519": df, "000858": df, ...}
        :param method: pearson / spearman
        :return: plotly Figure
        """
        # 构建收益率 DataFrame
        returns = {}
        for ticker, df in daily_dict.items():
            if "close" in df.columns and len(df) > 1:
                returns[ticker] = df.set_index("date")["close"].pct_change()

        ret_df = pd.DataFrame(returns).dropna()
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

    # ------------------------------------------------------------------
    # 信号评分雷达图
    # ------------------------------------------------------------------
    @staticmethod
    def signal_radar(scores, title="信号评分雷达图"):
        """
        生成信号评分雷达图。
        :param scores: {"price_score": 72, "event_score": 85, "macro_score": 60}
        :return: plotly Figure
        """
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

    # ------------------------------------------------------------------
    # 回测收益曲线
    # ------------------------------------------------------------------
    @staticmethod
    def backtest_curve(result_df, benchmark=None, title="策略回测收益曲线"):
        """
        绘制回测累计收益曲线。
        :param result_df: 回测结果，需含 date, cumulative_return
        :param benchmark: 基准收益 Series（可选）
        :return: plotly Figure
        """
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

    # ------------------------------------------------------------------
    # 回撤曲线
    # ------------------------------------------------------------------
    @staticmethod
    def drawdown_curve(result_df, title="最大回撤曲线"):
        """
        绘制回撤曲线。
        :param result_df: 需含 date, drawdown 列
        """
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

    # ------------------------------------------------------------------
    # 持仓盈亏柱状图
    # ------------------------------------------------------------------
    @staticmethod
    def portfolio_pnl(portfolio_df, title="持仓盈亏一览"):
        """
        持仓盈亏柱状图。
        :param portfolio_df: 需含 ticker, name, pnl_pct 列
        """
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

    # ------------------------------------------------------------------
    # 信号时间轴（事件标注在K线上）
    # ------------------------------------------------------------------
    @staticmethod
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
