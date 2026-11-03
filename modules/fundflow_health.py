"""modules/fundflow_health.py —— fundflow 资金流/财报数据层健康体检（方向 3 延续）。

用途
====
fundflow.py 是实时取数层（akshare → 东方财富，TTL 缓存 + 失败降级为空）。
本模块对每个公开接口做确定性体检，把「取数静默失败 / 结构漂移 / 日频数据断供」
变成显性告警：

  1. 接口可用性：provider 返回非空（df 非空 / dict 非空）即认为可取数；
     返回空 = 降级触发（红灯：页面展示的是兜底而非真数据）。
  2. 结构体检：必需列/键齐全（与 modules/fundflow.py 的输出契约对齐）。
  - 新鲜度 SLA：日频序列（北向历史、大盘资金流）的最新日期距参考交易日
     超标即红灯；参考交易日用 modules.trading_calendar 的交易所官方休市表
     （2026 内置），长假/春节不再误报；无表年份回退非周末近似。
  4. 汇总：summarize() 综合成 ok_all（红灯阻断，黄灯登记不阻断）。

设计约束
========
  - 纯函数 + provider 注入（默认真实 fundflow，测试注入 fake），零网络依赖可测。
  - 不 import modules.fundflow 的副作用（代理探测惰性），仅当 CLI 绑定真实 provider 时触达网络。
  - 新鲜度口径：交易日 = 最近的非周末自然日（节假日由宽容带 1~3 天覆盖，注释在案）；
    northbound_history 语义为「停披露前真实值兜底」，只查结构、豁免新鲜度。
  - 三档语义与 p1_signal_quality 对齐：红灯 = 不可用/结构缺失/新鲜度超标（阻断）；
    黄灯 = 空数据 best-effort / 新鲜度边缘（登记）；绿灯 = 全达标。
"""
from __future__ import annotations

from datetime import date
from typing import Callable

# ───────────────────────── 常量与默认阈值 ─────────────────────────

# 日频序列新鲜度 SLA（自然日）：数据最新日期距「参考交易日」超过 RED 天即红灯
# 参考交易日 = 今天的前一个非周末日（体检多在盘前跑，当日数据尚未产出；
# 周一盘前取上周五，age=0 不误报）。A 股法定长假/春节会导致参考日落在休市日，
# 数据停在长假前（age≈7~9）会被判红——属已知口径限制，遇长假人工确认或后续接交易日历。
DEFAULT_MAX_AGE_DAYS = 3
# 新鲜度宽容带：差 > WARN 天 → 黄灯登记；差 > RED 天 → 红灯
FRESHNESS_WARN_DAYS = 3
FRESHNESS_RED_DAYS = 6

# 结构契约（与 modules/fundflow.py 输出对齐）
INDUSTRY_KEYS = ["行业", "涨跌幅", "流入资金", "流出资金", "净额"]
MARKET_FF_KEYS = ["日期", "主力净流入-净额"]
NORTHBOUND_HIST_KEYS = ["last_net_buy", "last_net_buy_date", "cumulative", "cumulative_date"]
NORTHBOUND_FF_KEYS = ["trade_date", "total_inflow", "sh_inflow", "sz_inflow"]
EARNINGS_KEYS = ["每股收益", "净利润", "净利润同比%", "营业总收入"]
FORECAST_MIN_COLS = 1
DISCLOSURE_MIN_COLS = 1

# 报告期（默认最近披露窗口：2026 三季报）
DEFAULT_EARNINGS_PERIOD = "20260930"
DEFAULT_DISCLOSURE_MARKET = "沪深京"
DEFAULT_DISCLOSURE_PERIOD = "2026年报"


# ───────────────────────── 交易日工具 ─────────────────────────
def last_trading_day(today: date | None = None) -> date:
    """参考交易日：今天的前一个交易日（盘前语义，当日数据尚未产出）。

    用 modules.trading_calendar 的官方休市表（2026 内置）消除长假误报；
    无表年份（其他年份）回退非周末近似。
    """
    from modules.trading_calendar import prev_trading_day
    return prev_trading_day(today or date.today())


def age_in_days(latest_date: str | None, today: date | None = None) -> int | None:
    """latest_date(YYYY-MM-DD) 距最近交易日的自然日差；解析失败返回 None。"""
    if not latest_date:
        return None
    try:
        latest = date.fromisoformat(latest_date)
    except ValueError:
        # ui_audit_exempt: 输入类型/取值非法时返回空，防御性契约（非数据缺失）
        return None
    ref = last_trading_day(today)
    return max((ref - latest).days, 0)


def _freshness_status(latest_date: str | None, today: date | None = None) -> dict:
    """日频序列新鲜度判定：绿 / 黄(边缘) / 红(断供)。"""
    rec = {"ok": True, "status": "ok", "age_days": None, "note": ""}
    age = age_in_days(latest_date, today)
    rec["age_days"] = age
    if age is None:
        rec["ok"] = False
        rec["status"] = "red"
        rec["note"] = f"最新日期缺失或不可解析: {latest_date!r}"
        return rec
    if age > FRESHNESS_RED_DAYS:
        rec["ok"] = False
        rec["status"] = "red"
        rec["note"] = f"日频数据断供 {age} 天（> {FRESHNESS_RED_DAYS} 天；最近交易日 {last_trading_day(today)})"
    elif age > FRESHNESS_WARN_DAYS:
        rec["status"] = "yellow"
        rec["note"] = f"新鲜度边缘 {age} 天（宽容带内）"
    return rec


# ───────────────────────── 单项体检 ─────────────────────────
def check_industry(df, required_keys=INDUSTRY_KEYS) -> dict:
    """行业资金流向（快照）：非空 + 必需列齐全。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if df is None or (hasattr(df, "empty") and df.empty):
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("行业资金流为空（取数降级，页面展示兜底）")
        return rec
    if not isinstance(df, object):
        pass
    missing = [c for c in required_keys if c not in getattr(df, "columns", [])]
    if missing:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"行业资金流缺列: {missing}")
    return rec


def check_northbound_history(d, required_keys=NORTHBOUND_HIST_KEYS) -> dict:
    """北向历史（dict，停披露语义）：只查结构，豁免新鲜度。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if not d:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("北向历史为空（取数失败）")
        return rec
    missing = [k for k in required_keys if k not in d]
    if missing:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"北向历史缺键: {missing}")
    if rec["ok"]:
        rec["note"] = ("北向 2024-08-16 起停披露实时净买额，历史序列为真实值兜底，"
                       "新鲜度豁免（只查结构）")
    return rec


def check_northbound_fund_flow(d, today: date | None = None,
                               required_keys=NORTHBOUND_FF_KEYS) -> dict:
    """北向资金汇总（dict）：结构 + trade_date 新鲜度。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if not d:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("北向资金汇总为空（取数失败）")
        return rec
    missing = [k for k in required_keys if k not in d]
    if missing:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"北向资金汇总缺键: {missing}")
    trade_date = d.get("trade_date")
    if trade_date and rec["ok"]:
        fresh = _freshness_status(str(trade_date), today)
        rec["status"] = fresh["status"]
        rec["age_days"] = fresh["age_days"]
        if not fresh["ok"]:
            rec["ok"] = False
            rec["errors"].append(fresh["note"])
    return rec


def check_market_fund_flow(df, today: date | None = None,
                           required_keys=MARKET_FF_KEYS) -> dict:
    """大盘资金流（日频 df）：非空 + 列齐全 + 最新日期新鲜度。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if df is None or (hasattr(df, "empty") and df.empty):
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("大盘资金流为空（取数降级，页面展示兜底）")
        return rec
    missing = [c for c in required_keys if c not in getattr(df, "columns", [])]
    if missing:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"大盘资金流缺列: {missing}")
    if rec["ok"] and "日期" in getattr(df, "columns", []):
        last = df["日期"].astype(str).iloc[-1]
        fresh = _freshness_status(last[:10], today)
        rec["status"] = fresh["status"]
        rec["age_days"] = fresh["age_days"]
        if not fresh["ok"]:
            rec["ok"] = False
            rec["errors"].append(fresh["note"])
    return rec


def check_earnings_report(df, required_keys=EARNINGS_KEYS) -> dict:
    """业绩报表（df）：非空 + 关键列齐全。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if df is None or (hasattr(df, "empty") and df.empty):
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append("业绩报表为空（取数降级）")
        return rec
    missing = [c for c in required_keys if c not in getattr(df, "columns", [])]
    if missing:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"业绩报表缺列: {missing}")
    return rec


def check_best_effort(df, name: str, min_cols=1) -> dict:
    """best-effort 接口（业绩预告/披露日历）：非空即绿，空 = 黄灯登记。"""
    rec = {"ok": True, "status": "ok", "errors": [], "note": ""}
    if df is None or (hasattr(df, "empty") and df.empty):
        rec["status"] = "yellow"
        rec["errors"].append(f"{name}为空（best-effort 接口，可能接口暂不可用）")
    elif len(getattr(df, "columns", [])) < min_cols:
        rec["ok"] = False
        rec["status"] = "red"
        rec["errors"].append(f"{name}结构异常（列数 < {min_cols}）")
    return rec


# ───────────────────────── 汇总 ─────────────────────────
def summarize(providers: dict, today: date | None = None,
              earnings_period: str = DEFAULT_EARNINGS_PERIOD,
              disclosure_market: str = DEFAULT_DISCLOSURE_MARKET,
              disclosure_period: str = DEFAULT_DISCLOSURE_PERIOD) -> dict:
    """跑全量 fundflow 体检。providers 为 {名称: 无参可调用}，返回该接口真实产物。

    命名约定：industry / northbound_history / northbound_fund_flow / market_fund_flow /
              earnings_report / earnings_forecast / disclosure_calendar。
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
        rec = checker(raw, today) if name in (
            "northbound_fund_flow", "market_fund_flow") else checker(raw)
        rows.append({"model": name, "status": rec["status"],
                     "errors": rec.get("errors", []), "note": rec.get("note", "")})

    _add("industry", check_industry)
    _add("northbound_history", check_northbound_history)
    _add("northbound_fund_flow", check_northbound_fund_flow)
    _add("market_fund_flow", check_market_fund_flow)
    _add("earnings_report", check_earnings_report)
    _add("earnings_forecast", lambda df: check_best_effort(df, "业绩预告"))
    _add("disclosure_calendar", lambda df: check_best_effort(df, "披露日历"))

    red = [r for r in rows if r["status"] == "red"]
    yellow = [r for r in rows if r["status"] == "yellow"]
    return {
        "ok_all": not red,
        "rows": rows,
        "red": red,
        "yellow": yellow,
        "today": today.isoformat(),
        "earnings_period": earnings_period,
        "disclosure_period": disclosure_period,
    }


# ───────────────────────── 报告渲染 ─────────────────────────
def render_report(summary: dict) -> str:
    """Markdown 报告（供 CLI 与文档使用）。"""
    lines = ["# fundflow 数据层健康体检 — %s" % summary["today"]]
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
        lines.append(f"**结论**：🟡 全绿无红灯；{len(summary['yellow'])} 个 best-effort 接口空（登记，不阻断）")
    else:
        lines.append("**结论**：✅ 全绿（全部接口可取数且结构/新鲜度达标）")
    return "\n".join(lines)
