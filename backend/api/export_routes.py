"""backend/api/export_routes.py — 数据导出 v2 读端点（后端化 pages/95_数据导出）。

端点（url_prefix=/api/v2/read，均在 JWT 鉴权之后）：
  GET /export-bundle?format=zip|excel|pdf|json&period=YYYYMMDD&code=6位数字
      服务端 best-effort 装配 7 个数据集，单个失败进 skipped，绝不补零；
      全部失败 → 200 + available=false + skipped 全清单（诚实，不返回空文件假装成功）；
      zip = utf-8-sig CSV + manifest.csv 打包；excel = 多 Sheet xlsx；
      pdf = 中文摘要（每数据集前 25 行）；json = {datasets, skipped} 供前端自渲染。
      格式化失败（如 PDF 崩）→ 200 + available=false + reason，不返回半个损坏文件。
  GET /stock-report?code=6位数字&format=html|md
      复用 modules.research_report 一键研报装配 + render_html/render_markdown，
      取不到的板块留空并标注「数据不可用」，绝不编造。
      返回 JSON 信封（HTML/MD 作为字符串放 data 里，前端自行 Blob 下载）。

红线：
  * 参数严格校验，非法 → 422 validation_error；
  * 文件响应 Content-Disposition 用 ASCII 回退名 + RFC 5987 filename*（中文文件名不崩）；
  * 文件内不含任何交易类端点/字样。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, Response, g, request

from ..auth.decorators import jwt_required
from ..utils.response import fail, ok
from modules import export_bundle as eb

logger = logging.getLogger(__name__)

bp = Blueprint("export", __name__, url_prefix="/api/v2/read")

_CODE_RE = re.compile(r"^\d{6}$")
_PERIOD_RE = re.compile(r"^\d{8}$")
_FORMATS = ("zip", "excel", "pdf", "json")
_REPORT_FORMATS = ("html", "md")
# 64 投研圆桌静态交付物（v1 pages/64_投研圆桌.py 读取的固定路径，右侧文件名白名单，
# 不接受用户传路径，天然无目录穿越面）。v2 只读取，不写交付物。
_ROUNDTABLE_DIR = (Path(__file__).resolve().parents[2] / "deliverables"
                   / "stock-partner" / "2026-09-11")
_ROUNDTABLE_FILES = {
    "md": ("大盘主线与情绪研判_投研圆桌.md", "text/markdown; charset=utf-8"),
    "html": ("大盘主线与情绪研判_投研圆桌.html", "text/html; charset=utf-8"),
}
_ROUNDTABLE_FORMATS = ("meta", "md", "html")
_MIME = {
    "zip": "application/zip",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _content_disposition(filename: str) -> str:
    """RFC 6266/5987：ASCII 回退名 + filename*（UTF-8），中文文件名不崩。"""
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    ascii_name = "".join(c for c in filename if ord(c) < 128)
    ascii_name = ascii_name.replace('"', "").replace("\\", "").strip() or f"download{ext}"
    return f"attachment; filename=\"{ascii_name}\"; filename*=utf-8''{quote(filename)}"


def _roundtable_read(fmt: str) -> str | None:
    """读固定白名单交付物；缺文件/坏编码返回 None（诚实空，不补样本文字）。"""
    name, _ = _ROUNDTABLE_FILES[fmt]
    path = _ROUNDTABLE_DIR / name
    if not path.is_file():
        logger.warning("[roundtable] 交付物缺失: %s", path)
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("[roundtable] 交付物读取失败 %s: %s", path, e)
        return None


def _roundtable_kpis(md: str) -> list[dict]:
    """与 v1 pages/64_投研圆桌.py::_kpi_band 同款口径：只从报告正文正则提取。

    解析失败/字段缺失的卡跳过，整带无卡则空数组；绝不为凑卡编造或新拉数据。
    """
    cards: list[dict] = []
    m = re.search(r"数据日期：\*\*([^*]+)\*\*", md)
    if m:
        cards.append({"label": "数据日期", "value": m.group(1).strip(),
                      "meta": "westock-mcp 实时行情快照（收盘）"})
    m = re.search(r"涨占比 \*\*(\d+)%\*\*", md)
    if m:
        cards.append({"label": "市场涨占比", "value": f"{m.group(1)}%",
                      "meta": "广度温度官口径（报告快照值）"})
    n_views = len(re.findall(r"^### [①②③④⑤]", md, flags=re.M)) + (
        1 if "逆向视角" in md else 0)
    if n_views:
        cards.append({"label": "参与视角", "value": str(n_views),
                      "meta": "广度 / 结构 / 主线 / 资金 / 仓位 / 逆向"})
    missing = [n for n in ("宏观 PMI", "北向资金") if n in md]
    if missing:
        cards.append({"label": "显式缺席维度", "value": str(len(missing)),
                      "meta": "、".join(missing) + "（凡缺均显式标注）"})
    return cards


def _db_watchlist_codes() -> list:
    """从数据库读当前登录用户的自选股代码（自选股快照数据集的数据源）。"""
    from sqlalchemy import select as _select

    from ..extensions import db
    from ..models import Watchlist

    rows = db.session.execute(
        _select(Watchlist.stock_code)
        .where(Watchlist.user_id == g.current_user.id)
        .order_by(Watchlist.created_at.desc())
    ).scalars()
    return [str(c).strip().zfill(6) for c in rows if c]


@bp.get("/export-bundle")
@jwt_required
def export_bundle():
    """GET /api/v2/read/export-bundle — 四档格式（zip / excel / pdf / json）数据导出。"""
    fmt = (request.args.get("format") or "").strip().lower()
    if fmt not in _FORMATS:
        return fail(message="format 须为 zip / excel / pdf / json 之一",
                    code="validation_error", http_status=422)

    code = (request.args.get("code") or "").strip()
    if code and not _CODE_RE.fullmatch(code):
        return fail(message="code 须为 6 位数字股票代码",
                    code="validation_error", http_status=422)

    period = (request.args.get("period") or "").strip()
    if period and not _PERIOD_RE.fullmatch(period):
        return fail(message="period 须为 8 位数字的 YYYYMMDD 格式",
                    code="validation_error", http_status=422)

    try:
        datasets, skipped = eb.assemble_datasets(
            period, code, watchlist_codes=_db_watchlist_codes)
    except Exception as e:  # noqa: BLE001 - 装配框架级异常：诚实降级，不 500
        logger.warning("[export] 数据集装配失败: %s", e)
        return ok(data={"available": False, "datasets": {}, "skipped": [],
                        "reason": f"数据集装配失败：{type(e).__name__}，请稍后重试"},
                  message="export-bundle")

    if not datasets:
        # 全部失败：诚实返回 available=false + skipped 全清单，不返回空文件假装成功
        return ok(data={"available": False, "datasets": {}, "skipped": skipped,
                        "reason": "所有数据集均不可用（数据源无数据或获取失败），本次导出为空"},
                  message="export-bundle")

    if fmt == "json":
        payload = {"available": True, "reason": None}
        payload.update(eb.datasets_to_json(datasets, skipped))
        return ok(data=payload, message="export-bundle")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        if fmt == "zip":
            payload_bytes = eb.to_csv_zip(datasets, skipped)
            filename = f"StockSignal_数据导出_{stamp}.zip"
        elif fmt == "excel":
            payload_bytes = eb.to_excel(datasets)
            filename = f"StockSignal_数据汇总_{stamp}.xlsx"
        else:
            payload_bytes = eb.to_pdf(datasets, skipped, period, code)
            filename = f"StockSignal_数据摘要_{stamp}.pdf"
    except Exception as e:  # noqa: BLE001 - 格式化失败：诚实降级，不返回半个损坏文件
        logger.warning("[export] %s 格式生成失败: %s", fmt, e)
        return ok(data={"available": False, "datasets": {}, "skipped": skipped,
                        "reason": f"{fmt} 格式生成失败：{type(e).__name__}，请稍后重试"},
                  message="export-bundle")

    return Response(payload_bytes, mimetype=_MIME[fmt],
                    headers={"Content-Disposition": _content_disposition(filename)})


@bp.get("/stock-report")
@jwt_required
def stock_report():
    """GET /api/v2/read/stock-report — 一键研报（HTML / Markdown，JSON 信封）。"""
    code = (request.args.get("code") or "").strip()
    if not _CODE_RE.fullmatch(code):
        return fail(message="code 须为 6 位数字股票代码",
                    code="validation_error", http_status=422)
    fmt = (request.args.get("format") or "").strip().lower()
    if fmt not in _REPORT_FORMATS:
        return fail(message="format 须为 html 或 md",
                    code="validation_error", http_status=422)

    from ..api.market_routes import get_fetcher
    from modules import research_report as rrp

    try:
        data, name = eb.collect_report_data(code, fetcher=get_fetcher())
    except Exception as e:  # noqa: BLE001 - 装配框架级异常：诚实降级，不 500
        logger.warning("[export] 研报装配失败: %s", e)
        return ok(data={"available": False, "reason": f"研报装配失败：{type(e).__name__}，请稍后重试"},
                  message="stock-report")

    try:
        rep = rrp.build_report(code, name, data)
        rendered = rrp.render_html(rep) if fmt == "html" else rrp.render_markdown(rep)
    except Exception as e:  # noqa: BLE001 - 渲染失败：诚实降级，不返回半个损坏文件
        logger.warning("[export] 研报渲染失败: %s", e)
        return ok(data={"available": False, "reason": f"研报渲染失败：{type(e).__name__}，请稍后重试"},
                  message="stock-report")

    coverage = rep.get("coverage_pct", 0)
    available = bool(rendered) and coverage > 0
    payload = {
        "available": available,
        "code": code,
        "name": name,
        "coverage_pct": coverage,
        "skipped_blocks": rep.get("warnings", []),
        "reason": None if available
        else "本报告无有效数据板块（覆盖率 0%）——可能行情源不可用或代码有误，请勿据此做任何判断",
    }
    payload["html" if fmt == "html" else "md"] = rendered
    return ok(data=payload, message="stock-report")


@bp.get("/roundtable-report")
@jwt_required
def roundtable_report():
    """GET /api/v2/read/roundtable-report?format=meta|md|html —— 64 静态投研圆桌交付物。

    与 v1 pages/64_投研圆桌.py 读同一对本地 MD / HTML 文件（固定白名单路径）：
    - meta：KPI 带（从 MD 正文正则提取，同 v1 口径）+ 双格式可用状态；
    - md / html：原文字符串放统一信封 data.content，前端自行 Blob 下载 / 预览；
    - 文件缺失或坏编码 → 200 + available=false + reason，绝不补样例报告冒充交付物。
    """
    fmt = (request.args.get("format") or "meta").strip().lower()
    if fmt not in _ROUNDTABLE_FORMATS:
        return fail(message="format 须为 meta / md / html 之一",
                    code="validation_error", http_status=422)

    md = _roundtable_read("md")
    html = _roundtable_read("html")

    if fmt == "meta":
        return ok(data={
            "available": bool(md or html),
            "as_of": "2026-09-11",
            "kpis": _roundtable_kpis(md) if md else [],
            "md_available": md is not None,
            "html_available": html is not None,
            "source_note": "静态交付物原文（westock-mcp 2026-09-11 收盘快照），非实时数据",
            "reason": None if (md or html) else "MD / HTML 交付物均缺失，未做任何填充",
        }, message="roundtable-report")

    content = md if fmt == "md" else html
    if content is None:
        return ok(data={
            "available": False, "format": fmt, "as_of": "2026-09-11",
            "reason": f"{fmt.upper()} 交付物缺失或无法读取，未返回样例内容",
        }, message="roundtable-report")

    name, mime = _ROUNDTABLE_FILES[fmt]
    return ok(data={
        "available": True, "format": fmt, "filename": name, "mime": mime,
        "as_of": "2026-09-11", "content": content, "reason": None,
    }, message="roundtable-report")
