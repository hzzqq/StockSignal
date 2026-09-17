"""modules/research_report.py — 一键研报（H8）。

「分析结论只有留在 App 里」是这类工具的通病：老板看完六维评分、风险排雷、技术面，
想带走一份东西（存档 / 发给别人 / 贴进群里）就得自己截图。本模块把散落在各页的
结论**装配成一份可下载的单文件研报**（HTML 自包含 + Markdown 双格式）。

对标：芝麻 AI 的年报摘要、同花顺 i问财 的结论卡片、雪球的长文导出。

━━━━━━━━━━━━━━━━━━━━━━━━━━━ 诚实红线 ━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 纯计算、不触网：数据由调用方（页面）注入，本模块只做**装配与渲染**；
- 任一板块缺数据 → 该板块标「数据不可用」，并计入 ``warnings`` 与 ``coverage_pct``；
  **绝不用默认值 / 占位数字把空缺填满**；
- 覆盖率为 0 时，报告页首必须显著提示「本报告无有效数据」，不得装成一份正常研报；
- 所有注入文本**一律 HTML 转义**（标题来自外部数据源）；
- 免责声明为固定文案，任何情况下都要出现。
"""

from __future__ import annotations

import html
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

__all__ = [
    "SECTION_KEYS", "UP_COLOR", "DOWN_COLOR",
    "build_report", "render_html", "render_markdown",
]

# A 股配色：红=涨/流入，绿=跌/流出
UP_COLOR = "#ee2a2a"
DOWN_COLOR = "#1aa260"
_FLAT = "#8c8c8c"

SECTION_KEYS = [
    ("basic", "标的基本信息"),
    ("risk", "风险排雷"),
    ("technical", "技术面"),
    ("fundflow", "资金面"),
    ("announcement", "公告与事件"),
    ("conclusion", "结论"),
]

_DISCLAIMER = ("本报告由 StockSignal 依据公开数据自动生成，用于研究辅助；"
               "所有指标均为启发式规则，非预测模型，不构成任何投资建议。")


def _num(v):
    """尽力转 float；失败返回 ``None``（0 是合法值，保留）。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f else None
    try:
        f = float(str(v).replace(",", "").replace("%", "").strip())
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _fmt(v, suffix="", nd=2):
    f = _num(v)
    return f"{f:.{nd}f}{suffix}" if f is not None else "—"


def _sec(available, summary, rows=None, note=""):
    return {"available": bool(available), "summary": summary, "rows": rows or [], "note": note}


# ─────────────────────── 各板块装配（纯函数） ───────────────────────
def _basic(code, name, quote, fundamentals):
    q = quote if isinstance(quote, dict) else {}
    f = fundamentals if isinstance(fundamentals, dict) else {}
    rows = []
    price = _num(q.get("price") if q.get("price") is not None else f.get("price"))
    chg = _num(q.get("change_pct"))
    if price is not None:
        rows.append(("最新价", f"{price:.2f}", chg))
    for label, key, suffix in (("总市值", "market_cap", " 亿"), ("市盈率TTM", "pe_ttm", ""),
                               ("市净率", "pb", ""), ("股息率TTM", "dividend_yield", "%")):
        v = _num(f.get(key))
        if v is not None:
            rows.append((label, f"{v:.2f}{suffix}", None))
    ind = f.get("industry")
    if ind:
        rows.append(("所属行业", str(ind), None))
    if not rows:
        return _sec(False, "未取到行情 / 基本面数据")
    return _sec(True, f"{code} {name}" if name else str(code), rows)


def _risk(risk_report):
    """``risk_report`` 为 ``modules.stock_risk.build_risk_report`` 的返回值。"""
    if not isinstance(risk_report, dict) or not risk_report.get("components"):
        return _sec(False, "未执行风险排雷")
    lvl_cn = {"high": "高", "medium": "中", "low": "低", "unknown": "未知"}
    overall = lvl_cn.get(risk_report.get("overall_level"), "未知")
    rows = []
    for key, cn, _unit in _risk_dims():
        comp = (risk_report.get("components") or {}).get(key) or {}
        lv = lvl_cn.get(comp.get("level"), "未知")
        rows.append((cn, lv, comp.get("note") or ""))
    cov = _num(risk_report.get("coverage_pct"))
    note = f"维度覆盖率 {cov:.0f}%" if cov is not None else ""
    if risk_report.get("reliable") is False:
        note = (note + "；覆盖率不足，结论仅供参考").strip("；")
    return _sec(True, f"整体风险：{overall}", rows, note)


def _risk_dims():
    try:
        from modules.stock_risk import DIMENSIONS
        return DIMENSIONS
    except Exception:  # noqa: BLE001
        return [("goodwill", "商誉", ""), ("pledge", "质押", ""), ("unlock", "解禁", ""),
                ("reduction", "减持", ""), ("litigation", "诉讼处罚", ""), ("st", "ST/退市", "")]


def _technical(technical):
    t = technical if isinstance(technical, dict) else None
    if not t:
        return _sec(False, "未取到技术面数据")
    rows = []
    for label, path in (("趋势分", ("trend", "trend_score")),
                        ("动量分", ("momentum", "momentum_score")),
                        ("量价分", ("volume", "volume_price_score"))):
        node = t.get(path[0]) if isinstance(t.get(path[0]), dict) else {}
        v = _num(node.get(path[1]))
        if v is not None:
            rows.append((label, f"{v:.1f}", None))
    patterns = t.get("patterns") or []
    names = []
    for p in patterns:
        if isinstance(p, dict):
            nm = p.get("name")
            if nm:
                names.append(f"{nm}（{p.get('bias')}）" if p.get("bias") else str(nm))
        elif p:
            names.append(str(p))
    if names:
        rows.append(("技术形态", "、".join(names[:8]), None))
    if not rows:
        return _sec(False, "技术面数据为空")
    return _sec(True, f"识别到 {len(names)} 个技术形态" if names else "指标已计算", rows)


def _fundflow(fundflow):
    ff = fundflow if isinstance(fundflow, dict) else None
    if not ff:
        return _sec(False, "未取到资金面数据")
    rows = []
    for label, key, divisor, unit in (("主力净流入", "main_net", 1e8, " 亿"),
                                      ("超大单净流入", "super_net", 1e8, " 亿"),
                                      ("大单净流入", "big_net", 1e8, " 亿"),
                                      ("散户净流入", "retail_net", 1e8, " 亿")):
        v = _num(ff.get(key))
        if v is not None:
            rows.append((label, f"{v / divisor:+.2f}{unit}", v))
    if not rows:
        return _sec(False, "资金面数据为空")
    return _sec(True, "资金流向明细", rows)


def _announcement(titles):
    if titles is None:
        return _sec(False, "未取到公告数据")
    if not titles:
        return _sec(True, "近 1 年未取到公告", rows=[], note="无记录 ≠ 无风险")
    rows = [(f"公告 {i + 1}", str(t)) for i, t in enumerate(titles[:10])]
    return _sec(True, f"近 1 年 {len(titles)} 条公告（列示前 10 条）", rows)


def _conclusion(parts: dict, coverage):
    """结论板块由已知板块推导，缺数据就明说缺什么；零覆盖时直接标「不可用」。"""
    missing = [cn for k, cn in SECTION_KEYS
               if k not in ("conclusion",) and not (parts.get(k) or {}).get("available")]
    if coverage <= 0:
        # 没有任何有效板块 → 不给「结论」，只如实列出缺什么
        return _sec(False, "无有效板块可用于形成结论",
                    note=("缺失板块：" + "、".join(missing)) if missing else "")
    bullets = []
    risk = parts.get("risk") or {}
    if risk.get("available"):
        bullets.append(f"风险：{risk['summary']}")
    tech = parts.get("technical") or {}
    if tech.get("available"):
        bullets.append(f"技术面：{tech['summary']}")
    flow = parts.get("fundflow") or {}
    if flow.get("available"):
        bullets.append(f"资金面：{flow['summary']}")
    if missing:
        bullets.append("未纳入结论的板块（缺数据）：" + "、".join(missing))
    return _sec(True, f"基于 {coverage:.0f}% 的板块覆盖率形成以下要点：",
                [(f"要点 {i + 1}", b) for i, b in enumerate(bullets)])


def build_report(code: str, name: str = "", data: dict | None = None,
                 ts: str | None = None) -> dict:
    """装配研报。

    ``data`` 支持的键：``quote`` / ``fundamentals`` / ``technical`` / ``fundflow`` /
    ``risk_report`` / ``announcements``。
    """
    data = data if isinstance(data, dict) else {}
    code = str(code or "").strip()
    parts = {
        "basic": _basic(code, name, data.get("quote"), data.get("fundamentals")),
        "risk": _risk(data.get("risk_report")),
        "technical": _technical(data.get("technical")),
        "fundflow": _fundflow(data.get("fundflow")),
        "announcement": _announcement(data.get("announcements")),
    }
    total = len(parts)
    ok = sum(1 for v in parts.values() if v["available"])
    coverage = round(ok / total * 100, 1) if total else 0.0
    parts["conclusion"] = _conclusion(parts, coverage)

    warnings = [f"{cn}：{parts[k]['summary']}" for k, cn in SECTION_KEYS
                if k in parts and not parts[k]["available"]]
    return {
        "code": code,
        "name": name or code,
        "generated_at": ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "coverage_pct": coverage,
        "sections": parts,
        "warnings": warnings,
        "disclaimer": _DISCLAIMER,
    }


# ─────────────────────────── 渲染 ───────────────────────────
def _color_for(value):
    v = _num(value)
    if v is None or v == 0:
        return _FLAT
    return UP_COLOR if v > 0 else DOWN_COLOR


def render_html(report: dict) -> str:
    """渲染为**自包含**单文件 HTML（内联 CSS，无任何外部资源引用）。"""
    rep = report if isinstance(report, dict) else {}
    esc = html.escape
    code = esc(str(rep.get("code") or ""))
    name = esc(str(rep.get("name") or ""))
    ts = esc(str(rep.get("generated_at") or ""))
    cov = _num(rep.get("coverage_pct"))
    cov_txt = f"{cov:.0f}%" if cov is not None else "—"

    body = []
    if not cov:
        body.append('<div class="alert alert-bad">⚠️ 本报告无有效数据板块（覆盖率 0%）——'
                    '可能行情源不可用或标的代码有误，请勿据此做任何判断。</div>')
    elif cov < 60:
        body.append(f'<div class="alert alert-warn">⚠️ 板块覆盖率仅 {cov_txt}，'
                    f'缺失部分已在下方逐项标注「数据不可用」。</div>')

    for key, cn in SECTION_KEYS:
        sec = (rep.get("sections") or {}).get(key) or {}
        avail = bool(sec.get("available"))
        body.append(f'<section><h2>{esc(cn)}'
                    + ("" if avail else ' <span class="badge badge-off">数据不可用</span>')
                    + "</h2>")
        if sec.get("summary"):
            body.append(f'<p class="summary">{esc(str(sec["summary"]))}</p>')
        rows = sec.get("rows") or []
        if rows:
            body.append("<table><tbody>")
            for r in rows:
                label = esc(str(r[0]))
                value = esc(str(r[1]))
                color = _color_for(r[2] if len(r) > 2 else None)
                body.append(f'<tr><th>{label}</th><td style="color:{color}">{value}</td></tr>')
            body.append("</tbody></table>")
        if sec.get("note"):
            body.append(f'<p class="note">{esc(str(sec["note"]))}</p>')
        body.append("</section>")

    warn = rep.get("warnings") or []
    if warn:
        body.append('<section><h2>数据缺失说明</h2><ul>'
                    + "".join(f"<li>{esc(str(w))}</li>" for w in warn)
                    + "</ul></section>")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>研报 · {code} {name}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         max-width: 860px; margin: 0 auto; padding: 28px 20px 60px;
         background: #14161a; color: #e6e6e6; line-height: 1.65; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  h2 {{ font-size: 16px; margin: 26px 0 8px; padding-left: 10px;
        border-left: 4px solid #4a90d9; }}
  .meta {{ color: #9aa0a6; font-size: 13px; margin-bottom: 4px; }}
  .summary {{ margin: 4px 0 8px; color: #cfd3d8; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; width: 38%; color: #9aa0a6; font-weight: 500;
        padding: 5px 8px; border-bottom: 1px solid rgba(255,255,255,.08); }}
  td {{ padding: 5px 8px; border-bottom: 1px solid rgba(255,255,255,.08);
        word-break: break-all; }}
  .note {{ color: #9aa0a6; font-size: 12.5px; margin: 6px 0 0; }}
  .badge {{ font-size: 12px; padding: 1px 8px; border-radius: 10px;
            vertical-align: middle; }}
  .badge-off {{ background: #4a4a4a; color: #d8d8d8; }}
  .alert {{ padding: 10px 14px; border-radius: 8px; margin: 12px 0; font-size: 14px; }}
  .alert-warn {{ background: rgba(245,166,35,.14); border-left: 4px solid #f5a623; }}
  .alert-bad {{ background: rgba(238,42,42,.14); border-left: 4px solid #ee2a2a; }}
  footer {{ margin-top: 34px; padding-top: 12px; font-size: 12.5px; color: #9aa0a6;
            border-top: 1px solid rgba(255,255,255,.1); }}
  @media print {{ body {{ background:#fff; color:#111; }} th {{ color:#555; }}
    td, th {{ border-bottom-color:#ddd; }} h2 {{ border-left-color:#333; }} }}
</style></head><body>
<h1>📄 {code} {name} · 个股研报</h1>
<div class="meta">生成时间：{ts} ｜ 板块覆盖率：{cov_txt}</div>
{''.join(body)}
<footer>{esc(str(rep.get('disclaimer') or _DISCLAIMER))}</footer>
</body></html>"""


def render_markdown(report: dict) -> str:
    """渲染为 Markdown（便于贴进群 / 存档）。"""
    rep = report if isinstance(report, dict) else {}
    lines = [f"# 📄 {rep.get('code')} {rep.get('name')} · 个股研报", ""]
    cov = _num(rep.get("coverage_pct"))
    lines.append(f"- 生成时间：{rep.get('generated_at')}")
    lines.append(f"- 板块覆盖率：{f'{cov:.0f}%' if cov is not None else '—'}")
    lines.append("")
    if not cov:
        lines.append("> ⚠️ 本报告无有效数据板块（覆盖率 0%），请勿据此做任何判断。")
        lines.append("")
    for key, cn in SECTION_KEYS:
        sec = (rep.get("sections") or {}).get(key) or {}
        head = f"## {cn}" + ("" if sec.get("available") else "（数据不可用）")
        lines += [head, ""]
        if sec.get("summary"):
            lines += [str(sec["summary"]), ""]
        rows = sec.get("rows") or []
        if rows:
            lines.append("| 项 | 值 |")
            lines.append("| --- | --- |")
            for r in rows:
                lines.append(f"| {r[0]} | {r[1]} |")
            lines.append("")
        if sec.get("note"):
            lines += [f"_{sec['note']}_", ""]
    warn = rep.get("warnings") or []
    if warn:
        lines += ["## 数据缺失说明", ""] + [f"- {w}" for w in warn] + [""]
    lines += ["---", "", str(rep.get("disclaimer") or _DISCLAIMER)]
    return "\n".join(lines)
