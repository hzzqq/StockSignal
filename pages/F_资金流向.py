"""
页面 F：资金流向监控
展示北向资金、行业板块资金流向、大盘主力资金净流入历史，以及单只个股的主力资金动向。
数据层见 modules/fundflow.py（已确保经本地代理 + 关闭证书校验访问东方财富/同花顺源）。
A股配色：资金净流入=红，净流出=绿（与红涨绿跌一致）。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.fundflow import (
    get_industry_fund_flow, get_northbound_fund_flow,
    get_market_fund_flow, get_individual_fund_flow,
    get_market_wide_snapshot,
)
from modules.fetcher import StockFetcher
from modules.search_ui import stock_search_input

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

apply_page_config(page_title="资金流向", page_icon="🌊", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

# A股配色：净流入红、净流出绿
UP = "#ee2a2a"      # 红（流入 / 涨）
DOWN = "#1aa260"    # 绿（流出 / 跌）

st.title("🌊 资金流向监控")
st.caption("北向资金 · 行业板块资金流向 · 大盘主力净流入 · 个股主力资金动向。数据来源：东方财富/同花顺（经本地代理）。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()

# 性能优化：首次进入并行预取行业/北向/大盘三类全市场资金流，
# 填充各自缓存后三个 fragment 直接命中缓存（秒开）；后续脚本重跑命中缓存亦近乎瞬时。
try:
    get_market_wide_snapshot()
except Exception:
    pass


def _in_trading_hours():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return (570 <= hm <= 690) or (780 <= hm <= 900)


def _fig_layout(dark_mode):
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=50, r=20, t=30, b=30), hovermode="x unified",
    )
    if dark_mode:
        base.update(font=dict(color="#e6e6e6"),
                    xaxis=dict(gridcolor="#2a2a3a"), yaxis=dict(gridcolor="#2a2a3a"))
    else:
        base.update(font=dict(color="#1a1a1a"),
                    xaxis=dict(gridcolor="#ececec"), yaxis=dict(gridcolor="#ececec"))
    return base


def _section_title(text, accent="#2b8aef"):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0 10px;">'
        f'<span style="width:4px;height:18px;background:{accent};border-radius:2px;display:inline-block;"></span>'
        f'<span style="font-size:16px;font-weight:600;">{text}</span></div>',
        unsafe_allow_html=True,
    )


def _fmt_yi(x):
    try:
        x = float(x)
    except Exception:
        return "—"
    if abs(x) >= 1e8:
        return f"{x/1e8:.2f}亿"
    if abs(x) >= 1e4:
        return f"{x/1e4:.1f}万"
    return f"{x:.0f}"


# ───────────────────────── 北向资金 ─────────────────────────
@st.fragment
def fragment_northbound():
    _section_title("🧭 北向资金（沪股通 / 深股通）", accent="#7c5cff")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="nb_auto")
    try:
        nb = get_northbound_fund_flow()
    except Exception as e:
        st.error(f"北向资金加载失败：{e}")
        return
    if not nb or not nb.get("boards"):
        st.info("暂无北向资金数据。")
        return
    total = nb.get("total_inflow")
    sh = nb.get("sh_inflow")
    sz = nb.get("sz_inflow")
    avail = nb.get("northbound_net_available")
    cols = st.columns(4)
    if avail:
        with cols[0]:
            st.metric("北向净流入(实时)", _fmt_yi(total) if total is not None else "—",
                      help="沪股通 + 深股通 当日资金净流入合计")
        with cols[1]:
            st.metric("沪股通(实时)", _fmt_yi(sh) if sh is not None else "—")
        with cols[2]:
            st.metric("深股通(实时)", _fmt_yi(sz) if sz is not None else "—")
        with cols[3]:
            st.metric("交易日", nb.get("trade_date") or "—")
    else:
        # 实时未披露：展示「最近一次真实披露」历史值与累计净买入，避免整块空白
        with cols[0]:
            st.metric("北向净流入(最近真实披露)", _fmt_yi(nb.get("last_net_buy")),
                      help=f"交易所自 2024-08-16 起停披露实时净买额，此为停披露前最后真实值"
                           f"（{nb.get('last_net_buy_date') or '—'}）")
        with cols[1]:
            st.metric("历史累计净买入", _fmt_yi(nb.get("cumulative")),
                      help=f"北向资金历史累计净买入（截至 {nb.get('cumulative_date') or '—'}）")
        sh_board = next((b for b in nb["boards"] if str(b.get("板块")) == "沪股通"), None)
        sz_board = next((b for b in nb["boards"] if str(b.get("板块")) == "深股通"), None)
        with cols[2]:
            if sh_board:
                st.metric("沪股通 涨/跌家数", f"{sh_board.get('上涨数','—')}/{sh_board.get('下跌数','—')}",
                          help="沪股通成分股实时涨跌家数（真实数据）")
            else:
                st.metric("沪股通", "—")
        with cols[3]:
            if sz_board:
                st.metric("深股通 涨/跌家数", f"{sz_board.get('上涨数','—')}/{sz_board.get('下跌数','—')}",
                          help="深股通成分股实时涨跌家数（真实数据）")
            else:
                st.metric("深股通", "—")
    detail = []
    for b in nb["boards"]:
        detail.append({
            "板块": b.get("板块"),
            "资金方向": b.get("资金方向"),
            "成交净买额": b.get("成交净买额"),
            "资金净流入": b.get("资金净流入"),
            "上涨数": b.get("上涨数"),
            "下跌数": b.get("下跌数"),
            "指数涨跌幅": b.get("指数涨跌幅"),
        })
    df = pd.DataFrame(detail)
    if not df.empty:
        df["资金净流入"] = pd.to_numeric(df["资金净流入"], errors="coerce")
        df["指数涨跌幅"] = pd.to_numeric(df["指数涨跌幅"], errors="coerce")
        st.dataframe(df, use_container_width=True, hide_index=True)
    # 北向净买额数据源说明（东方财富自 2024-08 起停止披露实时北向净买额）
    if not avail:
        st.info("⚠️ **北向资金实时净买额已停披露**：交易所自 2024-08-16 起不再实时公布沪股通/深股通/北向合计净买额，"
                "东方财富接口长期返回 0。上方「最近真实披露」为停披露前最后真实值，「历史累计净买入」为累计值；"
                "下方表格中的**涨跌家数 / 指数涨跌幅 / 港股通南向净买额** 仍为实时真实数据。",
                icon="ℹ️")
    else:
        if df["资金净流入"].abs().sum() == 0:
            st.caption("提示：当前交易日北向资金净买额为 0（休市 / 尚未披露）。")


# ───────────────────────── 行业板块资金流向 ─────────────────────────
@st.fragment
def fragment_industry():
    _section_title("🏭 行业板块资金流向", accent="#2b8aef")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="ind_auto")
    try:
        df = get_industry_fund_flow()
    except Exception as e:
        st.error(f"行业资金流向加载失败：{e}")
        return
    if df is None or df.empty:
        st.info("暂无行业资金流向数据。")
        return
    df["净额"] = pd.to_numeric(df["净额"], errors="coerce")
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df = df.sort_values("净额", ascending=False).reset_index(drop=True)

    top = df.head(15).copy()
    colors = [UP if v >= 0 else DOWN for v in top["净额"]]
    fig = go.Figure(go.Bar(
        x=top["行业"], y=top["净额"], marker_color=colors,
        hovertemplate="%{x}<br>净额：%{y:.2f}亿<extra></extra>",
    ))
    fig.update_layout(**_fig_layout(dark), title="净流入 TOP15 行业（亿元）", height=360)
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "净额": st.column_config.NumberColumn("净额(亿)", format="%.2f"),
            "涨跌幅": st.column_config.NumberColumn("涨跌幅%", format="%.2f"),
            "流入资金": st.column_config.NumberColumn("流入(亿)", format="%.2f"),
            "流出资金": st.column_config.NumberColumn("流出(亿)", format="%.2f"),
        },
    )


# ───────────────────────── 大盘主力资金净流入 ─────────────────────────
@st.fragment
def fragment_market():
    _section_title("📈 大盘主力资金净流入（近 30 日）", accent="#10b981")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="mkt_auto")
    try:
        df = get_market_fund_flow(days=30)
    except Exception as e:
        st.error(f"大盘资金流向加载失败：{e}")
        return
    if df is None or df.empty:
        st.info("暂无大盘资金流向数据。")
        return
    df["主力净流入-净额"] = pd.to_numeric(df["主力净流入-净额"], errors="coerce")
    df["上证-涨跌幅"] = pd.to_numeric(df["上证-涨跌幅"], errors="coerce")
    df["超大单净流入-净额"] = pd.to_numeric(df["超大单净流入-净额"], errors="coerce")
    df["大单净流入-净额"] = pd.to_numeric(df["大单净流入-净额"], errors="coerce")
    df = df.dropna(subset=["主力净流入-净额"])
    if df.empty:
        st.info("暂无有效数据。")
        return
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["日期"], y=df["主力净流入-净额"], name="主力净流入(亿)",
        marker_color=[UP if v >= 0 else DOWN for v in df["主力净流入-净额"]],
        hovertemplate="%{x}<br>主力净流入：%{y:.2f}亿<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["日期"], y=df["上证-涨跌幅"], name="上证涨跌幅%", yaxis="y2",
        mode="lines+markers", line=dict(color="#f5a623", width=2),
        hovertemplate="%{x}<br>上证涨跌幅：%{y:.2f}%<extra></extra>",
    ))
    _layout = {k: v for k, v in _fig_layout(dark).items() if k != "margin"}
    fig.update_layout(
        **_layout, height=360,
        title="主力净流入（柱）与上证涨跌幅（线）",
        yaxis2=dict(title="涨跌幅%", overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=60, t=50, b=90),
        legend=dict(orientation="h", yanchor="top", y=-0.25, x=0.5, xanchor="center"),
    )
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ───────────────────────── 个股主力资金 ─────────────────────────
@st.fragment
def fragment_individual():
    _section_title("🔍 个股主力资金动向", accent="#ef5da8")
    code = stock_search_input(label="选择股票", key="ff_stock", default="600519")
    if not code:
        st.info("请选择一只股票查看主力资金。")
        return
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="indv_auto")
    try:
        r = get_individual_fund_flow(code)
    except Exception as e:
        st.error(f"个股资金加载失败：{e}")
        return
    if r.get("source") == "none" or r.get("main_net") is None:
        st.warning("该股主力资金数据暂不可用（接口受限或缺少历史）。")
        return
    name = fetcher.get_name_only(code)
    st.markdown(f"**{name}** `{code}` ｜ 数据日期：{r.get('latest_date')} ｜ "
                f"来源：{'实时(东方财富)' if r.get('source')=='akshare' else '估算(量价模型)'}")
    cols = st.columns(3)
    is_estimate = r.get("source") == "estimate"
    with cols[0]:
        st.metric("主力净流入", _fmt_yi(r.get("main_net")),
                  delta=f"{r.get('main_net_pct')}% 净占比" if r.get("main_net_pct") is not None else None)
    with cols[1]:
        st.metric("超大单净流入" + ("(估算)" if is_estimate else ""), _fmt_yi(r.get("super_net")))
    with cols[2]:
        st.metric("大单净流入" + ("(估算)" if is_estimate else ""), _fmt_yi(r.get("big_net")))
    if is_estimate:
        st.caption("⚠️ 当前为量价模型估算值（Chaikin 风格主力净流入），超大单/大单按经验比例拆分，仅反映近期量价博弈方向，非交易所逐笔主力数据。")
    elif r.get("source") == "akshare":
        st.caption("数据来源：东方财富实时资金流。")


# ───────────────────────── 页面主体 ─────────────────────────
fragment_northbound()
st.markdown("---")
fragment_industry()
st.markdown("---")
fragment_market()
st.markdown("---")
fragment_individual()
