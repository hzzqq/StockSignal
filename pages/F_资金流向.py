"""
页面 F：资金流向监控
展示北向资金、行业板块资金流向、大盘主力资金净流入历史，以及单只个股的主力资金动向。
数据层见 modules/fundflow.py（已确保经本地代理 + 关闭证书校验访问东方财富/同花顺源）。
A股配色：资金净流入=红，净流出=绿（与红涨绿跌一致）。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.page_guard import safe_fragment
from modules.fundflow import (
    get_industry_fund_flow, get_northbound_fund_flow,
    get_market_fund_flow, get_individual_fund_flow,
)
from modules.margin_trading import (
    get_margin_trading_data, plot_margin_trend, get_latest_margin_summary,
)
from modules.linear_trends import (
    get_northbound_history_series, plot_northbound_history,
    get_individual_fund_flow_series, plot_individual_series,
    get_index_series, plot_index_series,
    get_market_cumulative_series, plot_market_cumulative,
    get_industry_index_series, get_etf_series,
    plot_normalized_multi, ETF_NAMES_MAP,
    to_trend_csv, plot_correlation_heatmap, _slice_date_range,
)
from modules.fetcher import StockFetcher
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, UP, DOWN, is_trading_now, _fig_layout, _section_title, _fmt_yi, _trend_controls

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


st.title("🌊 资金流向监控")
st.caption("北向资金 · 行业板块资金流向 · 大盘主力净流入 · 个股主力资金动向。数据来源：东方财富/同花顺（经本地代理）。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


# 加法式性能优化（第十四批）：个股资金流接口在 60s 自动刷新下每次都重新请求网络，
# 叠加重试/解析开销；用 cache_data 缓存 5 分钟，刷新周期内复用，显著降低重复请求。
@st.cache_data(show_spinner=False, ttl=300)
def _cached_individual_fund_flow(code: str):
    return get_individual_fund_flow(code)


@st.cache_data(show_spinner=False, ttl=300)
def _cached_individual_series(code: str, days: int = 60):
    return get_individual_fund_flow_series(code, days=days)










# ───────────────────────── 北向资金 ─────────────────────────
@safe_fragment("北向资金")
def fragment_northbound():
    _section_title("🧭 北向资金（沪股通 / 深股通）", accent="#7c5cff")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="nb_auto")
    try:
        nb = get_northbound_fund_flow()
    except Exception as e:
        st.error(f"北向资金加载失败：{e}")
        return
    if not nb or not nb.get("boards"):
        _empty_info("暂无北向资金数据。")
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
        inflow_sum = df["资金净流入"].abs().sum()
        if pd.notna(inflow_sum) and inflow_sum == 0:
            st.caption("提示：当前交易日北向资金净买额为 0（休市 / 尚未披露）。")

    # 北向资金历史趋势（线性表达）：当日净买额 + 历史累计净买额
    try:
        hist = get_northbound_history_series()
    except Exception as e:
        hist = None
        st.warning(f"北向历史序列加载失败：{e}")
    if hist is not None and not hist.empty:
        dr, ma, _s, _m, ma_type = _trend_controls("nb", days_default=365, preset_default="全部")
        st.plotly_chart(plot_northbound_history(hist, dark_mode=dark, date_range=dr, ma_periods=ma,
                                                ma_type=ma_type, show_baseline=True),
                        use_container_width=True, config={"displayModeBar": False})
        st.caption("📈 北向资金历史趋势（线性表达）：紫色面积=当日成交净买额，蓝色线=历史累计净买额。"
                   "交易所自 2024-08-16 起停止披露实时净买额，故近期序列末端可能空白或持平。"
                   "可用上方「区间 / 均线叠加」交互筛选。")


# ───────────────────────── 行业板块资金流向 ─────────────────────────
@safe_fragment("行业板块资金流向")
def fragment_industry():
    _section_title("🏭 行业板块资金流向", accent="#2b8aef")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="ind_auto")
    try:
        df = get_industry_fund_flow()
    except Exception as e:
        st.error(f"行业资金流向加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无行业资金流向数据。")
        return
    # 字段完整性兜底：数据源字段名变更 / 网络异常时避免 KeyError 拖垮整块
    _need = ["行业", "净额", "涨跌幅"]
    if not all(c in df.columns for c in _need):
        st.info("行业资金流向数据字段不完整，暂无法展示（接口字段变更或网络异常）。")
        return
    df["净额"] = pd.to_numeric(df["净额"], errors="coerce")
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df = df.sort_values("净额", ascending=False).reset_index(drop=True)

    # 净流入 TOP 概览卡
    d2 = df.dropna(subset=["净额"])
    if not d2.empty:
        top_in, top_out = d2.iloc[0], d2.iloc[-1]
        oc1, oc2, oc3, oc4 = st.columns(4)
        with oc1:
            st.metric("最强净流入", f"{top_in['行业']}", help=f"净额 {top_in['净额']:.2f} 亿（红=流入）")
        with oc2:
            st.metric("最强净流出", f"{top_out['行业']}", help=f"净额 {top_out['净额']:.2f} 亿（绿=流出）")
        with oc3:
            st.metric("净流入行业", f"{int((d2['净额'] > 0).sum())}", help="净额为正（红）的行业数")
        with oc4:
            st.metric("净流出行业", f"{int((d2['净额'] < 0).sum())}", help="净额为负（绿）的行业数")
        st.caption("📌 概览：红=主力净流入行业，绿=净流出行业；逐日资金流以 industry_fund_flow 为准。")
    else:
        st.info("行业净流入概览暂不可用：当前行业资金流净额数据为空（网络/代理受限或数据源暂未接入）。")

    top = df.head(15).copy()
    try:
        colors = [UP if v >= 0 else DOWN for v in top["净额"]]
        fig = go.Figure(go.Bar(
            x=top["行业"], y=top["净额"], marker_color=colors,
            hovertemplate="%{x}<br>净额：%{y:.2f}亿<extra></extra>",
        ))
        fig.update_layout(**_fig_layout(dark), title="净流入 TOP15 行业（亿元）", height=360)
        fig.update_xaxes(tickangle=-45)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception as e:
        st.warning(f"行业净流入 TOP15 图表渲染失败：{e}")

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
@safe_fragment("大盘主力资金")
def fragment_market():
    _section_title("📈 大盘主力资金净流入（近 30 日）", accent="#10b981")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="mkt_auto")
    try:
        df = get_market_fund_flow(days=30)
    except Exception as e:
        st.error(f"大盘资金流向加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无大盘资金流向数据。")
        return
    _need = ["日期", "主力净流入-净额", "上证-涨跌幅"]
    if not all(c in df.columns for c in _need):
        _miss = [c for c in _need if c not in df.columns]
        st.info(f"大盘资金流向数据字段不完整（缺少：{', '.join(_miss)}），暂无法展示（接口字段变更或网络异常）。")
        return
    try:
        df["主力净流入-净额"] = pd.to_numeric(df["主力净流入-净额"], errors="coerce")
        df["上证-涨跌幅"] = pd.to_numeric(df["上证-涨跌幅"], errors="coerce")
        df["超大单净流入-净额"] = pd.to_numeric(df["超大单净流入-净额"], errors="coerce")
        df["大单净流入-净额"] = pd.to_numeric(df["大单净流入-净额"], errors="coerce")
        df = df.dropna(subset=["主力净流入-净额"])
        if df.empty:
            _empty_info("暂无有效数据。")
            return
    except Exception as e:
        st.warning(f"大盘资金流向数据解析失败：{e}")
        return
    try:
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
    except Exception as e:
        st.warning(f"大盘资金净流入图表渲染失败：{e}")

    # 大盘主力资金累计净流入（线性表达：累计面积线 + 当日细线）
    try:
        cum = get_market_cumulative_series(days=60)
    except Exception as e:
        cum = None
        st.warning(f"大盘累计资金加载失败：{e}")
    if cum is not None and not cum.empty:
        dr, ma, _s, _m, ma_type = _trend_controls("mkt_cum", days_default=60, preset_default="近60天")
        st.plotly_chart(plot_market_cumulative(cum, dark_mode=dark, date_range=dr, ma_periods=ma,
                                               ma_type=ma_type, show_baseline=True),
                        use_container_width=True, config={"displayModeBar": False})
        st.caption("📈 大盘主力资金累计净流入（线性表达）：面积线为累计值，橙色细线为逐日主力净流入。"
                   "连续红（正）表示主力持续净流入，绿（负）表示持续净流出。可用上方「区间 / 均线叠加」交互筛选。")


# ───────────────────────── 融资融券趋势（融资买入额 & 融资余额） ─────────────────────────
@safe_fragment("融资融券趋势")
def fragment_margin_trading():
    _section_title("📊 融资融券趋势（融资买入额 & 三大指数）", accent="#f59e0b")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="margin_auto")

    metric = st.radio(
        "指标", ["rzmr", "rzye"],
        format_func=lambda x: "融资买入额" if x == "rzmr" else "融资余额",
        horizontal=True, key="margin_metric",
    )

    try:
        df = get_margin_trading_data(days=180)
    except Exception as e:
        st.error(f"融资融券数据加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无融资融券数据。")
        return

    try:
        summary = get_latest_margin_summary() or {}
    except Exception as e:
        summary = {}
        st.warning(f"融资融券摘要加载失败：{e}")
    cols = st.columns(4)
    with cols[0]:
        st.metric("融资买入额(最新)", f"{summary.get('total_rzmr_yi'):.2f}亿" if summary.get('total_rzmr_yi') is not None else "—",
                  delta=f"{summary.get('rzmr_change_yi'):+.2f}亿" if summary.get('rzmr_change_yi') is not None else None)
    with cols[1]:
        st.metric("融资余额(最新)", f"{summary.get('total_rzye_yi'):.2f}亿" if summary.get('total_rzye_yi') is not None else "—",
                  delta=f"{summary.get('rzye_change_yi'):+.2f}亿" if summary.get('rzye_change_yi') is not None else None)
    with cols[2]:
        st.metric("沪市买入额", f"{summary.get('sh_rzmr_yi'):.2f}亿" if summary.get('sh_rzmr_yi') is not None else "—")
    with cols[3]:
        st.metric("深市买入额", f"{summary.get('sz_rzmr_yi'):.2f}亿" if summary.get('sz_rzmr_yi') is not None else "—")

    try:
        fig = plot_margin_trend(df, dark_mode=dark, metric=metric)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception as e:
        st.warning(f"融资融券趋势图渲染失败：{e}")
    st.caption("数据来源：东方财富融资融券（沪+深），指数叠加辅助判断杠杆资金与大盘节奏关系。"
               "北交所暂无公开宏观融资融券序列，故合计未包含 BJ。")



# （五维归一化子图面板已迁至独立模块 pages/H_市场驱动力.py）


# ───────────────────────── 个股主力资金 ─────────────────────────
@safe_fragment("个股主力资金")
def fragment_individual():
    _section_title("🔍 个股主力资金动向", accent="#ef5da8")
    code = stock_search_input(
        label="选择股票",
        key="ff_stock",
        default="600519",
        help="输入代码或名称（如 600519 / 贵州茅台）搜索个股，查看其主力资金动向",
    )
    if not code:
        st.info("请选择一只股票查看主力资金。")
        st.caption("💡 在上方输入框输入代码或名称（如 `600519` / `贵州茅台`），支持模糊搜索与拼音首字母。")
        if st.button("🔍 使用示例股（贵州茅台 600519）", key="ff_use_example"):
            st.session_state["ff_stock_confirmed"] = "600519"
            st.session_state["ff_stock_query"] = "600519"
        return
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="indv_auto")
    try:
        r = _cached_individual_fund_flow(code)
    except Exception as e:
        st.error(f"个股资金加载失败：{e}")
        return
    if r.get("source") == "none" or r.get("main_net") is None:
        st.warning("该股主力资金数据暂不可用（接口受限或缺少历史）。")
        return
    try:
        name = fetcher.get_name_only(code) or code
    except Exception:
        name = code
    st.markdown(f"**{name}** `{code}` ｜ 数据日期：{r.get('latest_date') or '—'} ｜ "
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

    # 个股主力资金逐日趋势（线性表达）
    try:
        sdf = _cached_individual_series(code, days=60)
    except Exception as e:
        sdf = None
        st.warning(f"个股资金趋势加载失败：{e}")
    if sdf is not None and not sdf.empty and sdf.attrs.get("source") != "none":
        dr, ma, _s, _m, ma_type = _trend_controls("indv", days_default=60, preset_default="近60天")
        # 加法式渲染兜底：个股资金序列可能含异常值/缺列，plotly 渲染失败不应拖垮整个 fragment
        try:
            st.plotly_chart(plot_individual_series(sdf, name=name, code=code, dark_mode=dark,
                                                   date_range=dr, ma_periods=ma,
                                                   ma_type=ma_type, show_baseline=True),
                            use_container_width=True, config={"displayModeBar": False})
        except Exception as _e:
            st.warning(f"个股资金趋势图渲染失败：{_e}")
        if sdf.attrs.get("source") == "estimate":
            st.caption("📈 个股主力资金逐日趋势（线性表达，量价模型估算）：面积线=主力净流入，"
                       "超大单/大单为经验拆分（图例可切换）。仅反映近期量价博弈方向。")
        else:
            st.caption("📈 个股主力资金逐日趋势（线性表达，东方财富真实数据）：面积线=主力净流入，"
                       "超大单/大单可在图例展开。")


# ───────────────────────── 三大指数走势对比（线性表达） ─────────────────────────
@safe_fragment("指数走势对比")
def fragment_index_trend():
    _section_title("📊 三大指数走势对比（归一化）", accent="#2b8aef")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="idx_auto")
    try:
        idx = get_index_series(days=180)
    except Exception as e:
        st.error(f"指数走势加载失败：{e}")
        return
    if idx is None or idx.empty:
        _empty_info("暂无指数走势数据。")
        return
    dr, ma, _s, _m, ma_type = _trend_controls("idx", days_default=180, preset_default="近180天")
    fig = plot_index_series(idx, dark_mode=dark, date_range=dr, ma_periods=ma, ma_type=ma_type)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("📈 三大指数走势对比（线性表达，归一化起点=100）：用于横向比较上证 / 深证成指 / 创业板指"
               "的相对强弱，而非绝对点位。可用上方「区间 / 均线叠加」交互筛选。")


# ───────────────────────── 行业板块指数价格趋势（线性表达） ─────────────────────────
@safe_fragment("行业指数走势")
def fragment_industry_trend():
    _section_title("🏭 行业板块指数走势对比（归一化）", accent="#2b8aef")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="indt_auto")
    try:
        ind = get_industry_index_series(top_n=8, days=120)
    except Exception as e:
        st.error(f"行业指数走势加载失败：{e}")
        return
    if ind is None or ind.empty:
        _empty_info("暂无行业指数走势数据（接口受限或网络不可用）。")
        return
    series_options = [(c, c) for c in ind.columns if c != "date"]
    dr, ma, sel, mode, ma_type = _trend_controls(
        "indt", days_default=120, preset_default="近90天",
        series_options=series_options, mode_toggle=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        show_cross = st.checkbox("标注金叉/死叉", value=False, key="indt_cross",
                                 help="需同时叠加至少两条均线")
    with c2:
        show_dd = st.checkbox("标注最大回撤", value=False, key="indt_dd")
    fig = plot_normalized_multi(
        ind, title="行业板块指数走势对比（归一化，起点=100）",
        dark_mode=dark, date_range=dr, ma_periods=ma, selected=sel,
        mode=mode, ma_type=ma_type, show_baseline=True,
        show_cross=show_cross, show_drawdown=show_dd,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="indt_norm")
    # 数据表联动（随区间 / 序列筛选）
    with st.expander("📋 数据表（随区间 / 序列联动）"):
        tbl = _slice_date_range(ind, dr)
        if sel:
            keep = [c for c in sel if c in tbl.columns]
            tbl = tbl[["date"] + keep] if keep else tbl[["date"]]
        st.dataframe(tbl, use_container_width=True, hide_index=True)
    # 导出 CSV
    csv = to_trend_csv(ind, names_map=None, selected=sel, date_range=dr)
    st.download_button("⬇️ 导出 CSV", data=csv, file_name="行业指数走势.csv", mime="text/csv")
    # 相关性热力图
    st.plotly_chart(plot_correlation_heatmap(ind, names_map=None, selected=sel,
                                             date_range=dr, dark_mode=dark),
                    use_container_width=True, config={"displayModeBar": False}, key="indt_corr")
    st.caption("📈 行业板块指数走势（线性表达，归一化起点=100）：行业板块无逐日资金流时间序列 API，"
               "故以**行业指数日线收盘价**做相对强弱对比。区间预设 / 均线（SMA·EMA）/ 序列多选 / 原始价格切换"
               " / 金叉死叉 / 最大回撤 均可交互；下方数据表与相关性热力图随筛选联动。")


# ───────────────────────── ETF 价格趋势（线性表达） ─────────────────────────
@safe_fragment("ETF 价格走势")
def fragment_etf_trend():
    _section_title("🧩 ETF 价格走势对比（归一化）", accent="#16c2c2")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, limit=200, key="etf_auto")
    try:
        etf = get_etf_series(days=180)
    except Exception as e:
        st.error(f"ETF 走势加载失败：{e}")
        return
    if etf is None or etf.empty:
        _empty_info("暂无 ETF 走势数据（接口受限或网络不可用）。")
        return
    series_options = [(c, ETF_NAMES_MAP.get(c, c)) for c in etf.columns if c != "date"]
    dr, ma, sel, mode, ma_type = _trend_controls(
        "etf", days_default=180, preset_default="近180天",
        series_options=series_options, mode_toggle=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        show_cross = st.checkbox("标注金叉/死叉", value=False, key="etf_cross",
                                 help="需同时叠加至少两条均线")
    with c2:
        show_dd = st.checkbox("标注最大回撤", value=False, key="etf_dd")
    fig = plot_normalized_multi(
        etf, names_map=ETF_NAMES_MAP,
        title="ETF 价格走势对比（归一化，起点=100）",
        dark_mode=dark, date_range=dr, ma_periods=ma, selected=sel,
        mode=mode, ma_type=ma_type, show_baseline=True,
        show_cross=show_cross, show_drawdown=show_dd,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="etf_norm")
    # 数据表联动
    with st.expander("📋 数据表（随区间 / 序列联动）"):
        tbl = _slice_date_range(etf, dr)
        if sel:
            keep = [c for c in sel if c in tbl.columns]
            tbl = tbl[["date"] + keep] if keep else tbl[["date"]]
        st.dataframe(tbl, use_container_width=True, hide_index=True)
    # 导出 CSV
    csv = to_trend_csv(etf, names_map=ETF_NAMES_MAP, selected=sel, date_range=dr)
    st.download_button("⬇️ 导出 CSV", data=csv, file_name="ETF价格走势.csv", mime="text/csv")
    # 相关性热力图
    st.plotly_chart(plot_correlation_heatmap(etf, names_map=ETF_NAMES_MAP, selected=sel,
                                             date_range=dr, dark_mode=dark),
                    use_container_width=True, config={"displayModeBar": False}, key="etf_corr")
    st.caption("📈 ETF 价格走势（线性表达，归一化起点=100）：宽基（沪深300/中证500/创业板）+ 行业"
               "（军工/医药/新能源）+ 跨境（纳指/恒生科技）。区间预设 / 均线（SMA·EMA）/ 序列多选 / 原始价格切换"
               " / 金叉死叉 / 最大回撤 均可交互；下方数据表与相关性热力图随筛选联动。")


# ───────────────────────── 页面主体 ─────────────────────────
fragment_northbound()
st.markdown("---")
fragment_industry()
st.markdown("---")
fragment_market()
st.markdown("---")
fragment_margin_trading()
st.markdown("---")
fragment_individual()
st.markdown("---")
fragment_index_trend()
st.markdown("---")
fragment_industry_trend()
st.markdown("---")
fragment_etf_trend()
