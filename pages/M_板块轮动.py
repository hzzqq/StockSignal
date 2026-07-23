"""
板块轮动热力图
----------------
用一张热力图 + 排行榜 + 资金轮动视图，直观呈现行业板块的「强弱」与「资金流向」。

  🔥 热力图   —— 行业按涨跌幅着色（红涨绿跌），按资金净流入定大小
  📊 排行榜   —— 涨幅/跌幅行业 TOP10
  🔄 资金轮动 —— 行业资金净流入排行 + 强弱象限（涨跌幅 × 净额）

数据优先取行业资金流（含涨跌幅+净额），失败时降级到板块涨跌列表。
各取数区块独立隔离（safe_section）。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, trading_autorefresh
from modules.fundflow import get_industry_fund_flow
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, safe_fragment, render_data_degradation_banner
from modules.page_widgets import _empty_info, UP, DOWN

apply_page_config(page_title="板块轮动", page_icon="🔥", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("🔥 板块轮动热力图")
st.caption("红涨绿跌；热力图块大小代表资金净流入，颜色代表涨跌幅。各视图独立取数。")

FETCHER = StockFetcher()


@st.cache_data(ttl=120, show_spinner=False)
def _load_flow():
    try:
        df = get_industry_fund_flow()
        if df is not None and not df.empty:
            return df, "行业资金流(akshare)"
    except Exception:
        pass
    # 降级：仅涨跌幅
    try:
        s = FETCHER.get_sector_list()
        if s is not None and not s.empty:
            s = s.rename(columns={"sector": "行业", "change_pct": "涨跌幅"})
            s["净额"] = np.nan
            return s, "板块涨跌列表"
    except Exception:
        pass
    return pd.DataFrame(), "无数据"


def _norm_num(series):
    return pd.to_numeric(series, errors="coerce")


def _heatmap(df):
    d = df.copy()
    if "行业" not in d.columns or "涨跌幅" not in d.columns:
        _empty_info("板块数据字段不完整（缺少「行业」或「涨跌幅」），暂无法渲染（接口字段变更或网络异常）。")
        return
    d["涨跌幅"] = _norm_num(d["涨跌幅"])
    d["净额"] = _norm_num(d.get("净额"))
    d = d.dropna(subset=["涨跌幅"]).drop_duplicates("行业")
    if d.empty:
        _empty_info("暂无板块数据。")
        return
    maxabs = max(abs(d["涨跌幅"]).max(), 0.1)
    # 大小：净额（缺失则用 1）
    sizes = d["净额"].abs().fillna(1)
    if sizes.sum() == 0 or sizes.isna().all():
        sizes = pd.Series([1] * len(d))
    fig = go.Figure(go.Treemap(
        labels=d["行业"],
        parents=[""] * len(d),
        values=sizes,
        marker=dict(
            colors=d["涨跌幅"],
            colorscale=[[0, DOWN], [0.5, "#cccccc"], [1, UP]],
            cmin=-maxabs, cmax=maxabs, cmid=0,
            colorbar=dict(title="涨跌幅%", tickfont=dict(color="white" if dark else "black")),
            line=dict(width=1, color="white" if dark else "#333"),
        ),
        text=[f"{v:+.2f}%" for v in d["涨跌幅"]],
        texttemplate="<b>%{label}</b><br>%{text}",
        textfont=dict(size=12, color="white" if dark else "black"),
        hovertemplate="<b>%{label}</b><br>涨跌幅 %{text}<extra></extra>",
    ))
    fig.update_layout(
        height=560, margin=dict(t=10, l=10, r=10, b=10),
        template="plotly_dark" if dark else "plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)


def _ranking(df):
    d = df.copy()
    if "行业" not in d.columns or "涨跌幅" not in d.columns:
        _empty_info("板块数据字段不完整（缺少「行业」或「涨跌幅」），暂无法渲染（接口字段变更或网络异常）。")
        return
    d["涨跌幅"] = _norm_num(d["涨跌幅"])
    d = d.dropna(subset=["涨跌幅"]).drop_duplicates("行业")
    if d.empty:
        _empty_info("暂无板块数据。")
        return
    d = d.sort_values("涨跌幅", ascending=False)
    top = d.head(10)
    bot = d.tail(10).sort_values("涨跌幅")
    col1, col2 = st.columns(2)
    y_common = dict(template="plotly_dark" if dark else "plotly_white",
                    height=360, margin=dict(t=30, l=80, r=20, b=20))
    with col1:
        st.markdown("#### 🚀 涨幅 TOP10")
        fig = go.Figure(go.Bar(
            x=top["涨跌幅"], y=top["行业"], orientation="h",
            marker=dict(color=top["涨跌幅"], colorscale=[[0, DOWN], [1, UP]]),
            text=[f"{v:+.2f}%" for v in top["涨跌幅"]], textposition="auto",
        ))
        fig.update_layout(**y_common, xaxis_title="涨跌幅%")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown("#### 📉 跌幅 TOP10")
        fig = go.Figure(go.Bar(
            x=bot["涨跌幅"], y=bot["行业"], orientation="h",
            marker=dict(color=bot["涨跌幅"], colorscale=[[0, DOWN], [1, UP]]),
            text=[f"{v:+.2f}%" for v in bot["涨跌幅"]], textposition="auto",
        ))
        fig.update_layout(**y_common, xaxis_title="涨跌幅%")
        st.plotly_chart(fig, use_container_width=True)


def _rotation(df):
    d = df.copy()
    if "行业" not in d.columns or "涨跌幅" not in d.columns:
        _empty_info("板块数据字段不完整（缺少「行业」或「涨跌幅」），暂无法渲染（接口字段变更或网络异常）。")
        return
    d["涨跌幅"] = _norm_num(d["涨跌幅"])
    d["净额"] = _norm_num(d.get("净额"))
    d = d.dropna(subset=["涨跌幅"]).drop_duplicates("行业")
    if d.empty:
        _empty_info("暂无板块数据。")
        return
    # 资金净流入排行（有净额时）
    if d["净额"].notna().any():
        dd = d.dropna(subset=["净额"]).sort_values("净额", ascending=False)
        top_in = dd.head(12)
        top_out = dd.tail(12).sort_values("净额")
        col1, col2 = st.columns(2)
        y_common = dict(template="plotly_dark" if dark else "plotly_white",
                        height=420, margin=dict(t=30, l=90, r=20, b=20))
        with col1:
            st.markdown("#### 💰 资金净流入 TOP12")
            fig = go.Figure(go.Bar(
                x=top_in["净额"] / 1e8, y=top_in["行业"], orientation="h",
                marker=dict(color=UP),
                text=[f"{v/1e8:.1f}亿" for v in top_in["净额"]], textposition="auto",
            ))
            fig.update_layout(**y_common, xaxis_title="净额(亿元)")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.markdown("#### 💸 资金净流出 TOP12")
            fig = go.Figure(go.Bar(
                x=top_out["净额"] / 1e8, y=top_out["行业"], orientation="h",
                marker=dict(color=DOWN),
                text=[f"{v/1e8:.1f}亿" for v in top_out["净额"]], textposition="auto",
            ))
            fig.update_layout(**y_common, xaxis_title="净额(亿元)")
            st.plotly_chart(fig, use_container_width=True)
    # 强弱象限：涨跌幅 × 净额
    st.markdown("#### 🔄 强弱象限（涨跌幅 × 资金净额）")
    quad = d.dropna(subset=["净额"]) if d["净额"].notna().any() else d.assign(净额=0)
    fig = go.Figure(go.Scatter(
        x=quad["涨跌幅"], y=quad["净额"] / 1e8,
        mode="markers+text", text=quad["行业"], textposition="top center",
        textfont=dict(size=10, color="white" if dark else "black"),
        marker=dict(
            size=12,
            color=quad["涨跌幅"],
            colorscale=[[0, DOWN], [1, UP]],
            line=dict(width=1, color="white" if dark else "#333"),
        ),
        hovertemplate="<b>%{text}</b><br>涨跌幅 %{x:.2f}%<br>净额 %{y:.2f}亿<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="#888")
    fig.add_vline(x=0, line_dash="dot", line_color="#888")
    fig.update_layout(
        height=480, template="plotly_dark" if dark else "plotly_white",
        xaxis_title="涨跌幅%", yaxis_title="资金净额(亿元)", margin=dict(t=20, l=60, r=20, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("右上象限＝价量齐升的领涨主线；左下象限＝价量齐跌的弱势板块。")


# ───────────────────────── 主渲染 ─────────────────────────
@safe_fragment("板块轮动")
def fragment_sectors():
    trading_autorefresh(key="sector_autorefresh")
    # ───────────────────────── 主渲染 ─────────────────────────
    with safe_section("板块数据", hint="行业资金流接口可能受网络限制；可稍后重试。"):
        df, src = _load_flow()
        if df.empty:
            st.error("⚠️ 板块数据暂时不可用，请稍后重试。")
        else:
            st.success(f"数据来源：{src}　·　共 {len(df)} 个行业", icon="📡")
            render_data_degradation_banner()
            tab1, tab2, tab3 = st.tabs(["🔥 热力图", "📊 排行榜", "🔄 资金轮动"])
            with tab1:
                _heatmap(df)
            with tab2:
                _ranking(df)
            with tab3:
                _rotation(df)
            st.divider()
            st.markdown("#### 🧭 板块轮动解读")
            st.caption("🔥 热力图：块越大=资金净流入越多，颜色越红=涨幅越大；"
                       "📊 排行榜：看哪些行业领涨/领跌；"
                       "🔄 资金轮动：右上象限（价量齐升）是当前主线，资金从绿（净流出）板块流向红（净流入）板块即为轮动。"
                       "交易时段内本区块每 60 秒自动刷新。")


fragment_sectors()
