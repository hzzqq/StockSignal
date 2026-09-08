"""
页面 G：财报与业绩日历
按报告期查看已披露财报的个股列表（业绩报表），含每股收益/营收/净利润/同比，并支持
业绩预告（best-effort）与披露日历（best-effort）。数据层见 modules/fundflow.py。
A股配色：业绩改善(净利润同比>0)=红，下滑=绿。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modules.fundflow import (
    get_earnings_report, get_earnings_forecast, get_disclosure_calendar,
)

from modules.page_guard import safe_fragment
from modules.page_utils import render_standard_page, get_fetcher
from modules.ui_theme import sf_card, sf_metric
from modules.page_widgets import UP, DOWN, _fig_layout, _section_title, _empty_info
from modules.search_ui import stock_search_input
from modules.chart_cache import cached_fig
from modules.financial_report_helpers import (
    fr_fmt, fr_filter_by_code, fr_color_yoy, fr_format_financial_df,
)

from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, info_banner
dark = render_standard_page(
    title="财报与业绩日历", icon="📅",
    caption="按报告期查看已披露财报个股（业绩报表），含业绩预告与披露日历（best-effort）。数据来源：东方财富。",
    layout="wide",
)
sf_card("📅 财报与业绩日历", "按报告期查看已披露财报个股（业绩报表），含每股收益 / 营收 / 净利润及同比；附业绩预告与披露日历（best-effort）。数据来源：东方财富。", icon="📊")
fetcher = get_fetcher()


# ─────────────── 页面级缓存（fundflow 内部也有缓存，这里是双层保险：跨会话复用） ───────────────
@st.cache_data(show_spinner=False, ttl=1800)
def _cached_report(period: str):
    return get_earnings_report(period)

@st.cache_data(show_spinner=False, ttl=1800)
def _cached_forecast(period: str):
    return get_earnings_forecast(period)

@st.cache_data(show_spinner=False, ttl=1800)
def _cached_disclosure(market: str, period: str):
    return get_disclosure_calendar(market=market, period=period)


# ── 新浪财务三表（个股查询用，best-effort）──
@st.cache_data(show_spinner=False, ttl=1800)
def _cached_financial(code: str, report_type: str):
    """财务三表（利润表/资产负债表/现金流量表），best-effort，失败返回 None。"""
    try:
        df = fetcher.get_financial(code, report_type)
        return df if (df is not None and not getattr(df, "empty", True)) else None
    except Exception:
        return None


@cached_fig(ttl=600)
def _build_financial_trend_fig(code: str):
    """利润表多期趋势：营业总收入 / 净利润（单位：亿元），取新浪利润表最新 8 期。

    best-effort：取数失败或字段缺失返回 None，调用方跳过渲染。
    """
    import plotly.graph_objects as go
    try:
        inc = _cached_financial(code, "income")
    except Exception:
        inc = None
    if inc is None or (hasattr(inc, "empty") and inc.empty) or "报告日" not in inc.columns:
        return None
    need = [c for c in ("营业总收入", "净利润") if c in inc.columns]
    if not need:
        return None
    try:
        d = inc[["报告日"] + need].copy()
        for c in need:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=need, how="all").iloc[::-1]  # 旧→新，左→右
        if d.empty:
            return None
        fig = go.Figure()
        _line_colors = {"营业总收入": "#667eea", "净利润": "#ffa502"}
        for c in need:
            fig.add_trace(go.Scatter(
                x=d["报告日"].astype(str), y=d[c] / 1e8,
                mode="lines+markers", name=c,
                line=dict(color=_line_colors.get(c, "#667eea"), width=2),
                marker=dict(size=6),
            ))
        fig.update_layout(
            height=320, margin=dict(l=50, r=20, t=34, b=40),
            template="plotly_dark" if dark else "plotly_white",
            xaxis_tickangle=-45, yaxis_title="亿元",
            legend=dict(orientation="h", y=1.12, x=0),
            title=f"{code} 利润表多期趋势（亿元）",
        )
        return fig
    except Exception:
        return None


@cached_fig(ttl=600)
def _build_financial_bar_fig(code: str):
    """利润表多期对比柱状图：营业总收入 / 净利润（单位：亿元）。
    净利润按环比增减着色（红=改善、绿=下滑），与页面「业绩配色」约定一致。
    best-effort：取数失败或字段缺失返回 None，调用方跳过渲染。
    """
    try:
        inc = _cached_financial(code, "income")
    except Exception:
        inc = None
    if inc is None or (hasattr(inc, "empty") and inc.empty) or "报告日" not in inc.columns:
        return None
    need = [c for c in ("营业总收入", "净利润") if c in inc.columns]
    if not need:
        return None
    try:
        d = inc[["报告日"] + need].copy()
        for c in need:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=need, how="all").iloc[::-1]  # 旧→新，左→右
        if d.empty:
            return None
        fig = go.Figure()
        if "营业总收入" in need:
            fig.add_trace(go.Bar(
                x=d["报告日"].astype(str), y=d["营业总收入"] / 1e8,
                name="营业总收入", marker_color="#667eea",
            ))
        if "净利润" in need:
            net = d["净利润"] / 1e8
            net_colors = []
            prev = None
            for v in net:
                if prev is None or pd.isna(prev):
                    net_colors.append("#8a8f98")  # 首期无环比，中性灰
                elif v >= prev:
                    net_colors.append("#ff4d4f")  # 改善=红
                else:
                    net_colors.append("#00d486")  # 下滑=绿
                prev = v
            fig.add_trace(go.Bar(
                x=d["报告日"].astype(str), y=net,
                name="净利润", marker_color=net_colors,
            ))
        fig.update_layout(
            height=340, margin=dict(l=50, r=20, t=34, b=40),
            barmode="group",
            template="plotly_dark" if dark else "plotly_white",
            xaxis_tickangle=-45, yaxis_title="亿元",
            legend=dict(orientation="h", y=1.12, x=0),
            title=f"{code} 利润表多期对比（亿元，净利润红=改善/绿=下滑）",
        )
        return fig
    except Exception:
        return None


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
        df = _cached_report(period)
    except Exception as e:
        xc_handle_error("业绩报表加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
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
        info_banner("「净利润同比%」字段缺失，盈利改善占比暂不可计算（接口字段变更或网络异常）。")
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
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
    else:
        info_banner("「净利润 / 名称」字段缺失，TOP 净利润柱状图暂不可绘制（接口字段变更或网络异常）。")

    try:
        st.dataframe(
            df, width="stretch", hide_index=True,
            column_config={
                "披露时间": st.column_config.TextColumn("披露时间", help="财报实际披露日期"),
                "每股收益": st.column_config.NumberColumn("每股收益", format="%.2f"),
                "营业总收入": st.column_config.NumberColumn("营业总收入", format="%.2e"),
                "营收同比%": st.column_config.NumberColumn("营收同比%", format="%.1f"),
                "净利润": st.column_config.NumberColumn("净利润", format="%.2e"),
                "净利润同比%": st.column_config.NumberColumn("净利润同比%", format="%.1f"),
                "ROE%": st.column_config.NumberColumn("ROE%", format="%.2f"),
            },
        height=400)
    except Exception as e:
        xc_handle_error("财报日历表格渲染失败", e, hint="请稍后重试，或检查网络与数据源连接")
    else:
        # 导出业绩报表 CSV（便于离线分析）
        try:
            csv = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("⬇️ 导出业绩报表 CSV", data=csv,
                               file_name=f"业绩报表_{period}.csv", mime="text/csv")
        except Exception:
            pass


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
        df = _cached_forecast(period)
    except Exception as e:
        df = pd.DataFrame()
        xc_handle_error("业绩预告接口加载失败", e, hint="已降级为空数据，请稍后重试")
    if df is None or df.empty:
        _empty_info(f"「{period_label}」业绩预告暂不可用（接口返回空）。")
        st.caption("💡 业绩预告接口稳定性较低，可切换报告期或稍后重试。")
        if st.button("📅 试看 2025 年报", key="fc_try_2025"):
            st.session_state["fc_period"] = "2025 年报"
        return
    # 加法式渲染兜底：best-effort 接口返回的 DataFrame 可能含怪异列类型（如嵌套列表/对象），
    # 直接 st.dataframe 会异常；包裹后失败仅提示，不影响上方概览与下方其它视图。
    try:
        st.dataframe(df, width="stretch", hide_index=True, height=400)
    except Exception as _e:
        xc_warn_box(f"业绩预告表格渲染失败：{_e}")


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
        df = _cached_disclosure(market=market, period=period_str)
    except Exception as e:
        df = pd.DataFrame()
        xc_handle_error("披露日历接口加载失败", e, hint="已降级为空数据，请稍后重试")
    if df is None or df.empty:
        _empty_info("披露日历暂不可用（接口返回空或参数不支持）。")
        st.caption("💡 可切换市场或报告期后重试；沪市 2025 年报通常最完整。")
        if st.button("📅 试看 沪市·2025年报", key="dc_try_2025"):
            st.session_state["dc_market"] = "沪市"
            st.session_state["dc_period"] = "2025年报"
        return
    # 加法式渲染兜底（Batch15）：best-effort 接口返回的 DataFrame 可能含怪异列类型，
    # 直接 st.dataframe 会异常；包裹后失败仅提示，不影响上方概览与下方其它视图。
    try:
        st.dataframe(df, width="stretch", hide_index=True, height=400)
    except Exception as _e:
        xc_warn_box(f"披露日历表格渲染失败：{_e}")


# ───────────────────────── 个股财报查询（搜索个股，看它自己的财报） ─────────────────────────
@safe_fragment
def fragment_stock_financials():
    """个股查询自己的财报情况：选一只股票，展示其业绩报表/预告/披露日历/财务三表。

    复用 modules.financial_report_helpers 的纯函数与 modules.fundflow 数据层，
    与 20页「个股财报」片段同源（同样按代码过滤、红=改善绿=下滑着色、CSV 导出），
    避免重复逻辑。新增于财报与业绩日历页，满足「财报与业绩日历内查个股」的需求。
    """
    _section_title("🔍 个股财报查询", accent="#667eea")
    st.caption("选择一只股票，查看它自己的业绩报表、业绩预告、披露日历与财务三表（利润表/资产负债表/现金流量表）。数据来源：东方财富 / 新浪财经。")
    ticker = stock_search_input(
        label='股票搜索', key='fin_stock', default='600519',
        placeholder='输入代码或名称搜索，如：600519 / 贵州茅台 / GZMT / 茅台',
    )
    if not ticker:
        return
    code = str(ticker).zfill(6)

    period_label = st.selectbox(
        "报告期", options=list(PERIODS.keys()), index=0, key=f"fsp_period_{ticker}",
        help="选择财报报告期，查看该股对应期的业绩数据",
    )
    period = PERIODS[period_label]

    # ── 业绩报表（东财，按代码过滤）──
    _section_title("📊 业绩报表", accent="#2b8aef")
    try:
        rep_df = _cached_report(period)
    except Exception as e:
        rep_df = None
        xc_handle_error("业绩报表加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
    row = fr_filter_by_code(rep_df, code)
    if row is None or row.empty:
        _empty_info(f"未查询到「{code}」在「{period_label}」的业绩报表（可能尚未披露或代码不匹配）。")
    else:
        _r = row.iloc[0]
        yoy_col, yoy_txt = fr_color_yoy(_r.get("净利润同比%"))
        rev_col, rev_txt = fr_color_yoy(_r.get("营收同比%"))
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("每股收益", fr_fmt(_r.get("每股收益")))
        with mc2:
            st.metric("营业总收入", fr_fmt(_r.get("营业总收入")), help="单位：元")
        with mc3:
            st.metric("净利润", fr_fmt(_r.get("净利润")), help="单位：元")
        with mc4:
            st.metric("ROE%", fr_fmt(_r.get("ROE%")))
        st.markdown(
            f"<div style='font-size:13px;line-height:1.9;color:var(--txt2);margin:6px 0 10px;'>"
            f"净利润同比 <b style='color:{yoy_col};'>净利润 {yoy_txt}</b>　|　"
            f"营收同比 <b style='color:{rev_col};'>营收 {rev_txt}</b>　|　"
            f"披露时间：<b style='color:var(--txt);'>{_r.get('披露时间', '—')}</b></div>",
            unsafe_allow_html=True,
        )
        st.caption("💡 业绩配色：红=同比增长为正（改善），绿=为负（下滑）；与价格「绿涨红跌」不同，仅针对业绩增速。")
        try:
            st.dataframe(row, width="stretch", hide_index=True, height=220)
        except Exception as e:
            xc_warn_box(f"业绩报表明细渲染失败：{e}")
        try:
            _csv = row.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "⬇️ 导出业绩报表 CSV", data=_csv,
                file_name=f"业绩报表_{code}_{period}.csv", mime="text/csv",
                key=f"fsp_csv_{ticker}_{period}",
            )
        except Exception:
            pass

    # ── 业绩预告（best-effort，按代码过滤）──
    with st.expander("🔮 业绩预告（best-effort）", expanded=False, key=f"fsp_fc_{ticker}"):
        try:
            fc_df = _cached_forecast(period)
        except Exception:
            fc_df = None
        fc_row = fr_filter_by_code(fc_df, code)
        if fc_row is None or fc_row.empty:
            _empty_info(f"「{code}」暂无「{period_label}」业绩预告（接口不稳定或尚未发布）。")
        else:
            try:
                st.dataframe(fc_row, width="stretch", hide_index=True, height=300)
            except Exception as e:
                xc_warn_box(f"业绩预告渲染失败：{e}")

    # ── 披露日历（best-effort，按代码过滤）──
    with st.expander("🗓️ 披露日历（best-effort）", expanded=False, key=f"fsp_dc_{ticker}"):
        mcol1, mcol2 = st.columns(2)
        with mcol1:
            market = st.selectbox("市场", ["沪市", "深市", "沪深京"], index=0, key=f"fsp_dc_mkt_{ticker}")
        with mcol2:
            period_str = st.selectbox("报告期（披露）", ["2025年报", "2024年报", "2023年报"], index=0, key=f"fsp_dc_per_{ticker}")
        try:
            dc_df = _cached_disclosure(market=market, period_str=period_str)
        except Exception:
            dc_df = None
        dc_row = fr_filter_by_code(dc_df, code)
        if dc_row is None or dc_row.empty:
            _empty_info(f"「{code}」在「{market}·{period_str}」披露日历中未匹配到记录（接口仅支持年报）。")
        else:
            try:
                st.dataframe(dc_row, width="stretch", hide_index=True, height=300)
            except Exception as e:
                xc_warn_box(f"披露日历渲染失败：{e}")

    # ── 财务三表（新浪，best-effort）──
    _section_title("🧾 财务三表", accent="#10b981")
    st.caption("数据来源：新浪财经财务三表（取最新 8 期，金额已自动换算为 亿/万）。接口偶发不稳定时单个表会单独提示。")
    # 多期趋势（利润表：营业总收入 / 净利润，单位亿元）
    try:
        _tf = _build_financial_trend_fig(code)
        if _tf is not None:
            st.plotly_chart(_tf, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
    except Exception:
        pass
    for _rt, _lbl in (("income", "利润表"), ("balance", "资产负债表"), ("cash", "现金流量表")):
        with st.expander(f"📄 {_lbl}", expanded=False, key=f"fsp_tbl_{_rt}_{ticker}"):
            try:
                _tdf = _cached_financial(code, _rt)
            except Exception:
                _tdf = None
            if _tdf is None or (hasattr(_tdf, "empty") and _tdf.empty):
                _empty_info(f"「{code}」{_lbl}暂不可用（接口返回空或网络受限）。可前往「基本面分析」页查看更完整的多期财务分析。")
                continue
            try:
                _tdf_disp = fr_format_financial_df(_tdf)
                st.dataframe(_tdf_disp, width="stretch", hide_index=True, height=360)
                _csv = _tdf.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    f"⬇️ 导出{_lbl} CSV", data=_csv,
                    file_name=f"{_lbl}_{code}.csv", mime="text/csv",
                    key=f"fsp_tbl_csv_{_rt}_{ticker}",
                )
            except Exception as e:
                xc_warn_box(f"{_lbl}渲染失败：{e}")


# ───────────────────────── 页面主体 ─────────────────────────
fragment_report()
st.markdown("---")
fragment_forecast()
st.markdown("---")
fragment_disclosure()
st.markdown("---")
fragment_stock_financials()
