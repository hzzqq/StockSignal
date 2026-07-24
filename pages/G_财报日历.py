"""
页面 G：财报与业绩日历
按报告期查看已披露财报的个股列表（业绩报表），含每股收益/营收/净利润/同比，并支持
业绩预告（best-effort）与披露日历（best-effort）。数据层见 modules/fundflow.py。
A股配色：业绩改善(净利润同比>0)=红，下滑=绿。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.fundflow import (
    get_earnings_report, get_earnings_forecast, get_disclosure_calendar,
)

from modules.page_guard import safe_fragment
from modules.page_widgets import UP, DOWN, _fig_layout, _section_title, _empty_info

apply_page_config(page_title="财报日历", page_icon="📅", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)


st.title("📅 财报与业绩日历")
st.caption("按报告期查看已披露财报个股（业绩报表），含业绩预告与披露日历（best-effort）。数据来源：东方财富。")

PERIODS = {
    "2026 一季报": "20260331",
    "2025 年报": "20251231",
    "2026 中报": "20260630",
    "2026 三季报": "20260930",
    "2025 三季报": "20250930",
    "2025 中报": "20250630",
}






# ───────────────────────── 业绩报表 ─────────────────────────
@safe_fragment
def fragment_report():
    _section_title("📊 业绩报表（按报告期）", accent="#2b8aef")
    period_label = st.selectbox(
        "报告期", options=list(PERIODS.keys()), index=0,
        help="选择财报报告期，查看该期已披露财报的个股", key="rp_period",
    )
    period = PERIODS[period_label]
    try:
        df = get_earnings_report(period)
    except Exception as e:
        st.error(f"业绩报表加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info(f"「{period_label}」暂无已披露财报数据（可能尚未到披露期或接口受限）。")
        st.caption("💡 试试切换其他报告期，已完整披露的「2025 年报」通常数据最全。")
        if st.button("📅 试看 2025 年报", key="rp_try_2025"):
            st.session_state["rp_period"] = "2025 年报"
        return

    for c in ["每股收益", "营业总收入", "营收同比%", "净利润", "净利润同比%", "净利润环比%", "ROE%"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 概览指标
    up_cnt, down_cnt, beat_ratio = 0, 0, 0.0
    if "净利润同比%" in df.columns:
        yoy = df["净利润同比%"].dropna()
        up_cnt = int((yoy > 0).sum())
        down_cnt = int((yoy < 0).sum())
        beat_ratio = round(up_cnt / len(yoy) * 100, 1) if len(yoy) else 0.0
    else:
        st.info("「净利润同比%」字段缺失，盈利改善占比暂不可计算（接口字段变更或网络异常）。")
    cols = st.columns(4)
    with cols[0]:
        st.metric("披露家数", f"{len(df)}")
    with cols[1]:
        st.metric("净利润同比↑", f"{up_cnt}", help="净利润同比增长为正的公司数")
    with cols[2]:
        st.metric("净利润同比↓", f"{down_cnt}", help="净利润同比下滑的公司数")
    with cols[3]:
        st.metric("盈利改善占比", f"{beat_ratio}%",
                  help="净利润同比增长为正的公司占已披露财报公司的比例")

    # TOP 净利润柱状（红涨绿跌）
    if "净利润" in df.columns and "名称" in df.columns:
        top = df.dropna(subset=["净利润"]).sort_values("净利润", ascending=False).head(15).copy()
        if not top.empty:
            # 加法式格式化边界（第十四批）：净利润原始单位为「元」，直接展示会得到 1.2e11
            # 这类超长数字，可读性差。改以「亿元」为坐标/悬浮单位（涨跌着色仍以原始元符号判断）。
            top["净利润_亿"] = top["净利润"] / 1e8
            fig = go.Figure(go.Bar(
                x=top["名称"], y=top["净利润_亿"],
                customdata=top["净利润_亿"],
                marker_color=[UP if v >= 0 else DOWN for v in top["净利润"]],
                hovertemplate="%{x}<br>净利润：%{y:,.2f} 亿元<extra></extra>",
            ))
            fig.update_layout(**_fig_layout(dark), title="净利润 TOP15（亿元）", height=340)
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("「净利润 / 名称」字段缺失，TOP 净利润柱状图暂不可绘制（接口字段变更或网络异常）。")

    try:
        st.dataframe(
            df, use_container_width=True, hide_index=True,
            column_config={
                "披露时间": st.column_config.TextColumn("披露时间", help="财报实际披露日期"),
                "每股收益": st.column_config.NumberColumn("每股收益", format="%.2f"),
                "营业总收入": st.column_config.NumberColumn("营业总收入", format="%.2e"),
                "营收同比%": st.column_config.NumberColumn("营收同比%", format="%.1f"),
                "净利润": st.column_config.NumberColumn("净利润", format="%.2e"),
                "净利润同比%": st.column_config.NumberColumn("净利润同比%", format="%.1f"),
                "ROE%": st.column_config.NumberColumn("ROE%", format="%.2f"),
            },
        )
    except Exception as e:
        st.warning(f"财报日历表格渲染失败：{e}")


# ───────────────────────── 业绩预告（best-effort） ─────────────────────────
@safe_fragment
def fragment_forecast():
    _section_title("🔮 业绩预告（best-effort）", accent="#7c5cff")
    st.caption("业绩预告接口稳定性较低，加载失败时将自动跳过。")
    period_label = st.selectbox(
        "报告期（预告）", options=list(PERIODS.keys()), index=0, key="fc_period",
    )
    period = PERIODS[period_label]
    try:
        df = get_earnings_forecast(period)
    except Exception as e:
        df = pd.DataFrame()
        st.warning(f"业绩预告接口加载失败，已降级为空数据（{e}）。")
    if df is None or df.empty:
        _empty_info(f"「{period_label}」业绩预告暂不可用（接口返回空）。")
        st.caption("💡 业绩预告接口稳定性较低，可切换报告期或稍后重试。")
        if st.button("📅 试看 2025 年报", key="fc_try_2025"):
            st.session_state["fc_period"] = "2025 年报"
        return
    # 加法式渲染兜底：best-effort 接口返回的 DataFrame 可能含怪异列类型（如嵌套列表/对象），
    # 直接 st.dataframe 会异常；包裹后失败仅提示，不影响上方概览与下方其它视图。
    try:
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as _e:
        st.warning(f"业绩预告表格渲染失败：{_e}")


# ───────────────────────── 披露日历（best-effort） ─────────────────────────
@safe_fragment
def fragment_disclosure():
    _section_title("🗓️ 披露日历（best-effort）", accent="#10b981")
    st.caption("披露日期接口稳定性较低，加载失败时将自动跳过。")
    mcol1, mcol2 = st.columns(2)
    with mcol1:
        market = st.selectbox("市场", ["沪市", "深市", "沪深京"], index=0, key="dc_market")
    with mcol2:
        period_str = st.selectbox(
            "报告期（披露）",
            ["2025年报", "2024年报", "2023年报"],
            index=0, key="dc_period",
        )
    try:
        df = get_disclosure_calendar(market=market, period=period_str)
    except Exception as e:
        df = pd.DataFrame()
        st.warning(f"披露日历接口加载失败，已降级为空数据（{e}）。")
    if df is None or df.empty:
        _empty_info("披露日历暂不可用（接口返回空或参数不支持）。")
        st.caption("💡 可切换市场或报告期后重试；沪市 2025 年报通常最完整。")
        if st.button("📅 试看 沪市·2025年报", key="dc_try_2025"):
            st.session_state["dc_market"] = "沪市"
            st.session_state["dc_period"] = "2025年报"
        return
    st.dataframe(df, use_container_width=True, hide_index=True)


# ───────────────────────── 页面主体 ─────────────────────────
fragment_report()
st.markdown("---")
fragment_forecast()
st.markdown("---")
fragment_disclosure()
