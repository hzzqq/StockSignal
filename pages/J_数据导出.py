"""
页面 J：数据导出中心
统一的数据导出枢纽 —— 从平台已有数据模块导出 CSV / Excel(多Sheet) / PDF 摘要，
并支持一键打包为 ZIP（内含 CSV + 多Sheet Excel + manifest）。
数据层见 modules.fundflow / modules.portfolio / modules.fetcher / modules.session。
A股配色：红=涨/流入，绿=跌/流出。
"""
import streamlit as st
import pandas as pd
import io, zipfile
from datetime import datetime
from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get
from modules.fundflow import (
    get_industry_fund_flow, get_northbound_fund_flow,
    get_market_fund_flow, get_individual_fund_flow,
    get_earnings_report,
)
from modules.portfolio import PortfolioManager
from modules.fetcher import StockFetcher
from modules.page_guard import safe_fragment
from modules.page_widgets import _empty_info, UP, DOWN
# 注：openpyxl / reportlab 为「重型导出」依赖，改为惰性加载（见 _to_excel_bytes / _to_pdf_bytes），
#     避免进入本页（仅查看 CSV 导出入口）时也强制 import 拖慢首屏。

apply_page_config(page_title="数据导出", page_icon="📤", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("📤 数据导出中心")

st.caption("统一导出平台数据：行业板块资金流向、北向资金、大盘主力净流入、个股主力资金、业绩报表、组合持仓盈亏、自选股实时快照。"
           "支持三种格式 —— CSV（单表）、Excel 多 Sheet 汇总、PDF 摘要报告，并可一键 ZIP 打包。所有文本均使用中文友好编码。"
           "在下方选择数据集后点击对应按钮即可导出；单个数据集失败不影响整体。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    """导出为 utf-8-sig 编码的 CSV 字节，确保 Excel 中文正常。"""
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def _sheet_name(fname: str) -> str:
    """转成 Excel 合法的 sheet 名（≤31 字符，无非法字符）。"""
    name = fname.replace(".csv", "").replace("/", "-").replace("\\", "-")
    for ch in '[]:*?/\\':
        name = name.replace(ch, "-")
    return name[:31]


def _to_excel_bytes(sheets: dict) -> bytes:
    """将多个 DataFrame 写入一个 .xlsx（多 Sheet），自动列宽 + 冻结表头。"""
    import openpyxl  # 惰性加载：仅在导出 Excel 时
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for fname, df in sheets.items():
            sheet = _sheet_name(fname)
            df.to_excel(writer, sheet_name=sheet, index=False)
        for fname, df in sheets.items():
            sheet = _sheet_name(fname)
            ws = writer.sheets[sheet]
            for i, col in enumerate(df.columns, start=1):
                vals = [str(col)]
                try:
                    vals += [str(v) for v in df[col].head(200).tolist()]
                except Exception:
                    pass
                maxlen = max((len(v) for v in vals), default=8)
                ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = \
                    min(max(maxlen + 2, 10), 42)
            ws.freeze_panes = "A2"
    buf.seek(0)
    return buf.getvalue()


# PDF 相关依赖（reportlab）与样式常量、辅助函数均惰性加载于 _to_pdf_bytes 内，避免拖慢首屏。


def _to_pdf_bytes(datasets: dict, skipped: list, period: str, code: str) -> bytes:
    """生成中文数据摘要 PDF：标题 + 各数据集表格（前 25 行）。"""
    # 惰性加载 reportlab 全家桶 + 注册中文字体：仅真正导出 PDF 时才 import，避免拖慢首屏
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    _PDF_FONT = 'STSong-Light'
    _H_STYLE = ParagraphStyle('h', fontName=_PDF_FONT, fontSize=8, textColor=colors.white, leading=10)
    _C_STYLE = ParagraphStyle('c', fontName=_PDF_FONT, fontSize=7, leading=9)
    _TITLE_STYLE = ParagraphStyle('t', fontName=_PDF_FONT, fontSize=16, leading=20)
    _SUB_STYLE = ParagraphStyle('s', fontName=_PDF_FONT, fontSize=9, leading=12,
                                textColor=colors.HexColor('#555555'))
    _SEC_STYLE = ParagraphStyle('sec', fontName=_PDF_FONT, fontSize=11, leading=14,
                                textColor=colors.HexColor('#ee2a2a'), spaceBefore=4, spaceAfter=2)

    def _cell(v) -> str:
        if v is None:
            return '—'
        s = str(v)
        if s in ('nan', 'None', ''):
            return '—'
        if len(s) > 40:
            s = s[:37] + '…'
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _df_to_pdf_table(df: pd.DataFrame, avail: float, max_rows: int = 25):
        cols = list(df.columns)
        head = [str(c) for c in cols]
        d = df.head(max_rows)
        data = [[Paragraph(h, _H_STYLE) for h in head]]
        for _, row in d.iterrows():
            data.append([Paragraph(_cell(row[c]), _C_STYLE) for c in cols])
        n = max(len(cols), 1)
        w = [avail / n] * n
        t = Table(data, colWidths=w, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ee2a2a')),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#bbbbbb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f6f6f6')]),
        ]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm,
        leftMargin=12 * mm, rightMargin=12 * mm, title="StockSignal 数据摘要",
    )
    avail = A4[0] - 24 * mm
    story = [
        Paragraph("StockSignal 数据摘要报告", _TITLE_STYLE),
        Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}　|　"
                  f"报告期：{period or '—'}　|　个股：{code or '—'}", _SUB_STYLE),
        Spacer(1, 6 * mm),
    ]
    if skipped:
        story.append(Paragraph("以下数据集本次不可用，已跳过：" + "、".join(skipped), _SUB_STYLE))
        story.append(Spacer(1, 3 * mm))
    for fname, df in datasets.items():
        title = fname.replace('.csv', '')
        story.append(Paragraph(f"◆ {title}（{len(df)} 行）", _SEC_STYLE))
        story.append(_df_to_pdf_table(df, avail))
        story.append(Spacer(1, 4 * mm))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# ───────────────────────── 公共取数（供 ZIP/Excel/PDF 复用） ─────────────────────────
def _parse_watchlist(body) -> list:
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
            codes = [c.get("stock_code") or c.get("code") or c.get("ticker") for c in codes]
        codes = [str(c).strip().zfill(6) for c in codes if c]
    return codes or []


def _watch_rows(codes: list) -> list:
    rows = []
    for c in codes:
        try:
            q = fetcher.get_realtime_quote(c) or {}
            cur = q.get("current")
            prev = q.get("prev_close")
            # 行情可能返回 NaN / 非数值：用 pd.notna 守卫，避免算出差额/涨跌幅为 "nan" 或除零
            cur_ok = isinstance(cur, (int, float)) and pd.notna(cur)
            prev_ok = isinstance(prev, (int, float)) and pd.notna(prev)
            delta = round(cur - prev, 2) if (cur_ok and prev_ok) else None
            pct = round((cur - prev) / prev * 100, 2) if (cur_ok and prev_ok and prev != 0) else None
            rows.append({
                "代码": c,
                "名称": q.get("name"),
                "现价": cur,
                "涨跌额": delta,
                "涨跌幅%": pct,
                "开盘": q.get("open"),
                "最高": q.get("high"),
                "最低": q.get("low"),
                "成交额": q.get("amount"),
                "成交量": q.get("volume"),
                "时间": q.get("datetime"),
            })
        except Exception:
            rows.append({"代码": c, "名称": None})
    return rows


def _collect_all(period: str, code: str):
    """汇总所有数据集，返回 (datasets 字典, 跳过列表)。单个失败不影响整体。"""
    datasets: dict = {}
    skipped: list = []

    def _add(key, df):
        if isinstance(df, pd.DataFrame) and df is not None and not df.empty:
            datasets[key] = df
        else:
            skipped.append(key)

    # 行业板块
    try:
        _add("行业板块资金流向.csv", get_industry_fund_flow())
    except Exception:
        skipped.append("行业板块资金流向.csv")

    # 北向资金（板块 + 汇总）
    try:
        d = get_northbound_fund_flow()
        boards = pd.DataFrame(d.get("boards") or [])
        summary = pd.DataFrame([{
            "trade_date": d.get("trade_date"),
            "total_inflow": d.get("total_inflow"),
            "sh_inflow": d.get("sh_inflow"),
            "sz_inflow": d.get("sz_inflow"),
        }])
        _add("北向资金_板块.csv", boards)
        _add("北向资金_汇总.csv", summary)
    except Exception:
        skipped += ["北向资金_板块.csv", "北向资金_汇总.csv"]

    # 大盘主力净流入30日
    try:
        _add("大盘主力净流入30日.csv", get_market_fund_flow(days=30))
    except Exception:
        skipped.append("大盘主力净流入30日.csv")

    # 个股主力资金
    try:
        if code:
            r = get_individual_fund_flow(code)
            _add(f"个股主力资金_{code}.csv", pd.DataFrame([{
                "代码": code,
                "source": r.get("source"),
                "main_net": r.get("main_net"),
                "main_net_pct": r.get("main_net_pct"),
                "big_net": r.get("big_net"),
                "super_net": r.get("super_net"),
                "latest_date": r.get("latest_date"),
            }]))
        else:
            skipped.append("个股主力资金.csv")
    except Exception:
        skipped.append(f"个股主力资金_{code or ''}.csv")

    # 业绩报表
    try:
        if period and period.isdigit() and len(period) == 8:
            _add(f"业绩报表_{period}.csv", get_earnings_report(period=period))
        else:
            skipped.append("业绩报表.csv")
    except Exception:
        skipped.append(f"业绩报表_{period or ''}.csv")

    # 组合持仓盈亏 + 汇总
    try:
        pm = PortfolioManager()
        pnl_df = pm.calc_pnl()
        if pnl_df is not None and not pnl_df.empty:
            datasets["组合持仓盈亏.csv"] = pnl_df
            datasets["组合持仓汇总.csv"] = pd.DataFrame([pm.summary()])
        else:
            skipped += ["组合持仓盈亏.csv", "组合持仓汇总.csv"]
    except Exception:
        skipped += ["组合持仓盈亏.csv", "组合持仓汇总.csv"]

    # 自选股实时快照
    try:
        _, body = api_get("/api/watchlist", timeout=10)
        codes = _parse_watchlist(body)
        if codes:
            rows = _watch_rows(codes)
            if rows:
                datasets["自选股实时快照.csv"] = pd.DataFrame(rows)
            else:
                skipped.append("自选股实时快照.csv")
        else:
            skipped.append("自选股实时快照.csv")
    except Exception:
        skipped.append("自选股实时快照.csv")

    return datasets, skipped


# ───────────────────────── 行业板块资金流向 ─────────────────────────
@safe_fragment("行业板块数据")
def frag_industry():
    st.subheader("🏭 行业板块资金流向")
    st.caption("数据源：东方财富 stock_fund_flow_industry()")
    if st.button("生成并下载 CSV", key="exp_industry_btn"):
        try:
            with st.spinner("获取行业板块资金流向…"):
                df = get_industry_fund_flow()
        except Exception as e:
            st.error(f"⚠️ 获取行业板块资金流向失败：{e}")
            return
        if df is None or df.empty:
            _empty_info("暂无数据")
        else:
            csv = _to_csv_bytes(df)
            st.download_button(
                "⬇️ 下载 CSV", data=csv,
                file_name="行业板块资金流向.csv", mime="text/csv",
            )
            st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 北向资金 ─────────────────────────
@safe_fragment("北向资金")
def frag_northbound():
    st.subheader("🌐 北向资金")
    st.caption("数据源：东方财富 stock_hsgt_fund_flow_summary_em()（沪股通/深股通/北向）")
    if st.button("生成并下载 CSV", key="exp_north_btn"):
        try:
            with st.spinner("获取北向资金…"):
                d = get_northbound_fund_flow()
        except Exception as e:
            st.error(f"⚠️ 获取北向资金失败：{e}")
            return
        if d is None:
            _empty_info("暂无北向资金数据（接口暂不可用）")
            return
        boards = pd.DataFrame(d.get("boards") or [])
        summary = pd.DataFrame([{
            "trade_date": d.get("trade_date"),
            "total_inflow": d.get("total_inflow"),
            "sh_inflow": d.get("sh_inflow"),
            "sz_inflow": d.get("sz_inflow"),
        }])
        if boards is None or boards.empty:
            _empty_info("暂无数据")
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
@safe_fragment("市场资金概览")
def frag_market():
    st.subheader("📊 大盘主力净流入（近30日）")
    st.caption("数据源：东方财富 stock_market_fund_flow()，取最近 30 日")
    if st.button("生成并下载 CSV", key="exp_market_btn"):
        try:
            with st.spinner("获取大盘主力净流入…"):
                df = get_market_fund_flow(days=30)
        except Exception as e:
            st.error(f"⚠️ 获取大盘主力净流入失败：{e}")
            return
        if df is None or df.empty:
            _empty_info("暂无数据")
        else:
            csv = _to_csv_bytes(df)
            st.download_button(
                "⬇️ 下载 CSV", data=csv,
                file_name="大盘主力净流入30日.csv", mime="text/csv",
            )
            st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 个股主力资金 ─────────────────────────
@safe_fragment("个股资金流")
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
            try:
                r = get_individual_fund_flow(code)
            except Exception as e:
                st.error(f"⚠️ 获取 {code} 主力资金失败：{e}")
                return
        if not r:
            st.warning(f"暂未获取到 {code} 的主力资金数据，请稍后重试。")
            return
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
@safe_fragment("业绩日历")
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
            try:
                df = get_earnings_report(period=period)
            except Exception as e:
                st.error(f"⚠️ 获取业绩报表失败：{e}")
                return
        if df is None or df.empty:
            _empty_info("暂无数据")
        else:
            csv = _to_csv_bytes(df)
            st.download_button(
                "⬇️ 下载 CSV", data=csv,
                file_name=f"业绩报表_{period}.csv", mime="text/csv",
            )
            st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 组合持仓盈亏 ─────────────────────────
@safe_fragment("持仓组合")
def frag_portfolio():
    st.subheader("💼 组合持仓盈亏")
    st.caption("数据源：modules.portfolio.PortfolioManager（calc_pnl / summary）")
    if st.button("生成并下载 CSV", key="exp_port_btn"):
        try:
            with st.spinner("计算持仓盈亏…"):
                pm = PortfolioManager()
                pnl_df = pm.calc_pnl()
        except Exception as e:
            st.error(f"⚠️ 计算持仓盈亏失败：{e}")
            return
        if pnl_df is None or pnl_df.empty:
            _empty_info("暂无数据（当前组合为空）")
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
@safe_fragment("自选股池")
def frag_watchlist():
    st.subheader("⭐ 自选股实时快照")
    st.caption("数据源：/api/watchlist + StockFetcher.get_realtime_quote()")
    if st.button("生成并下载 CSV", key="exp_watch_btn"):
        try:
            with st.spinner("获取自选股实时行情…"):
                _, body = api_get("/api/watchlist", timeout=10)
                codes = _parse_watchlist(body)
        except Exception as e:
            st.error(f"⚠️ 获取自选股失败：{e}")
            return
        if not codes:
            _empty_info("暂无数据（自选股为空或接口不可用）")
            return
        rows = _watch_rows(codes)
        if not rows:
            _empty_info("暂无数据（自选股为空或接口不可用）")
            return
        df = pd.DataFrame(rows)
        st.download_button(
            "⬇️ 下载 CSV", data=_to_csv_bytes(df),
            file_name="自选股实时快照.csv", mime="text/csv",
        )
        st.success(f"已导出 {len(df)} 行")


# ───────────────────────── 一键导出 Excel（多Sheet） ─────────────────────────
@safe_fragment("Excel 多Sheet 导出")
def frag_excel():
    st.subheader("📊 一键导出 Excel（多 Sheet）")
    st.caption("将所有可用数据集汇总进单个 .xlsx，每个数据集一个 Sheet（自动列宽 + 冻结表头）。")
    from modules.search_ui import stock_search_input
    period = st.text_input("财报报告期 (YYYYMMDD)", value="20260331", key="expall_period")
    code = stock_search_input(label="个股主力资金 - 选择股票", key="expall_stock", default="600519")
    if st.button("📊 生成并下载 Excel", key="expall_btn"):
        with st.spinner("汇总所有数据集…"):
            datasets, skipped = _collect_all(period, code)
        if not datasets:
            _empty_info("暂无数据（所有数据集均不可用）")
            return
        xlsx = _to_excel_bytes(datasets)
        st.download_button(
            "⬇️ 下载 Excel（多 Sheet）", data=xlsx,
            file_name=f"StockSignal_数据汇总_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.success(f"已生成 {len(datasets)} 个 Sheet" + (f"；跳过 {len(skipped)} 项" if skipped else ""))


# ───────────────────────── 导出数据摘要 PDF ─────────────────────────
@safe_fragment("PDF 摘要导出")
def frag_pdf():
    st.subheader("📄 导出数据摘要 PDF")
    st.caption("生成中文数据摘要报告（每个数据集展示前 25 行）。完整数据请用 CSV / Excel / ZIP。")
    from modules.search_ui import stock_search_input
    period = st.text_input("财报报告期 (YYYYMMDD)", value="20260331", key="pdf_period")
    code = stock_search_input(label="个股主力资金 - 选择股票", key="pdf_stock", default="600519")
    if st.button("📄 生成并下载 PDF", key="pdf_btn"):
        with st.spinner("汇总并生成中文 PDF…"):
            datasets, skipped = _collect_all(period, code)
        if not datasets:
            _empty_info("暂无数据（所有数据集均不可用）")
            return
        try:
            pdf = _to_pdf_bytes(datasets, skipped, period, code)
        except Exception as e:  # PDF 生成极端失败兜底
            st.error(f"PDF 生成失败：{e}")
            return
        st.download_button(
            "⬇️ 下载 PDF 摘要", data=pdf,
            file_name=f"StockSignal_数据摘要_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
        )
        st.success(f"已生成摘要（{len(datasets)} 个数据集" + (f"；跳过 {len(skipped)} 项" if skipped else "") + "）")


# ───────────────────────── 一键打包导出全部 (ZIP) ─────────────────────────
@safe_fragment("批量打包下载")
def frag_zip():
    st.subheader("📦 一键打包导出全部 (ZIP)")
    st.caption("汇总上述所有数据集（成功返回的部分）打入内存 ZIP，内含 CSV + 多Sheet Excel + manifest。单个数据集失败不影响整体。")
    from modules.search_ui import stock_search_input
    period = st.text_input("财报报告期 (YYYYMMDD，用于打包)", value="20260331", key="zip_period")
    code = stock_search_input(label="个股主力资金 - 选择股票", key="zip_stock", default="600519")

    if st.button("📦 生成并下载 ZIP", key="exp_zip_btn"):
        with st.spinner("汇总所有数据集…"):
            datasets, skipped = _collect_all(period, code)
        if not datasets:
            _empty_info("暂无数据（所有数据集均不可用）")
            return

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, df in datasets.items():
                zf.writestr(fname, df.to_csv(index=False, encoding="utf-8-sig"))
            # 多 Sheet Excel 一并打包
            try:
                zf.writestr(
                    "StockSignal_全量数据.xlsx",
                    _to_excel_bytes(datasets),
                )
            except Exception:
                pass
            # manifest 清单
            lines = [
                "StockSignal 数据导出清单",
                f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"报告期：{period or '—'}　个股：{code or '—'}",
                "",
                "已包含数据集：",
            ]
            for fname in datasets:
                lines.append(f"  ✓ {fname}")
            if skipped:
                lines.append("")
                lines.append("本次跳过（不可用）：")
                for s in skipped:
                    lines.append(f"  ✗ {s}")
            zf.writestr("manifest.txt", "\n".join(lines))
        buf.seek(0)
        st.download_button(
            "⬇️ 下载 ZIP", data=buf.getvalue(),
            file_name=f"StockSignal_数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
        )
        st.success(f"已打包 {len(datasets)} 个数据集" + (f"；跳过 {len(skipped)} 项" if skipped else ""))


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
with st.expander("📊 一键导出 Excel（多 Sheet）", expanded=False):
    frag_excel()
with st.expander("📄 导出数据摘要 PDF", expanded=False):
    frag_pdf()
with st.expander("📦 一键打包导出全部 (ZIP)", expanded=False):
    frag_zip()
