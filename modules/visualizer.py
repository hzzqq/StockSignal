"""
可视化模块
生成 K 线图、行业热力图、相关性矩阵、信号评分雷达图等。
基于 Plotly + Matplotlib，适配 Streamlit 展示。
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# mplfinance 可选导入（仅 matplotlib 静态 K 线用到，Plotly 交互图不需要）
try:
    import mplfinance as mpf
    _MPF_OK = True
except ImportError:
    _MPF_OK = False

# 中文字体配置
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


class Visualizer:
    """图表生成器。"""

    # ------------------------------------------------------------------
    # K 线图（Plotly 交互式）
    # ------------------------------------------------------------------
    @staticmethod
    def candlestick(df, title="K线图", show_volume=True, ma_windows=[5, 20, 60]):
        """
        生成交互式 K 线图。
        :param df: 行情数据，需含 date, open, close, high, low, volume
        :return: plotly Figure
        """
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        rows = 2 if show_volume else 1
        row_heights = [0.7, 0.3] if show_volume else [1.0]
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=True,
            vertical_spacing=0.05, row_heights=row_heights,
            subplot_titles=(title, "成交量") if show_volume else (title,)
        )

        # K线
        fig.add_trace(go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"],
            increasing_line_color="#e74c3c",   # A股：涨红
            decreasing_line_color="#2ecc71",   # A股：跌绿
            name="K线"
        ), row=1, col=1)

        # 均线
        for w in ma_windows:
            if len(df) >= w:
                ma = df["close"].rolling(w).mean()
                fig.add_trace(go.Scatter(
                    x=df["date"], y=ma, name=f"MA{w}",
                    line=dict(width=1.2)
                ), row=1, col=1)

        # 成交量
        if show_volume and "volume" in df.columns:
            colors = np.where(df["close"] >= df["open"], "#e74c3c", "#2ecc71")
            fig.add_trace(go.Bar(
                x=df["date"], y=df["volume"], name="成交量",
                marker_color=colors, opacity=0.7
            ), row=2, col=1)

        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template="plotly_white",
            height=550,
            margin=dict(l=40, r=20, t=50, b=40),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
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

        colors = np.where(df["change_pct"] > 0, "#e74c3c", "#2ecc71")
        fig = go.Figure(go.Bar(
            x=df["change_pct"], y=df["sector"],
            orientation="h",
            marker_color=colors,
            text=df["change_pct"].round(2).astype(str) + "%",
            textposition="outside"
        ))
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
            line=dict(color="#3498db", width=2),
            fillcolor="rgba(52, 152, 219, 0.2)"
        ))
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
            line=dict(color="#e74c3c", width=2)
        ))
        if benchmark is not None:
            fig.add_trace(go.Scatter(
                x=result_df["date"], y=benchmark,
                mode="lines", name="基准收益",
                line=dict(color="#95a5a6", width=1.5, dash="dash")
            ))
        fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=0.5)
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
            line=dict(color="#e74c3c", width=1.5),
            fill="tozeroy", fillcolor="rgba(231, 76, 60, 0.15)"
        ))
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
        colors = np.where(df["pnl_pct"] >= 0, "#e74c3c", "#2ecc71")
        fig = go.Figure(go.Bar(
            x=df["name"], y=df["pnl_pct"],
            marker_color=colors,
            text=df["pnl_pct"].round(2).astype(str) + "%",
            textposition="outside"
        ))
        fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=0.5)
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
    def event_timeline(df, events_df, title="事件时间轴"):
        """
        在 K 线图上标注事件。
        :param df: 行情数据
        :param events_df: 事件数据，需含 date, title
        """
        fig = Visualizer.candlestick(df, title=title)

        for _, evt in events_df.iterrows():
            evt_date = pd.to_datetime(evt["date"])
            # 找到最接近的交易日
            mask = df["date"] <= evt_date
            if mask.any():
                idx = df.loc[mask, "high"].idxmax()
                fig.add_annotation(
                    x=evt_date, y=df.loc[idx, "high"] * 1.03,
                    text=str(evt.get("title", ""))[:10],
                    showarrow=True, arrowhead=2, arrowsize=0.8,
                    arrowcolor="#3498db", font=dict(size=10, color="#3498db")
                )
        return fig
