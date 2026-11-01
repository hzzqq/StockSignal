"""modules/quotes_health.py —— 行情/指数/ETF 取数层健康体检（方向 3 延续）。

用途
====
modules/linear_trends.py 是行情取数层（指数=新浪源，行业板块/ETF=东方财富源，
TTL 缓存 + 12s 硬超时 + 失败空 DataFrame 兜底）。本模块对三组日频行情序列做
确定性体检，把「取数静默失败 / 结构漂移 / 日频断供」变成显性告警：

  1. index         三大指数日线（sh000001/sz399001/sz399006，ak.stock_zh_index_daily）
  2. industry_board 行业板块指数日线（东财 stock_board_industry_hist_em）
  3. etf           8 只 ETF 日线（东财 fund_etf_hist_em）

体检项：
  - 可用性：provider 返回非空宽表即可取数；空 = 降级触发（页面展示兜底）。
  - 结构：index 必须三列齐全；industry/etf 必须至少 1 个数据列（date 之外）。
  - 新鲜度：宽表最新日期距参考交易日（trading_calendar 官方休市表修正）超标即红灯。

设计约束
========
  - 纯函数 + provider 注入（默认真实 linear_trends 函数，测试注入 fake），零网络可测。
  - 新鲜度/交易日工具复用 modules.fundflow_health（同一口径，避免重复实现）。
  - 三档语义与 fundflow_health 对齐：红灯阻断 / 黄灯登记 / 绿灯全达标。
"""
from __future__ import annotations

from datetime import date
from typing import Callable

from modules.fundflow_health import age_in_days, last_trading_day

# 结构契约（与 modules/linear_trends.py 输出对齐）
INDEX_KEYS = ["sh000001", "sz399001", "sz399006"]          # 上证/深成/创业板
DATE_KEY = "date"


def check_index(df, today: date | None = None,
                required_keys=INDEX_KEYS) -> dict:
    """三大指数日线：非空 + 三列齐全 + 最新日期新鲜度。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if df is None or (hasattr(df, "empty") and df.empty):
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("指数日线为空（取数降级，页面展示兜底）")
        return rec
    missing = [c for c in required_keys if c not in getattr(df, "columns", [])]
    if missing:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"指数缺列: {missing}")
    if rec["ok"] and DATE_KEY in getattr(df, "columns", []):
        _apply_freshness(df, rec, today)
    return rec


def check_industry_board(df, today: date | None = None, min_cols=1) -> dict:
    """行业板块指数日线（宽表）：非空 + ≥1 数据列 + 最新日期新鲜度。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if df is None or (hasattr(df, "empty") and df.empty):
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("行业板块指数为空（取数降级，页面展示兜底）")
        return rec
    data_cols = [c for c in getattr(df, "columns", []) if c != DATE_KEY]
    if len(data_cols) < min_cols:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"行业板块指数无数据列（列数不足）")
        return rec
    if rec["ok"] and DATE_KEY in getattr(df, "columns", []):
        _apply_freshness(df, rec, today)
    return rec


def check_etf(df, today: date | None = None, min_cols=1) -> dict:
    """ETF 日线（宽表）：非空 + ≥1 数据列 + 最新日期新鲜度。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if df is None or (hasattr(df, "empty") and df.empty):
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("ETF 日线为空（取数降级，页面展示兜底）")
        return rec
    data_cols = [c for c in getattr(df, "columns", []) if c != DATE_KEY]
    if len(data_cols) < min_cols:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("ETF 无数据列（列数不足）")
        return rec
    if rec["ok"] and DATE_KEY in getattr(df, "columns", []):
        _apply_freshness(df, rec, today)
    return rec


def _apply_freshness(df, rec: dict, today: date | None) -> None:
    """宽表最新日期新鲜度判定（写入 rec）。"""
    try:
        last = str(df[DATE_KEY].astype(str).iloc[-1])[:10]
    except Exception as e:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"最新日期不可读: {e}")
        return
    fresh = _freshness_status(last, today)
    rec["status"] = fresh["status"]
    rec["age_days"] = fresh["age_days"]
    if not fresh["ok"]:
        rec["ok"] = False
        rec["errors"].append(fresh["note"])


def _freshness_status(latest_date: str, today: date | None = None) -> dict:
    """日频序列新鲜度判定：绿 / 黄(边缘) / 红(断供)。与 fundflow_health 同口径。"""
    rec = {"ok": True, "status": "ok", "age_days": None, "note": ""}
    age = age_in_days(latest_date, today)
    rec["age_days"] = age
    if age is None:
        rec["ok"] = False
        rec["status"] = "red"
        rec["note"] = f"最新日期缺失或不可解析: {latest_date!r}"
        return rec
    if age > 6:
        rec["ok"] = False
        rec["status"] = "red"
        rec["note"] = f"日频数据断供 {age} 天（> 6 天；最近交易日 {last_trading_day(today)})"
    elif age > 3:
        rec["status"] = "yellow"
        rec["note"] = f"新鲜度边缘 {age} 天（宽容带内）"
    return rec


# ───────────────────────── 汇总 ─────────────────────────
def summarize(providers: dict[str, Callable], today: date | None = None) -> dict:
    """跑全量行情体检。providers 为 {名称: 无参可调用}，返回该接口真实产物。

    命名约定：index / industry_board / etf。
    """
    today = today or date.today()
    rows = []

    def _add(name, checker):
        try:
            raw = providers[name]()
        except KeyError:
            rows.append({"model": name, "status": "skipped", "errors": [],
                         "note": "本次未探测（调用方跳过）"})
            return
        except Exception as e:  # provider 本身抛异常 = 红灯
            rows.append({"model": name, "status": "red",
                         "errors": [f"接口调用异常: {type(e).__name__}: {e}"],
                         "note": ""})
            return
        rec = checker(raw, today) if name in ("index", "industry_board", "etf") else checker(raw)
        rows.append({"model": name, "status": rec["status"],
                     "errors": rec.get("errors", []), "note": rec.get("note", "")})

    _add("index", check_index)
    _add("industry_board", check_industry_board)
    _add("etf", check_etf)

    red = [r for r in rows if r["status"] == "red"]
    yellow = [r for r in rows if r["status"] == "yellow"]
    return {
        "ok_all": not red,
        "rows": rows,
        "red": red,
        "yellow": yellow,
        "today": today.isoformat(),
    }


# ───────────────────────── 报告渲染 ─────────────────────────
def render_report(summary: dict) -> str:
    """Markdown 报告（供 CLI 与文档使用）。"""
    lines = ["# 行情取数层健康体检 — %s" % summary["today"]]
    lines.append("")
    lines.append("| 接口 | 状态 | 问题 |")
    lines.append("|---|---|---|")
    for r in summary["rows"]:
        icon = {"red": "❌", "yellow": "🟡", "ok": "✅", "skipped": "⏭"}.get(r["status"], "❌")
        err = "; ".join(r["errors"]) or r["note"] or "—"
        lines.append(f"| {r['model']} | {icon} {r['status']} | {err} |")
    lines.append("")
    if summary["red"]:
        lines.append(f"**结论**：❌ {len(summary['red'])} 个接口红灯，需处理（页面可能在展示兜底数据）")
    elif summary["yellow"]:
        lines.append(f"**结论**：🟡 全绿无红灯；{len(summary['yellow'])} 个接口边缘状态（登记，不阻断）")
    else:
        lines.append("**结论**：✅ 全绿（全部接口可取数且结构/新鲜度达标）")
    return "\n".join(lines)
