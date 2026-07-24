"""
页面 H：自选股组合收益跟踪
基于仓位管理中的持仓，构建组合历史净值曲线（按剩余股数加权），与沪深300基准对比，
展示累计收益、个股贡献、最大回撤。数据层复用 modules/portfolio.PortfolioManager 与
modules/fetcher.StockFetcher.get_daily（已验证可用）。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.portfolio import PortfolioManager
from modules.fetcher import StockFetcher

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

from modules.page_guard import safe_fragment
from modules.page_widgets import _empty_info, UP, DOWN, _fig_layout, _section_title

apply_page_config(page_title="组合收益", page_icon="📊", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)


st.title("📊 自选股组合收益跟踪")
st.caption("基于「仓位管理」中的持仓，按剩余股数加权构建组合净值曲线，对比沪深300基准。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()
pm = PortfolioManager()






def _build_portfolio_series(positions):
    """返回 (portfolio_index: Series, bench_index: Series|None, start_date)。"""
    if positions is None or positions.empty:
        return None, None, None
    positions = positions.copy()
    positions["buy_date"] = pd.to_datetime(positions["buy_date"], errors="coerce")
    positions = positions.dropna(subset=["buy_date"])
    if positions.empty:
        return None, None, None
    start = positions["buy_date"].min()
    start_str = (start - timedelta(days=5)).strftime("%Y-%m-%d")
    end_str = datetime.now().strftime("%Y-%m-%d")

    def _fetch_position_series(ticker, remaining, s_start, s_end):
        """单只持仓的日线价值序列（线程安全：不修改外部可变状态，仅返回结果字典）。"""
        out = {}
        try:
            df = fetcher.get_daily(ticker, start=s_start, end=s_end)
            if df is None or df.empty or "close" not in df.columns:
                return out
            df = df.copy()
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                df = df.dropna(subset=["date"])
                df = df.set_index("date")
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            for d, c in df["close"].dropna().items():
                ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                out[ds] = float(c) * remaining
        except Exception:
            pass
        return out

    # 加法式性能优化：原实现按持仓逐只串行拉取日线（持仓多时明显变慢）。
    # 改用线程池并行取数；线程内不共享可变状态，结果在主线程统一 merge，线程安全。
    series = {}
    _tasks = []
    for _, row in positions.iterrows():
        ticker = str(row["ticker"]).zfill(6)
        remaining = int(row.get("remaining_shares", row.get("shares", 0)) or 0)
        if remaining <= 0:
            continue
        _tasks.append((ticker, remaining))
    if _tasks:
        with ThreadPoolExecutor(max_workers=min(8, len(_tasks))) as _ex:
            _futs = {_ex.submit(_fetch_position_series, t, r, start_str, end_str): t for t, r in _tasks}
            for _fut in as_completed(_futs):
                series.update(_fut.result())

    if not series:
        return None, None, start_str

    pdict = {d: sum(v.values()) for d, v in series.items()}
    pidx = pd.Series(pdict, name="组合").sort_index()
    pidx = pidx[pidx > 0]
    if len(pidx) < 2:
        return None, None, start_str
    pidx = pidx / pidx.iloc[0] * 100.0

    # 基准：沪深300
    bench = None
    try:
        bdf = fetcher.get_daily("000300", start=start_str, end=end_str)
        if bdf is not None and not bdf.empty and "close" in bdf.columns:
            bdf = bdf.copy()
            if "date" in bdf.columns:
                bdf["date"] = pd.to_datetime(bdf["date"], errors="coerce")
                bdf = bdf.dropna(subset=["date"]).set_index("date")
            bdf["close"] = pd.to_numeric(bdf["close"], errors="coerce")
            bser = bdf["close"].dropna()
            bser.index = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10] for d in bser.index]
            bser = bser.sort_index()
            bser = bser[bser > 0]
            if len(bser) >= 2:
                bench = bser / bser.iloc[0] * 100.0
                bench = bench.reindex(pidx.index).ffill().dropna()
    except Exception:
        bench = None

    return pidx, bench, start_str


def _max_drawdown(idxs: pd.Series):
    if idxs is None or len(idxs) < 2:
        return 0.0
    peak = idxs.cummax()
    dd = (idxs - peak) / peak * 100.0
    return float(dd.min())


# ───────────────────────── 主体 ─────────────────────────
@safe_fragment
def fragment_portfolio():
    _section_title("💼 组合净值与基准对比", accent="#2b8aef")
    if st_autorefresh is not None:
        st_autorefresh(interval=300000, limit=100, key="pf_auto")

    positions = pm.get_positions()
    if positions is None or positions.empty:
        _empty_info("暂无持仓。请先在「仓位管理」页添加持仓，再回来查看组合收益跟踪。")
        return

    with st.spinner("计算组合历史净值（拉取各持仓日线）…"):
        pidx, bench, start_str = _build_portfolio_series(positions)

    if pidx is None:
        st.warning("暂无法构建组合净值（持仓缺少可用历史行情）。请检查持仓买入日期与代码。")
        # 仍展示当前盈亏快照（best-effort，失败不影响上方提示）
        try:
            _show_pnl_snapshot()
        except Exception as e:
            st.warning(f"盈亏快照渲染失败：{e}")
        return

    total_ret = float(pidx.iloc[-1] - 100)
    mdd = _max_drawdown(pidx)
    cols = st.columns(4)
    with cols[0]:
        st.metric("组合累计收益", f"{total_ret:+.2f}%")
    with cols[1]:
        st.metric("最大回撤", f"{mdd:.2f}%")
    with cols[2]:
        bench_ret = float(bench.iloc[-1] - 100) if bench is not None and len(bench) else None
        st.metric("沪深300基准", f"{bench_ret:+.2f}%" if bench_ret is not None else "—",
                  delta=f"{total_ret - bench_ret:+.2f}%" if bench_ret is not None else None,
                  help="组合收益 − 基准收益（超额收益）")
    with cols[3]:
        st.metric("区间起始", start_str)

    if bench is None:
        st.caption("ℹ️ 沪深300基准暂未展示：未能获取足够历史行情（区间可能过短或接口受限），"
                   "组合收益与回撤结论不受影响。")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pidx.index, y=pidx.values, name="组合净值",
        line=dict(color=UP if total_ret >= 0 else DOWN, width=2.5),
        hovertemplate="%{x}<br>组合：%{y:.1f}<extra></extra>",
    ))
    if bench is not None and len(bench):
        fig.add_trace(go.Scatter(
            x=bench.index, y=bench.values, name="沪深300",
            line=dict(color="#888888", width=1.8, dash="dot"),
            hovertemplate="%{x}<br>沪深300：%{y:.1f}<extra></extra>",
        ))
    fig.add_hline(y=100, line=dict(color="#999", width=1, dash="dash"))
    fig.update_layout(**_fig_layout(dark), height=380, title="组合净值 vs 沪深300（起点=100）",
                      legend=dict(orientation="h", yanchor="top", y=-0.25, x=0.5, xanchor="center"))
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # 加法式健壮性：summary() / pnl_attribution() 在持仓数据异常时可能抛 KeyError，
    # 原代码无兜底会导致整个 fragment 崩溃、净值曲线也一同消失。这里隔离两个子视图，
    # 任一失败仅提示，净值曲线与另一子视图仍可正常展示。
    try:
        _show_pnl_snapshot()
    except Exception as _e:
        st.warning(f"盈亏快照加载失败：{_e}")
    try:
        _show_attribution()
    except Exception as _e:
        st.warning(f"收益贡献加载失败：{_e}")


def _show_pnl_snapshot():
    _section_title("💰 当前盈亏快照", accent="#10b981")
    # 加法式字段级兜底：summary() 因版本差异可能缺失个别键，用 .get 降级为 0，
    # 避免单键缺失导致整块盈亏快照崩溃（外层虽有 try，但部分数据仍应可见）。
    s = pm.summary() or {}
    cols = st.columns(4)
    with cols[0]:
        st.metric("持仓成本", f"{s.get('total_cost', 0):,.0f}")
    with cols[1]:
        st.metric("市值", f"{s.get('total_market_value', 0):,.0f}")
    with cols[2]:
        st.metric("浮动盈亏", f"{s.get('total_pnl', 0):,.0f}", delta=f"{s.get('total_pnl_pct', 0):+.2f}%")
    with cols[3]:
        st.metric("持仓数", f"{s.get('position_count', 0)}")


def _show_attribution():
    _section_title("🥧 个股收益贡献", accent="#ef5da8")
    attr = pm.pnl_attribution()
    if attr is None or attr.empty:
        _empty_info("暂无收益贡献数据。")
        return
    attr = attr.copy()
    attr["contribution"] = pd.to_numeric(attr["contribution"], errors="coerce")
    # 加法式健壮性：个别版本 pnl_attribution 返回可能缺 pnl/name 列
    if "pnl" not in attr.columns:
        attr["pnl"] = 0.0
    attr = attr.sort_values("pnl", ascending=False)
    if "name" not in attr.columns:
        attr["name"] = attr["ticker"] if "ticker" in attr.columns else ""
    top = attr.head(15).copy()
    fig = go.Figure(go.Bar(
        x=top["name"], y=top["contribution"],
        marker_color=[UP if v >= 0 else DOWN for v in top["contribution"]],
        hovertemplate="%{x}<br>贡献：%{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(**_fig_layout(dark), title="收益贡献 TOP15（%）", height=340)
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.dataframe(
        attr, use_container_width=True, hide_index=True,
        column_config={
            "pnl": st.column_config.NumberColumn("盈亏", format="%.0f"),
            "pnl_pct": st.column_config.NumberColumn("盈亏%", format="%.2f"),
            "contribution": st.column_config.NumberColumn("贡献%", format="%.2f"),
        },
    )


fragment_portfolio()
