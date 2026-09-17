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

from modules.portfolio import PortfolioManager
from modules.page_guard import safe_fragment
from modules.page_utils import render_standard_page, import_autorefresh, get_fetcher
from modules.ui_theme import sf_card, sf_metric
from modules.page_widgets import _empty_info, UP, DOWN, _fig_layout, _section_title
from modules.chart_cache import cached_fig

from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, xc_kpi_grid
st_autorefresh = import_autorefresh()

dark = render_standard_page(
    title="自选股组合收益跟踪", icon="📊",
    caption="基于「仓位管理」中的持仓，按剩余股数加权构建组合净值曲线，对比沪深300基准。",
    layout="wide",
)
sf_card("📊 自选股组合收益跟踪", "基于「仓位管理」中的持仓，按剩余股数加权构建组合净值曲线，对比沪深300基准，展示累计收益、个股贡献与最大回撤。", icon="📈")

fetcher = get_fetcher()
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
    # series 结构：{date: 组合当日市值}；跨持仓同日期必须累加（不能用 dict.update 覆盖，会丢失其它持仓贡献）。
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
                for _d, _v in _fut.result().items():
                    series[_d] = series.get(_d, 0.0) + _v

    if not series:
        return None, None, start_str

    # 注意：series 的值已是「跨持仓累加后的当日组合市值」(float)，直接构造时序，勿再对 v 调 .values()。
    pidx = pd.Series(series, name="组合").sort_index()
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


# ── 图表 figure 构建缓存（性能优化：避免每次脚本重跑/自动刷新时重复 rebuild）──
@cached_fig(ttl=120)
def _build_portfolio_nav_fig(pidx, bench, total_ret, dark):
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
    return fig


@cached_fig(ttl=120)
def _build_attribution_fig(top, dark):
    fig = go.Figure(go.Bar(
        x=top["name"], y=top["contribution"],
        marker_color=[UP if v >= 0 else DOWN for v in top["contribution"]],
        hovertemplate="%{x}<br>贡献：%{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(**_fig_layout(dark), title="收益贡献 TOP15（%）", height=340)
    fig.update_xaxes(tickangle=-45)
    return fig


# ───────────────────────── 主体 ─────────────────────────
@safe_fragment
def fragment_portfolio():
    _section_title("💼 组合净值与基准对比")
    if st_autorefresh is not None:
        st_autorefresh(interval=300000, limit=100, key="pf_auto")

    positions = pm.get_positions()
    if positions is None or positions.empty:
        _empty_info("暂无持仓。请先在「仓位管理」页添加持仓，再回来查看组合收益跟踪。")
        return

    with st.spinner("计算组合历史净值（拉取各持仓日线）…"):
        pidx, bench, start_str = _build_portfolio_series(positions)

    if pidx is None:
        xc_warn_box("暂无法构建组合净值（持仓缺少可用历史行情）。请检查持仓买入日期与代码。")
        # 仍展示当前盈亏快照（best-effort，失败不影响上方提示）
        try:
            _show_pnl_snapshot()
        except Exception as e:
            xc_handle_error("盈亏快照渲染失败", e, hint="请稍后重试，或检查网络与数据源连接")
        return

    total_ret = float(pidx.iloc[-1] - 100)
    mdd = _max_drawdown(pidx)
    bench_ret = float(bench.iloc[-1] - 100) if bench is not None and len(bench) else None
    xc_kpi_grid([
        {"label": "组合累计收益", "value": f"{total_ret:+.2f}%", "icon": "📈",
         "tone": "up" if total_ret >= 0 else "down", "meta": "净值起点 = 100"},
        {"label": "最大回撤", "value": f"{mdd:.2f}%", "icon": "📉",
         "tone": "down" if mdd < 0 else "flat", "meta": "区间峰值回落"},
        {"label": "沪深300基准", "value": f"{bench_ret:+.2f}%" if bench_ret is not None else "—",
         "icon": "🧭",
         "delta": (f"超额 {total_ret - bench_ret:+.2f}%" if bench_ret is not None else ""),
         "delta_dir": ("up" if (bench_ret is not None and total_ret - bench_ret >= 0) else "down"),
         "meta": "组合收益 − 基准收益"},
        {"label": "区间起始", "value": str(start_str), "icon": "🗓️"},
    ])

    if bench is None:
        st.caption("ℹ️ 沪深300基准暂未展示：未能获取足够历史行情（区间可能过短或接口受限），"
                   "组合收益与回撤结论不受影响。")

    fig = _build_portfolio_nav_fig(pidx, bench, total_ret, dark)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
    # 加法式小便利（Batch15）：标注净值曲线数据更新时间，便于判断是否为最新行情。
    st.caption(f"🕒 数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}（组合净值基于各持仓历史收盘价加权构建）")

    # 加法式健壮性：summary() / pnl_attribution() 在持仓数据异常时可能抛 KeyError，
    # 原代码无兜底会导致整个 fragment 崩溃、净值曲线也一同消失。这里隔离两个子视图，
    # 任一失败仅提示，净值曲线与另一子视图仍可正常展示。
    try:
        _show_pnl_snapshot()
    except Exception as _e:
        xc_warn_box(f"盈亏快照加载失败：{_e}")
    try:
        _show_attribution()
    except Exception as _e:
        xc_warn_box(f"收益贡献加载失败：{_e}")
    try:
        _show_risk_xray()
    except Exception as _e:
        xc_warn_box(f"组合风险透视加载失败：{_e}")


def _show_pnl_snapshot():
    _section_title("💰 当前盈亏快照")
    # 加法式字段级兜底：summary() 因版本差异可能缺失个别键，用 .get 降级为 0，
    # 避免单键缺失导致整块盈亏快照崩溃（外层虽有 try，但部分数据仍应可见）。
    s = pm.summary() or {}
    _pnl = s.get('total_pnl', 0)
    _pnl_pct = s.get('total_pnl_pct', 0)
    xc_kpi_grid([
        {"label": "持仓成本", "value": f"{s.get('total_cost', 0):,.0f}", "icon": "🧾"},
        {"label": "市值", "value": f"{s.get('total_market_value', 0):,.0f}", "icon": "💼"},
        {"label": "浮动盈亏", "value": f"{_pnl:,.0f}", "icon": "📊",
         "tone": "up" if _pnl >= 0 else "down",
         "delta": f"{_pnl_pct:+.2f}%", "delta_dir": "up" if _pnl_pct >= 0 else "down"},
        {"label": "持仓数", "value": f"{s.get('position_count', 0)}", "icon": "🔢"},
    ])


def _show_attribution():
    _section_title("🥧 个股收益贡献")
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
    fig = _build_attribution_fig(top, dark)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
    st.dataframe(
        attr, width="stretch", hide_index=True,
        column_config={
            "pnl": st.column_config.NumberColumn("盈亏", format="%.0f"),
            "pnl_pct": st.column_config.NumberColumn("盈亏%", format="%.2f"),
            "contribution": st.column_config.NumberColumn("贡献%", format="%.2f"),
        },
    height=400)
    # 导出收益贡献 CSV（便于离线分析）
    try:
        csv = attr.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("⬇️ 导出收益贡献 CSV", data=csv,
                           file_name="组合收益贡献.csv", mime="text/csv")
    except Exception:
        pass


def _show_risk_xray():
    """H4：组合风险透视 —— 集中度 / 行业暴露 / 相关性 / 情景回放（对标米筐 RQBeta、组合 X-ray）。"""
    from modules.risk_xray import concentration, sector_exposure, correlation_matrix, scenario_pnl
    _section_title("🩻 组合风险透视（X-ray）")
    try:
        pnl_df = pm.calc_pnl()
    except Exception as _e:
        xc_warn_box(f"风险透视取数失败：{_e}")
        return
    if pnl_df is None or pnl_df.empty:
        _empty_info("暂无持仓，无法做组合风险透视。")
        return
    # 权重 = 当前市值（仅取正值）
    w = {}
    for _, r in pnl_df.iterrows():
        try:
            mv = float(r.get("market_value") or 0)
        except Exception:  # noqa: BLE001
            mv = 0.0
        if mv > 0:
            w[str(r.get("ticker"))] = mv
    if len(w) < 1:
        _empty_info("持仓市值为 0，无法计算风险透视。")
        return

    # ── 集中度 ──
    c = concentration(w)
    if c.get("status") == "ok":
        xc_kpi_grid([
            {"label": "持仓数", "value": f"{c['n']}", "icon": "🔢"},
            {"label": "集中度 HHI", "value": f"{c['hhi']:.3f}", "icon": "🎯", "meta": c["level"]},
            {"label": "最大权重", "value": f"{c['max_weight_pct']:.1f}%", "icon": "📌"},
            {"label": "有效持仓数", "value": f"{c['effective_n']:.1f}", "icon": "🧮", "meta": "1/HHI"},
        ])
        st.caption("HHI <0.15 分散 · 0.15–0.25 适中 · >0.25 集中；有效持仓数越低，组合越依赖个别标的。")

    # ── 行业暴露（best-effort，取不到行业如实告警，不编造）──
    try:
        sector_of = {}
        for code in w:
            try:
                sector_of[code] = (fetcher.get_fundamentals(code) or {}).get("industry")
            except Exception:  # noqa: BLE001
                sector_of[code] = None
        se = sector_exposure(w, sector_of)
        if se.get("status") == "ok":
            st.markdown("**行业暴露**")
            st.dataframe(pd.DataFrame([{"行业": k, "权重%": v} for k, v in se["exposure"].items()]),
                         width="stretch", hide_index=True, height=200)
            if se.get("warning"):
                xc_warn_box(se["warning"])
    except Exception as _e:  # noqa: BLE001
        xc_warn_box(f"行业暴露计算失败：{_e}")

    # ── 相关性 + 情景回放（按需触发，避免每次进页都拉行情）──
    with st.expander("🔗 持仓相关性 & 情景压力测试", expanded=False):
        st.caption("基于各持仓近一年日线（最多取权重最大的 8 只）。相关性衡量「是否同涨同跌」；"
                   "情景回放把当前持仓放回最近 1/3/6/12 个月的行情里，看组合会经历多大波动。")
        if st.button("运行相关性 + 情景分析", key="xray_run"):
            top_codes = [k for k, _ in sorted(w.items(), key=lambda kv: -kv[1])][:8]
            hist = {}
            with st.spinner("拉取持仓历史行情…"):
                for code in top_codes:
                    try:
                        df = fetcher.get_daily(
                            code,
                            start=(datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d"),
                            end=datetime.now().strftime("%Y-%m-%d"),
                        )
                        if df is not None and not df.empty:
                            hist[code] = df
                    except Exception:  # noqa: BLE001
                        continue
            if not hist:
                xc_warn_box("未能获取任何持仓历史行情，无法计算相关性/情景。")
                return
            # 相关性热图
            rets = {}
            for code, df in hist.items():
                try:
                    s = pd.to_numeric(df["close"], errors="coerce").dropna()
                    rets[code] = s.pct_change().dropna().tolist()[-120:]
                except Exception:  # noqa: BLE001
                    continue
            cm = correlation_matrix(rets)
            if cm.get("status") == "ok":
                _txt = [[f"{v:.2f}" for v in row] for row in cm["matrix"]]
                figc = go.Figure(go.Heatmap(z=cm["matrix"], x=cm["codes"], y=cm["codes"],
                                            colorscale="RdBu", zmin=-1, zmax=1,
                                            text=_txt, texttemplate="%{text}"))
                figc.update_layout(title=f"持仓收益相关性（近 {cm['n_obs']} 日 · 平均 {cm['avg_corr']}）",
                                   height=380,
                                   template="plotly_white" if not dark else "plotly_dark",
                                   margin=dict(l=40, r=20, t=50, b=40))
                st.plotly_chart(figc, width="stretch",
                                config={"displaylogo": False, "responsive": True})
                st.caption("越接近 1 = 越同涨同跌（分散效果差）；接近 0 = 独立；为负 = 互为对冲。")
            else:
                xc_warn_box(cm.get("reason", "相关性不可用"))

            # 情景回放（历史区间，非虚构事件）
            rows = []
            for label, days in [("近 1 个月", 30), ("近 3 个月", 90), ("近 6 个月", 180), ("近 1 年", 365)]:
                sr = {}
                for code, df in hist.items():
                    try:
                        s = pd.to_numeric(df["close"], errors="coerce").dropna()
                        seg = s.tail(days)
                        if len(seg) >= 2 and float(seg.iloc[0]) > 0:
                            sr[code] = float(seg.iloc[-1]) / float(seg.iloc[0]) - 1
                    except Exception:  # noqa: BLE001
                        continue
                sp = scenario_pnl(w, sr)
                rows.append({"情景": label,
                             "组合损益%": sp.get("pnl_pct") if sp.get("status") == "ok" else None,
                             "覆盖%": sp.get("coverage_pct"), "缺失数": sp.get("n_missing")})
            st.markdown("**历史区间回放（按当前权重静态持有，期末/期初价格模拟）**")
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=200)
            st.caption("⚠️ 回放按当前权重静态持有、未考虑区间内调仓与交易成本，仅作风险量级参考，不构成投资建议。")


fragment_portfolio()
