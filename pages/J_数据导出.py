"""
页面 J：数据导出中心
统一的数据导出枢纽 —— 从平台已有数据模块导出 CSV，并支持一键打包为 ZIP。
数据层见 modules.fundflow / modules.portfolio / modules.fetcher / modules.session。
A股配色：红=涨/流入，绿=跌/流出。
"""
import streamlit as st
import pandas as pd
import io, zipfile, tempfile, os
from datetime import datetime, timedelta
from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get, safe_switch_page
from modules.fundflow import (
    get_industry_fund_flow, get_northbound_fund_flow,
    get_market_fund_flow, get_individual_fund_flow,
    get_earnings_report,
)
from modules.portfolio import PortfolioManager
from modules.fetcher import StockFetcher

apply_page_config(page_title="数据导出", page_icon="📤", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("📤 数据导出中心")

# A股配色（仅用于样式提示）
UP = "#ee2a2a"      # 红（涨 / 流入）
DOWN = "#1aa260"    # 绿（跌 / 流出）

st.caption("统一导出平台数据：行业板块资金流向、北向资金、大盘主力净流入、个股主力资金、业绩报表、组合持仓盈亏、自选股实时快照。所有 CSV 均使用 utf-8-sig 编码，Excel 可直接正确显示中文。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    """导出为 utf-8-sig 编码的 CSV 字节，确保 Excel 中文正常。"""
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


# ───────────────────────── 行业板块资金流向 ─────────────────────────
@st.fragment
def frag_industry():
    st.subheader("🏭 行业板块资金流向")
    st.caption("数据源：东方财富 stock_fund_flow_industry()")
    if st.button("生成并下载 CSV", key="exp_industry_btn"):
        with st.spinner("获取行业板块资金流向…"):
            df = get_industry_fund_flow()
        if df is None or df.empty:
            st.info("暂无数据")
        else:
            csv = _to_csv_bytes(df)
            st.download_button(
                "⬇️ 下载 CSV", data=csv,
                file_name="行业板块资金流向.csv", mime="text/csv",
            )
            st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 北向资金 ─────────────────────────
@st.fragment
def frag_northbound():
    st.subheader("🌐 北向资金")
    st.caption("数据源：东方财富 stock_hsgt_fund_flow_summary_em()（沪股通/深股通/北向）")
    if st.button("生成并下载 CSV", key="exp_north_btn"):
        with st.spinner("获取北向资金…"):
            d = get_northbound_fund_flow()
        boards = pd.DataFrame(d.get("boards") or [])
        summary = pd.DataFrame([{
            "trade_date": d.get("trade_date"),
            "total_inflow": d.get("total_inflow"),
            "sh_inflow": d.get("sh_inflow"),
            "sz_inflow": d.get("sz_inflow"),
        }])
        if boards is None or boards.empty:
            st.info("暂无数据")
            return
        st.download_button(
            "⬇️ 下载 CSV（板块明细）", data=_to_csv_bytes(boards),
            file_name="北向资金_板块.csv", mime="text/csv",
        )
        st.download_button(
            "⬇️ 下载 CSV（汇总标量）", data=_to_csv_bytes(summary),
            file_name="北向资金_汇总.csv", mime="text/csv",
        )
        st.success(f"已导出 {len(boards)} 行（板块）+ 1 行（汇总）")


# ───────────────────────── 大盘主力净流入(近30日) ─────────────────────────
@st.fragment
def frag_market():
    st.subheader("📊 大盘主力净流入（近30日）")
    st.caption("数据源：东方财富 stock_market_fund_flow()，取最近 30 日")
    if st.button("生成并下载 CSV", key="exp_market_btn"):
        with st.spinner("获取大盘主力净流入…"):
            df = get_market_fund_flow(days=30)
        if df is None or df.empty:
            st.info("暂无数据")
        else:
            csv = _to_csv_bytes(df)
            st.download_button(
                "⬇️ 下载 CSV", data=csv,
                file_name="大盘主力净流入30日.csv", mime="text/csv",
            )
            st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 个股主力资金 ─────────────────────────
@st.fragment
def frag_individual():
    st.subheader("🎯 个股主力资金")
    st.caption("数据源：东方财富 stock_individual_fund_flow()（失败则量价模型估算兜底）")
    from modules.search_ui import stock_search_input
    code = stock_search_input(label="选择股票", key="exp_stock", default="600519")
    if st.button("生成并下载 CSV", key="exp_individual_btn"):
        if not code:
            st.warning("请先选择股票")
            return
        with st.spinner(f"获取 {code} 主力资金…"):
            r = get_individual_fund_flow(code)
        row = pd.DataFrame([{
            "代码": code,
            "source": r.get("source"),
            "main_net": r.get("main_net"),
            "main_net_pct": r.get("main_net_pct"),
            "big_net": r.get("big_net"),
            "super_net": r.get("super_net"),
            "latest_date": r.get("latest_date"),
        }])
        st.download_button(
            "⬇️ 下载 CSV", data=_to_csv_bytes(row),
            file_name=f"个股主力资金_{code}.csv", mime="text/csv",
        )
        st.success(f"已导出 1 行（来源：{r.get('source')}）")


# ───────────────────────── 业绩报表(财报) ─────────────────────────
@st.fragment
def frag_earnings():
    st.subheader("📑 业绩报表（财报）")
    st.caption("数据源：东方财富 stock_yjbb_em()，报告期格式 YYYYMMDD（如 20260331=一季报）")
    period = st.text_input(
        "报告期 (YYYYMMDD)", value="20260331", key="exp_period",
        help="例如 20260331=一季报，20260630=中报，20260930=三季报，20261231=年报",
    )
    if st.button("生成并下载 CSV", key="exp_earnings_btn"):
        if not (period and period.isdigit() and len(period) == 8):
            st.warning("报告期须为 8 位数字的 YYYYMMDD 格式")
            return
        with st.spinner(f"获取业绩报表 {period}…"):
            df = get_earnings_report(period=period)
        if df is None or df.empty:
            st.info("暂无数据")
        else:
            csv = _to_csv_bytes(df)
            st.download_button(
                "⬇️ 下载 CSV", data=csv,
                file_name=f"业绩报表_{period}.csv", mime="text/csv",
            )
            st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 组合持仓盈亏 ─────────────────────────
@st.fragment
def frag_portfolio():
    st.subheader("💼 组合持仓盈亏")
    st.caption("数据源：modules.portfolio.PortfolioManager（calc_pnl / summary）")
    if st.button("生成并下载 CSV", key="exp_port_btn"):
        with st.spinner("计算持仓盈亏…"):
            pm = PortfolioManager()
            pnl_df = pm.calc_pnl()
        if pnl_df is None or pnl_df.empty:
            st.info("暂无数据（当前组合为空）")
            return
        summary = pm.summary()
        summary_df = pd.DataFrame([summary])
        st.download_button(
            "⬇️ 下载 CSV（持仓盈亏明细）", data=_to_csv_bytes(pnl_df),
            file_name="组合持仓盈亏.csv", mime="text/csv",
        )
        st.download_button(
            "⬇️ 下载 CSV（汇总）", data=_to_csv_bytes(summary_df),
            file_name="组合持仓汇总.csv", mime="text/csv",
        )
        st.success(f"已导出 {len(pnl_df)} 行（明细）+ 1 行（汇总）")


# ───────────────────────── 自选股实时快照 ─────────────────────────
@st.fragment
def frag_watchlist():
    st.subheader("⭐ 自选股实时快照")
    st.caption("数据源：/api/watchlist + StockFetcher.get_realtime_quote()")
    if st.button("生成并下载 CSV", key="exp_watch_btn"):
        with st.spinner("获取自选股实时行情…"):
            sc, body = api_get("/api/watchlist", timeout=10)
            codes = []
            if isinstance(body, dict):
                for key in ("watchlist", "data", "items", "stocks"):
                    v = body.get(key)
                    if isinstance(v, list):
                        codes = v
                        break
            elif isinstance(body, list):
                codes = body
            if isinstance(codes, list) and codes:
                if isinstance(codes[0], dict):
                    codes = [c.get("stock_code") or c.get("code") or c.get("ticker")
                             for c in codes]
                codes = [str(c).strip().zfill(6) for c in codes if c]
        if not codes:
            st.info("暂无数据（自选股为空或接口不可用）")
            return
        rows = []
        for code in codes:
            try:
                q = fetcher.get_realtime_quote(code) or {}
                rows.append({
                    "代码": code,
                    "名称": q.get("name"),
                    "现价": q.get("current"),
                    "涨跌额": (round(q.get("current", 0) - q.get("prev_close", 0), 2)
                               if q.get("current") is not None and q.get("prev_close") is not None else None),
                    "涨跌幅%": (round((q.get("current", 0) - q.get("prev_close", 0)) / q.get("prev_close", 0) * 100, 2)
                                if q.get("prev_close") else None),
                    "开盘": q.get("open"),
                    "最高": q.get("high"),
                    "最低": q.get("low"),
                    "成交额": q.get("amount"),
                    "成交量": q.get("volume"),
                    "时间": q.get("datetime"),
                })
            except Exception:
                rows.append({"代码": code, "名称": None})
        df = pd.DataFrame(rows)
        st.download_button(
            "⬇️ 下载 CSV", data=_to_csv_bytes(df),
            file_name="自选股实时快照.csv", mime="text/csv",
        )
        st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 一键打包导出全部 (ZIP) ─────────────────────────
@st.fragment
def frag_zip():
    st.subheader("📦 一键打包导出全部 (ZIP)")
    st.caption("汇总上述所有数据集（成功返回的部分）打入内存 ZIP，单个数据集失败不影响整体。")
    from modules.search_ui import stock_search_input
    period = st.text_input(
        "财报报告期 (YYYYMMDD，用于打包)", value="20260331", key="zip_period",
    )
    code = stock_search_input(label="个股主力资金 - 选择股票", key="zip_stock", default="600519")

    if st.button("📦 生成并下载 ZIP", key="exp_zip_btn"):
        datasets = {}

        # 行业板块
        try:
            df = get_industry_fund_flow()
            if df is not None and not df.empty:
                datasets["行业板块资金流向.csv"] = df
        except Exception:
            pass

        # 北向资金（板块 + 汇总）
        try:
            d = get_northbound_fund_flow()
            boards = pd.DataFrame(d.get("boards") or [])
            if boards is not None and not boards.empty:
                datasets["北向资金_板块.csv"] = boards
            summary = pd.DataFrame([{
                "trade_date": d.get("trade_date"),
                "total_inflow": d.get("total_inflow"),
                "sh_inflow": d.get("sh_inflow"),
                "sz_inflow": d.get("sz_inflow"),
            }])
            datasets["北向资金_汇总.csv"] = summary
        except Exception:
            pass

        # 大盘主力净流入30日
        try:
            df = get_market_fund_flow(days=30)
            if df is not None and not df.empty:
                datasets["大盘主力净流入30日.csv"] = df
        except Exception:
            pass

        # 个股主力资金
        try:
            if code:
                r = get_individual_fund_flow(code)
                datasets[f"个股主力资金_{code}.csv"] = pd.DataFrame([{
                    "代码": code,
                    "source": r.get("source"),
                    "main_net": r.get("main_net"),
                    "main_net_pct": r.get("main_net_pct"),
                    "big_net": r.get("big_net"),
                    "super_net": r.get("super_net"),
                    "latest_date": r.get("latest_date"),
                }])
        except Exception:
            pass

        # 业绩报表
        try:
            if period and period.isdigit() and len(period) == 8:
                df = get_earnings_report(period=period)
                if df is not None and not df.empty:
                    datasets[f"业绩报表_{period}.csv"] = df
        except Exception:
            pass

        # 组合持仓盈亏 + 汇总
        try:
            pm = PortfolioManager()
            pnl_df = pm.calc_pnl()
            if pnl_df is not None and not pnl_df.empty:
                datasets["组合持仓盈亏.csv"] = pnl_df
                datasets["组合持仓汇总.csv"] = pd.DataFrame([pm.summary()])
        except Exception:
            pass

        # 自选股实时快照
        try:
            sc, body = api_get("/api/watchlist", timeout=10)
            codes = []
            if isinstance(body, dict):
                for key in ("watchlist", "data", "items", "stocks"):
                    v = body.get(key)
                    if isinstance(v, list):
                        codes = v
                        break
            elif isinstance(body, list):
                codes = body
            if isinstance(codes, list) and codes:
                if isinstance(codes[0], dict):
                    codes = [c.get("stock_code") or c.get("code") or c.get("ticker")
                             for c in codes]
                codes = [str(c).strip().zfill(6) for c in codes if c]
            if codes:
                rows = []
                for c in codes:
                    try:
                        q = fetcher.get_realtime_quote(c) or {}
                        rows.append({
                            "代码": c,
                            "名称": q.get("name"),
                            "现价": q.get("current"),
                            "涨跌额": (round(q.get("current", 0) - q.get("prev_close", 0), 2)
                                       if q.get("current") is not None and q.get("prev_close") is not None else None),
                            "涨跌幅%": (round((q.get("current", 0) - q.get("prev_close", 0)) / q.get("prev_close", 0) * 100, 2)
                                        if q.get("prev_close") else None),
                            "开盘": q.get("open"),
                            "最高": q.get("high"),
                            "最低": q.get("low"),
                            "成交额": q.get("amount"),
                            "成交量": q.get("volume"),
                            "时间": q.get("datetime"),
                        })
                    except Exception:
                        rows.append({"代码": c, "名称": None})
                if rows:
                    datasets["自选股实时快照.csv"] = pd.DataFrame(rows)
        except Exception:
            pass

        if not datasets:
            st.info("暂无数据（所有数据集均不可用）")
            return

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, df in datasets.items():
                zf.writestr(fname, df.to_csv(index=False, encoding="utf-8-sig"))
        buf.seek(0)
        st.download_button(
            "⬇️ 下载 ZIP", data=buf.getvalue(),
            file_name=f"StockSignal_数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
        )
        st.success(f"已打包 {len(datasets)} 个数据集")


# ───────────────────────── 渲染 ─────────────────────────
with st.expander("🏭 行业板块资金流向", expanded=True):
    frag_industry()
with st.expander("🌐 北向资金", expanded=False):
    frag_northbound()
with st.expander("📊 大盘主力净流入（近30日）", expanded=False):
    frag_market()
with st.expander("🎯 个股主力资金", expanded=False):
    frag_individual()
with st.expander("📑 业绩报表（财报）", expanded=False):
    frag_earnings()
with st.expander("💼 组合持仓盈亏", expanded=False):
    frag_portfolio()
with st.expander("⭐ 自选股实时快照", expanded=False):
    frag_watchlist()
with st.expander("📦 一键打包导出全部 (ZIP)", expanded=False):
    frag_zip()
