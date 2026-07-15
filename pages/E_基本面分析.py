"""
页面 E：基本面分析
───────────────
个股综合基本面视图：
- 同业/板块横向对比
- 历史走势纵向对比（股价所处历史分位）
- 是否大盘主线（行业排名）
- 估值、市值、综合评分

数据以现有 StockFetcher 为主，缺失时降级展示，避免页面崩溃。
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, safe_switch_page
from modules.fetcher import StockFetcher
from modules.search_ui import stock_search_input
from modules.visualizer import UP_COLOR, DOWN_COLOR

apply_page_config(page_title="基本面分析", page_icon="🏛️", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🏛️ 基本面分析")
st.caption("个股估值、历史位置、行业横向对比与大盘主线判断（仅供参考，非投资建议）")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _to_float(x):
    try:
        return float(x) if x not in (None, "", "—") else None
    except Exception:
        return None


def _percentile(series: pd.Series, value: float) -> float | None:
    """计算 value 在 series 中的百分位（0-100）。"""
    if series is None or series.empty or value is None:
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return float(np.clip((s <= value).mean() * 100, 0, 100))


def _pe_status(pe: float | None) -> str:
    if pe is None or pe <= 0:
        return "—"
    if pe < 15:
        return "低估区间"
    if pe < 30:
        return "合理区间"
    if pe < 50:
        return "偏高区间"
    return "高估区间"


def _sector_rank(sector_df: pd.DataFrame, industry: str) -> int | None:
    if sector_df is None or sector_df.empty or not industry:
        return None
    df = sector_df.copy()
    df["change_pct"] = pd.to_numeric(df.get("change_pct", 0), errors="coerce").fillna(0)
    df = df.sort_values("change_pct", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    hits = df[df["sector"].astype(str).str.contains(industry, na=False)]
    if not hits.empty:
        return int(hits.iloc[0]["rank"])
    return None


def _composite_score(
    price: float | None,
    pe: float | None,
    hist_pct_5y: float | None,
    sector_rank: int | None,
    sector_total: int,
    market_cap: float | None,
) -> tuple[int, str]:
    """返回 0-100 的综合评分与解读文本。"""
    reasons = []
    score = 50.0

    # 1) 估值合理性（PE） 25 分
    pe_score = 12.5
    if pe is not None and pe > 0:
        if pe < 15:
            pe_score = 22.5
            reasons.append(f"✅ PE(TTM) {pe:.1f} 处于低估区间")
        elif pe < 30:
            pe_score = 18.0
            reasons.append(f"✅ PE(TTM) {pe:.1f} 估值合理")
        elif pe < 50:
            pe_score = 10.0
            reasons.append(f"⚠️ PE(TTM) {pe:.1f} 估值偏高")
        else:
            pe_score = 4.0
            reasons.append(f"❌ PE(TTM) {pe:.1f} 估值偏高")
    else:
        reasons.append("ℹ️ 暂无有效 PE 数据")

    # 2) 历史位置 25 分：40-75% 视为健康，过低过高压减
    hist_score = 12.5
    if hist_pct_5y is not None:
        if 40 <= hist_pct_5y <= 75:
            hist_score = 22.0
            reasons.append(f"✅ 5年价格分位 {hist_pct_5y:.1f}%，处于健康区间")
        elif hist_pct_5y < 20:
            hist_score = 14.0
            reasons.append(f"⚠️ 5年价格分位 {hist_pct_5y:.1f}%，处于历史低位（偏弱或超跌）")
        elif hist_pct_5y > 90:
            hist_score = 8.0
            reasons.append(f"⚠️ 5年价格分位 {hist_pct_5y:.1f}%，接近历史高位")
        else:
            hist_score = 17.0
            reasons.append(f"ℹ️ 5年价格分位 {hist_pct_5y:.1f}%")
    else:
        reasons.append("ℹ️ 暂无历史位置数据")

    # 3) 行业动能 30 分
    theme_score = 15.0
    if sector_rank is not None and sector_total > 0:
        pct = max(0, 1 - (sector_rank - 1) / sector_total)
        if sector_rank <= 5:
            theme_score = 28.0
            reasons.append(f"✅ 行业排名 #{sector_rank} / {sector_total}，位于主线前列")
        elif sector_rank <= 20:
            theme_score = 22.0
            reasons.append(f"✅ 行业排名 #{sector_rank} / {sector_total}，动能较好")
        elif sector_rank <= sector_total * 0.5:
            theme_score = 16.0
            reasons.append(f"ℹ️ 行业排名 #{sector_rank} / {sector_total}，中等水平")
        else:
            theme_score = 8.0
            reasons.append(f"⚠️ 行业排名 #{sector_rank} / {sector_total}，相对落后")
    else:
        reasons.append("ℹ️ 暂无行业排名数据")

    # 4) 市值规模 20 分
    cap_score = 10.0
    if market_cap is not None and market_cap > 0:
        if market_cap >= 1000:
            cap_score = 18.0
            reasons.append(f"✅ 总市值 {market_cap:.1f} 亿，大盘蓝筹")
        elif market_cap >= 300:
            cap_score = 15.0
            reasons.append(f"✅ 总市值 {market_cap:.1f} 亿，中大盘")
        elif market_cap >= 50:
            cap_score = 11.0
            reasons.append(f"ℹ️ 总市值 {market_cap:.1f} 亿，中小盘")
        else:
            cap_score = 7.0
            reasons.append(f"⚠️ 总市值 {market_cap:.1f} 亿，小盘股波动大")
    else:
        reasons.append("ℹ️ 暂无市值数据")

    score = pe_score + hist_score + theme_score + cap_score
    score = int(round(np.clip(score, 0, 100)))
    return score, "<br>".join(reasons)


# ═══════════════════════════════════════════════════════════════
# 选股
# ═══════════════════════════════════════════════════════════════
picked = stock_search_input(
    label="选择股票",
    key="fa_stock",
    default="600519",
)
code = str(picked or "600519").zfill(6)

if code:
    # ═══════════════════════════════════════════════════════════
    # 数据加载
    # ═══════════════════════════════════════════════════════════
    with st.spinner("正在加载基本面数据…"):
        fund = fetcher.get_fundamentals(code) or {}
        name = fund.get("name") or code
        industry = (fund.get("industry") or "").strip() or "—"
        price = _to_float(fund.get("price"))
        pe_ttm = _to_float(fund.get("pe_ttm"))
        market_cap = _to_float(fund.get("market_cap"))

        end = datetime.now().date()
        start_5y = (end - timedelta(days=365 * 5 + 30)).strftime("%Y-%m-%d")
        try:
            hist_df = fetcher.get_daily(code, start=start_5y, end=end.strftime("%Y-%m-%d"))
            if hist_df is not None and not hist_df.empty:
                hist_df = hist_df.copy()
                hist_df["close"] = pd.to_numeric(hist_df["close"], errors="coerce")
                hist_df = hist_df.dropna(subset=["close"]).reset_index(drop=True)
            else:
                hist_df = None
        except Exception:
            hist_df = None

        try:
            sector_df = fetcher.get_sector_list()
            if sector_df is None or sector_df.empty:
                sector_df = pd.DataFrame()
            else:
                sector_df = sector_df.copy()
                sector_df["change_pct"] = pd.to_numeric(sector_df.get("change_pct", 0), errors="coerce").fillna(0)
        except Exception:
            sector_df = pd.DataFrame()

    # ═══════════════════════════════════════════════════════════
    # 概览卡片
    # ═══════════════════════════════════════════════════════════
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("股票", f"{name}")
    with c2:
        st.metric("代码", code)
    with c3:
        st.metric("所属行业", industry)
    with c4:
        st.metric("最新价", f"¥{price:.2f}" if price else "—")
    with c5:
        st.metric("总市值", f"¥{market_cap:.1f}亿" if market_cap else "—")

    # ═══════════════════════════════════════════════════════════
    # 历史位置（纵向对比）
    # ═══════════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("📍 历史位置 · 纵向对比")
    if hist_df is not None and not hist_df.empty:
        current = float(hist_df["close"].iloc[-1])
        p_1y = _percentile(hist_df.tail(252)["close"], current) if len(hist_df) >= 60 else None
        p_3y = _percentile(hist_df.tail(756)["close"], current) if len(hist_df) >= 400 else None
        p_5y = _percentile(hist_df["close"], current)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("当前价", f"¥{current:.2f}")
        m2.metric("1年价格分位", f"{p_1y:.1f}%" if p_1y is not None else "—")
        m3.metric("3年价格分位", f"{p_3y:.1f}%" if p_3y is not None else "—")
        m4.metric("5年价格分位", f"{p_5y:.1f}%" if p_5y is not None else "—")

        fig_hist = go.Figure()
        fig_hist.add_trace(
            go.Scatter(
                x=hist_df["date"],
                y=hist_df["close"],
                mode="lines",
                name="收盘价",
                line=dict(color="#6366f1", width=1.4),
                fill="tozeroy",
                fillcolor="rgba(99,102,241,0.10)",
            )
        )
        fig_hist.add_hline(
            y=current,
            line=dict(color=UP_COLOR, dash="dash", width=1.5),
            annotation_text="当前价",
            annotation_position="top right",
        )
        fig_hist.update_layout(
            title=f"{name} 近5年走势与当前位置",
            xaxis_title="",
            yaxis_title="收盘价",
            height=360,
            margin=dict(l=40, r=40, t=40, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("暂无历史行情数据，无法计算历史分位。")

    # ═══════════════════════════════════════════════════════════
    # 行业横向对比
    # ═══════════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("🏭 行业横向对比")
    if not sector_df.empty and industry != "—":
        # 行业涨跌幅排名 Top15，高亮当前行业
        top_n = 15
        top_sectors = sector_df.sort_values("change_pct", ascending=False).head(top_n).copy()
        bar_colors = [
            UP_COLOR if str(row["sector"]) == industry or industry in str(row["sector"]) else (DOWN_COLOR if row["change_pct"] < 0 else "#94a3b8")
            for _, row in top_sectors.iterrows()
        ]

        fig_sector = go.Figure()
        fig_sector.add_trace(
            go.Bar(
                x=top_sectors["sector"],
                y=top_sectors["change_pct"],
                marker_color=bar_colors,
                text=[f"{v:+.2f}%" for v in top_sectors["change_pct"]],
                textposition="outside",
            )
        )
        fig_sector.update_layout(
            title=f"行业涨跌幅 Top {top_n}（{industry} 高亮显示）",
            xaxis_tickangle=-45,
            yaxis_title="涨跌幅 %",
            height=420,
            margin=dict(l=40, r=20, t=50, b=100),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_sector, use_container_width=True)

        # 行业摘要
        sector_row = sector_df[sector_df["sector"].astype(str).str.contains(industry, na=False)]
        if not sector_row.empty:
            sector_chg = float(sector_row.iloc[0]["change_pct"])
            avg_chg = float(sector_df["change_pct"].mean())
            delta = sector_chg - avg_chg
            sc1, sc2 = st.columns(2)
            with sc1:
                st.metric(f"{industry} 今日涨跌", f"{sector_chg:+.2f}%")
            with sc2:
                st.metric("相对全市场平均", f"{delta:+.2f}%", delta=f"{delta:+.2f}%")
        else:
            st.info("未在行业列表中精确匹配到当前股票行业。")
    else:
        st.info("暂无行业数据，无法横向对比。")

    # ═══════════════════════════════════════════════════════════
    # 大盘主线判断
    # ═══════════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("🚩 大盘主线判断")
    rank = _sector_rank(sector_df, industry) if industry != "—" else None
    sector_total = len(sector_df) if not sector_df.empty else 0

    if rank is not None and sector_total > 0:
        is_main = rank <= 5
        main_html = (
            f'<div style="padding:14px 18px;border-radius:10px;'
            f'background:rgba(16,185,129,0.12);border-left:4px solid {UP_COLOR};'
            f'color:{"#e2e8f0" if dark else "#064e3b"};font-size:15px;">'
            f'✅ <b>{industry}</b> 今日行业排名 <b>#{rank} / {sector_total}</b>，'
            f'处于市场主线前列，资金关注度较高。</div>'
        ) if is_main else (
            f'<div style="padding:14px 18px;border-radius:10px;'
            f'background:rgba(245,158,11,0.12);border-left:4px solid #f59e0b;'
            f'color:{"#e2e8f0" if dark else "#78350f"};font-size:15px;">'
            f'⚠️ <b>{industry}</b> 今日行业排名 <b>#{rank} / {sector_total}</b>，'
            f'暂未进入主线 Top5，建议结合题材与资金面综合判断。</div>'
        )
        st.markdown(main_html, unsafe_allow_html=True)

        # Top5 行业列表
        with st.expander("查看行业排名 Top10", expanded=False):
            top10 = sector_df.sort_values("change_pct", ascending=False).head(10).reset_index(drop=True)
            top10["排名"] = top10.index + 1
            display = top10[["排名", "sector", "change_pct"]].rename(
                columns={"sector": "行业", "change_pct": "涨跌幅"}
            )
            st.dataframe(
                display,
                use_container_width=True,
                column_config={"涨跌幅": st.column_config.NumberColumn(format="%.2f%%")},
                hide_index=True,
            )
    else:
        st.info("暂无行业排名，无法判断主线地位。")

    # ═══════════════════════════════════════════════════════════
    # 综合评估
    # ═══════════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("🎯 综合评估")
    score, reasons_html = _composite_score(price, pe_ttm, p_5y if hist_df is not None else None, rank, sector_total, market_cap)

    # 评分颜色
    if score >= 75:
        score_color = UP_COLOR
        score_label = "较强"
    elif score >= 50:
        score_color = "#f59e0b"
        score_label = "中等"
    else:
        score_color = DOWN_COLOR
        score_label = "偏弱"

    sc1, sc2 = st.columns([0.25, 0.75])
    with sc1:
        st.markdown(
            f'<div style="text-align:center;padding:20px 10px;border-radius:12px;'
            f'background:{"rgba(26,26,46,0.6)" if dark else "#f3f4f6"};'
            f'border:1px solid {"rgba(255,255,255,0.08)" if dark else "#e5e7eb"};">'
            f'<div style="font-size:13px;opacity:.8;">综合评分</div>'
            f'<div style="font-size:48px;font-weight:800;color:{score_color};">{score}</div>'
            f'<div style="font-size:14px;color:{score_color};font-weight:600;">{score_label}</div></div>',
            unsafe_allow_html=True,
        )
    with sc2:
        st.markdown(
            f'<div style="padding:14px 18px;border-radius:10px;'
            f'background:{"rgba(26,26,46,0.4)" if dark else "#f9fafb"};'
            f'border:1px solid {"rgba(255,255,255,0.08)" if dark else "#e5e7eb"};'
            f'font-size:14px;line-height:1.8;">{reasons_html}</div>',
            unsafe_allow_html=True,
        )

    # 估值摘要
    st.markdown("---")
    st.subheader("📊 估值摘要")
    v1, v2, v3 = st.columns(3)
    with v1:
        st.metric("PE(TTM)", f"{pe_ttm:.2f}" if pe_ttm else "—", help="市盈率，越低通常代表估值越低")
    with v2:
        st.metric("PE 状态", _pe_status(pe_ttm))
    with v3:
        st.metric("总市值", f"¥{market_cap:.1f}亿" if market_cap else "—", help="单位：亿元人民币")

    # 个股跳转
    st.markdown("---")
    if st.button("🔍 查看该股票详细 K 线与技术面 →", type="primary", use_container_width=True):
        st.query_params["pick_stock"] = code
        safe_switch_page("pages/1_股票选取.py")
else:
    st.info("请在上方选择一只股票开始分析。")
