"""modules/export_bundle.py — 数据导出打包纯函数库（v2 后端化 pages/95_数据导出）。

承接 v1 页面的三件事，拆成可独立单测的纯函数层：
  1. 数据集装配 assemble_datasets：7 个数据集 best-effort，单个失败进 skipped，
     全部数据源通过参数注入（sources / watchlist_codes），本模块自身不触网、不读库；
  2. 四档格式化 to_csv_zip / to_excel / to_pdf / datasets_to_json（CSV/Excel/PDF
     逻辑照抄 v1 页面实现，含 utf-8-sig、Sheet 名清洗、STSong-Light 中文字体）；
  3. 一键研报装配 collect_report_data：行情 / 技术面 / 基本面 / 资金面 / 风险排雷 /
     公告 best-effort 装配，渲染交给 modules.research_report（复用，不重抄）。

诚实红线：
  - 任一数据集失败 → 计入 skipped，不补零、不编造；
  - 全部失败 → datasets 为空字典，由调用方返回 available=false；
  - 格式化异常向上抛出，由端点层转 200 + available=false + reason，绝不返回半个损坏文件。
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date, datetime, timedelta
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

__all__ = [
    "build_default_sources",
    "assemble_datasets",
    "to_csv_zip",
    "to_excel",
    "to_pdf",
    "datasets_to_json",
    "collect_report_data",
    "sheet_name",
]

# 取数函数惰性加载，避免 import 本模块就拖起 akshare / fetcher 全家桶
def _fundflow():
    from modules import fundflow
    return fundflow


_FETCHER = None


def _get_fetcher():
    global _FETCHER
    if _FETCHER is None:
        from modules.fetcher import StockFetcher
        _FETCHER = StockFetcher()
    return _FETCHER


# ───────────────────────── CSV / Sheet 名（照抄 v1） ─────────────────────────
def sheet_name(fname: str) -> str:
    """转成 Excel 合法的 sheet 名（≤31 字符，无非法字符）。"""
    name = str(fname).replace(".csv", "").replace("/", "-").replace("\\", "-")
    for ch in "[]:*?/\\":
        name = name.replace(ch, "-")
    return name[:31]


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """utf-8-sig 编码的 CSV 字节，确保 Excel 打开中文正常。"""
    return df.to_csv(index=False).encode("utf-8-sig")


# ───────────────────────── 数据集装配（依赖注入） ─────────────────────────
def _northbound_datasets() -> dict:
    d = _fundflow().get_northbound_fund_flow() or {}
    boards = pd.DataFrame(d.get("boards") or [])
    summary = pd.DataFrame([{
        "trade_date": d.get("trade_date"),
        "total_inflow": d.get("total_inflow"),
        "sh_inflow": d.get("sh_inflow"),
        "sz_inflow": d.get("sz_inflow"),
    }])
    return {"北向资金_板块.csv": boards, "北向资金_汇总.csv": summary}


def _portfolio_datasets() -> dict:
    from modules.portfolio import PortfolioManager
    pm = PortfolioManager()
    pnl_df = pm.calc_pnl()
    if pnl_df is None or pnl_df.empty:
        return {}  # 持仓为空：明细与汇总一并跳过（与 v1 一致）
    return {
        "组合持仓盈亏.csv": pnl_df,
        "组合持仓汇总.csv": pd.DataFrame([pm.summary()]),
    }


def _watch_rows(codes: list, fetcher) -> list:
    """自选股实时快照行（照抄 v1，NaN 守卫）。"""
    rows = []
    for c in codes:
        try:
            q = fetcher.get_realtime_quote(c) or {}
            cur = q.get("current")
            prev = q.get("prev_close")
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
        except Exception as e:  # noqa: BLE001 - 单只失败不中断整批
            logger.debug("[export] %s 实时行情获取失败: %s", c, e)
            rows.append({"代码": c, "名称": None})
    return rows


def build_default_sources(period: str, code: str, watchlist_codes: Callable | None = None):
    """构造默认数据源清单（依赖注入的默认实现，全部 best-effort）。

    返回 (sources, pre_skipped)：
      sources   : [(数据集名列表, fn() -> dict[数据集名, DataFrame]), ...]
      pre_skipped: 前置条件不满足（缺 code / period 非法 / 无自选股查询通道）的
                   数据集名，直接计入 skipped，不发起取数。
    """
    sources: list = []
    pre_skipped: list = []

    sources.append((["行业板块资金流向.csv"],
                    lambda: {"行业板块资金流向.csv": _fundflow().get_industry_fund_flow()}))
    sources.append((["北向资金_板块.csv", "北向资金_汇总.csv"], _northbound_datasets))
    sources.append((["大盘主力净流入30日.csv"],
                    lambda: {"大盘主力净流入30日.csv": _fundflow().get_market_fund_flow(days=30)}))

    if code:
        def _individual():
            r = _fundflow().get_individual_fund_flow(code) or {}
            return {f"个股主力资金_{code}.csv": pd.DataFrame([{
                "代码": code,
                "source": r.get("source"),
                "main_net": r.get("main_net"),
                "main_net_pct": r.get("main_net_pct"),
                "big_net": r.get("big_net"),
                "super_net": r.get("super_net"),
                "latest_date": r.get("latest_date"),
            }])}
        sources.append(([f"个股主力资金_{code}.csv"], _individual))
    else:
        pre_skipped.append("个股主力资金.csv")

    if period and period.isdigit() and len(period) == 8:
        sources.append(([f"业绩报表_{period}.csv"],
                        lambda: {"业绩报表_{0}.csv".format(period): _fundflow().get_earnings_report(period=period)}))
    else:
        pre_skipped.append("业绩报表.csv")

    sources.append((["组合持仓盈亏.csv", "组合持仓汇总.csv"], _portfolio_datasets))

    if watchlist_codes is not None:
        def _watchlist():
            codes = watchlist_codes() or []
            if not codes:
                return {}
            return {"自选股实时快照.csv": pd.DataFrame(_watch_rows(codes, _get_fetcher()))}
        sources.append((["自选股实时快照.csv"], _watchlist))
    else:
        pre_skipped.append("自选股实时快照.csv")

    return sources, pre_skipped


def assemble_datasets(period: str, code: str, sources=None,
                      watchlist_codes: Callable | None = None):
    """汇总所有数据集，返回 (datasets 字典, skipped 列表)。

    单个数据源失败 / 返回空表 → 该数据集名计入 skipped，不中断整体、不补零。
    ``sources`` 注入后完全离线可测；缺省走 build_default_sources。
    """
    datasets: dict = {}
    skipped: list = []
    if sources is None:
        sources, pre = build_default_sources(period, code, watchlist_codes)
        skipped.extend(pre)

    for names, fn in sources:
        try:
            out = fn() or {}
        except Exception as e:  # noqa: BLE001 - 单源失败不中断整批
            logger.warning("[export] 数据集 %s 获取失败: %s", names, e)
            skipped.extend(names)
            continue
        for name in names:
            df = out.get(name)
            if isinstance(df, pd.DataFrame) and not df.empty:
                datasets[name] = df
            else:
                skipped.append(name)
    return datasets, skipped


# ───────────────────────── 四档格式化 ─────────────────────────
def to_csv_zip(datasets: dict, skipped: list) -> bytes:
    """全部成功数据集的 utf-8-sig CSV 打入内存 ZIP + manifest.csv（含 skipped 说明）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, df in datasets.items():
            zf.writestr(fname, _df_to_csv_bytes(df))
        # manifest.csv：含 included / skipped 清单与说明
        sio = io.StringIO()
        w = csv.writer(sio)
        w.writerow(["数据集", "状态", "说明"])
        for fname in datasets:
            w.writerow([fname, "已包含", ""])
        for s in skipped or []:
            w.writerow([s, "已跳过", "数据不可用"])
        zf.writestr("manifest.csv", sio.getvalue().encode("utf-8-sig"))
    return buf.getvalue()


def to_excel(datasets: dict) -> bytes:
    """将多个 DataFrame 写入一个 .xlsx（多 Sheet），自动列宽 + 冻结表头（照抄 v1）。"""
    import openpyxl  # 惰性加载：仅在导出 Excel 时
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for fname, df in datasets.items():
            # 守卫：仅写入结构合法的非空 DataFrame，避免 AttributeError 致导出崩溃
            if not isinstance(df, pd.DataFrame) or df is None or df.empty:
                continue
            sheet = sheet_name(fname)
            df.to_excel(writer, sheet_name=sheet, index=False)
        for fname, df in datasets.items():
            if not isinstance(df, pd.DataFrame) or df is None or df.empty:
                continue
            sheet = sheet_name(fname)
            ws = writer.sheets[sheet]
            for i, col in enumerate(df.columns, start=1):
                vals = [str(col)]
                try:
                    vals += [str(v) for v in df[col].head(200).tolist()]
                except Exception:  # noqa: BLE001 - 列宽自动估算为 cosmetic best-effort
                    pass
                maxlen = max((len(v) for v in vals), default=8)
                ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = \
                    min(max(maxlen + 2, 10), 42)
            ws.freeze_panes = "A2"
    buf.seek(0)
    return buf.getvalue()


def to_pdf(datasets: dict, skipped: list, period: str, code: str) -> bytes:
    """生成中文数据摘要 PDF：标题 + 各数据集表格（前 25 行）+ skipped 列表（照抄 v1）。"""
    from reportlab.lib.pagesizes import A4  # noqa: I001
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    _PDF_FONT = "STSong-Light"
    _H_STYLE = ParagraphStyle("h", fontName=_PDF_FONT, fontSize=8, textColor=colors.white, leading=10)
    _C_STYLE = ParagraphStyle("c", fontName=_PDF_FONT, fontSize=7, leading=9)
    _TITLE_STYLE = ParagraphStyle("t", fontName=_PDF_FONT, fontSize=16, leading=20)
    _SUB_STYLE = ParagraphStyle("s", fontName=_PDF_FONT, fontSize=9, leading=12,
                                textColor=colors.HexColor("#555555"))
    _SEC_STYLE = ParagraphStyle("sec", fontName=_PDF_FONT, fontSize=11, leading=14,
                                textColor=colors.HexColor("#ee2a2a"), spaceBefore=4, spaceAfter=2)

    def _cell(v) -> str:
        if v is None:
            return "—"
        s = str(v)
        if s in ("nan", "None", ""):
            return "—"
        if len(s) > 40:
            s = s[:37] + "…"
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ee2a2a")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bbbbbb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f6")]),
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
        title = str(fname).replace(".csv", "")
        story.append(Paragraph(f"◆ {title}（{len(df)} 行）", _SEC_STYLE))
        story.append(_df_to_pdf_table(df, avail))
        story.append(Spacer(1, 4 * mm))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def _json_cell(v):
    """单个单元格 JSON 化：NaN/NaT→None，时间→ISO 字符串，numpy 标量→Python 原生。"""
    if v is None:
        return None
    try:
        if bool(pd.isna(v)):
            return None
    except (TypeError, ValueError):  # ui_audit_exempt(T-239R3): pd.isna 判别失败保留原值透传-已审
        pass
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if isinstance(v, np.generic):
        return v.item()
    return v


def datasets_to_json(datasets: dict, skipped: list) -> dict:
    """datasets → {"datasets": {名称: [record...]}, "skipped": [...]}，NaN/NaT→None。"""
    out = {}
    for name, df in datasets.items():
        if not isinstance(df, pd.DataFrame):
            continue
        out[name] = [
            {k: _json_cell(v) for k, v in rec.items()}
            for rec in df.to_dict("records")
        ]
    return {"datasets": out, "skipped": list(skipped or [])}


# ───────────────────────── 一键研报装配（依赖注入，渲染复用 research_report） ─────────────────────────
def collect_report_data(code: str, fetcher=None, *, name_fn=None, daily_fn=None,
                        fundamentals_fn=None, fundflow_fn=None, risk_fn=None):
    """为研报装配**真实**数据；任一板块取不到就留空（研报会标注「数据不可用」）。

    各 fn 可注入以便离线测试；缺省实现走 fetcher / fundflow / stock_risk 惰性导入。
    返回 (data 字典, name)，data 支持的键与 modules.research_report.build_report 对齐。
    """
    data: dict = {}
    name = str(code or "").strip()
    if fetcher is None:
        fetcher = _get_fetcher()

    if name_fn is None:
        name_fn = lambda: fetcher.get_name_only(code)  # noqa: E731
    try:
        name = name_fn() or name
    except Exception as e:  # noqa: BLE001 - best-effort
        logger.debug("[export] %s 名称获取失败: %s", code, e)

    # 行情 + 技术面
    if daily_fn is None:
        def daily_fn():
            today = datetime.now()
            start = (today - timedelta(days=180)).strftime("%Y-%m-%d")
            return fetcher.get_daily(code, start=start, end=today.strftime("%Y-%m-%d"))
    try:
        df = daily_fn()
        if df is not None and not getattr(df, "empty", True):
            from modules.cleaner import DataCleaner
            from modules.technical import full_analysis
            d = DataCleaner.full_pipeline(df)
            data["technical"] = full_analysis(d)
            last = d.iloc[-1]

            def _pick(*cands):
                for c in cands:
                    if c in d.columns:
                        return last.get(c)
                return None

            data["quote"] = {"price": _pick("close", "收盘", "收盘价"),
                             "change_pct": _pick("pct_chg", "涨跌幅")}
    except Exception as e:  # noqa: BLE001 - best-effort
        logger.debug("[export] %s 行情装配失败: %s", code, e)

    # 基本面
    if fundamentals_fn is None:
        fundamentals_fn = lambda: fetcher.get_fundamentals(code)  # noqa: E731
    try:
        fd = fundamentals_fn()
        if isinstance(fd, dict) and fd:
            data["fundamentals"] = fd
    except Exception as e:  # noqa: BLE001 - best-effort
        logger.debug("[export] %s 基本面装配失败: %s", code, e)

    # 资金面
    if fundflow_fn is None:
        fundflow_fn = lambda: _fundflow().get_individual_fund_flow(code)  # noqa: E731
    try:
        ff = fundflow_fn()
        if isinstance(ff, dict) and ff:
            data["fundflow"] = ff
    except Exception as e:  # noqa: BLE001 - best-effort
        logger.debug("[export] %s 资金面装配失败: %s", code, e)

    # 风险排雷 + 公告
    if risk_fn is None:
        def risk_fn():
            from modules import stock_risk as sr
            res = sr.scan_stock(code, name)
            return res.get("report"), sr.fetch_announcement_titles(code)
    try:
        report, announcements = risk_fn()
        data["risk_report"] = report
        data["announcements"] = announcements
    except Exception as e:  # noqa: BLE001 - best-effort
        logger.debug("[export] %s 风险/公告装配失败: %s", code, e)

    return data, name
