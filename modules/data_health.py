# -*- coding: utf-8 -*-
"""决策依赖的「全数据源健康」注册表与统一新鲜度判定。

背景（承接「数据新鲜度守卫」capstone，自找缺口 S9）：
    此前的守卫只覆盖「牧羊人情绪 + P1 事件因子」两个源。但决策闭环实际还依赖
    连板晋级率、事件池、市场温度缓存、今日快照等源——它们一旦陈旧，面板同样是
    「拿旧数据当当日结论」却零提示。本模块把**所有**决策相关源登记成一张表，
    各自抽取真实数据截止日（内容优先、文件 mtime 兜底），统一交给 ``assess_freshness``
    判定，做到「任一源陈旧 → 整体告警」。

设计要点：
- 抽取器全部惰性 + 容错：任一源读不到/解析失败都返回 ``None``（status=unknown），
  绝不因单源异常让整个健康看板崩掉。
- 内容优先：能直接从数据里拿到真实截止日（如 CSV 末行日期、信号 latest_date、
  快照 date 字段）就用它；拿不到才退到文件 mtime（mtime 只代表「文件更新过」，
  不代表「数据日期」，故标 unknown 风险更低时仍按 mtime 提示而非静默）。
- P1 事件因子复用 ``P1SignalLoader`` 的内容 latest_date（与 _event_position_adj 同源，
  其内置 ttl 缓存，重复调用不重读 11MB）。
- 本模块不触网、只读本地文件，离线可跑；CI / 用户均可 `python scripts/check_data_health.py`。
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime

from modules.decision import assess_freshness

# 项目根 / data 目录（data_health.py 在 modules/ 下，根在上两级）
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")


# ───────────────────────── 各类抽取器（惰性 + 容错） ─────────────────────────
def _csv_last_date_col(path: str, col: int = 0) -> str | None:
    """CSV 末行第 ``col`` 列的日期（兼容 ``YYYY-MM-DD`` 与 ``YYYY-MM-DD HH:MM:SS``）。"""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if len(rows) < 2:
            return None
        val = (rows[-1][col] or "").strip()
        return val[:10] if val else None
    except Exception:  # noqa: BLE001
        return None


def _json_date_field(path: str, field: str) -> str | None:
    """JSON 文件的某个日期字段（取前 10 位）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        v = d.get(field)
        return str(v)[:10] if v else None
    except Exception:  # noqa: BLE001
        return None


def _mtime_date(path: str) -> str | None:
    """文件 mtime 作为「最后更新日」兜底（仅代表文件被改写过）。"""
    try:
        if not os.path.exists(path):
            return None
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _p1_event_latest_date() -> str | None:
    """P1 事件信号真实数据截止日（内容 latest_date，与决策同源）。"""
    try:
        from modules.p1_signal import P1SignalLoader
        return P1SignalLoader(ttl=300).latest_date("ev")
    except Exception:  # noqa: BLE001
        return None


def _track_last_scored_date() -> str | None:
    """校准回测样本（prediction_log）最近一次成功打分的日期——校准证据的「数据截止日」。

    这是决策闭环的「第二层」数据依赖：决策输入源（牧羊人/P1/…）陈旧会让仓位失真，
    而**校准证据源**陈旧会让 CYCLE_ADJ 补丁基于过期回测被误采纳。两者都必须入守卫。
    """
    try:
        from modules.decision_track import last_scored_date
        return last_scored_date()
    except Exception:  # noqa: BLE001
        return None


# ───────────────────────── 决策数据源注册表 ─────────────────────────
# kind 决定抽取方式；path 用于 csv/json/mtime；col/field 用于字段定位。
DATA_SOURCES: list[dict] = [
    {"key": "shepherd_sentiment", "name": "牧羊人情绪", "kind": "csv_last_date",
     "path": os.path.join(_DATA_DIR, "shepherd_history.csv"), "col": 0},
    {"key": "p1_event", "name": "P1 事件因子", "kind": "p1_latest_date", "path": None},
    {"key": "ladder", "name": "连板晋级率", "kind": "mtime",
     "path": os.path.join(_DATA_DIR, "shepherd_ladder_history.json")},
    {"key": "event_pool", "name": "事件池", "kind": "csv_last_date",
     "path": os.path.join(_DATA_DIR, "events.csv"), "col": 0},
    {"key": "market_temp", "name": "市场温度缓存", "kind": "mtime",
     "path": os.path.join(_DATA_DIR, "market_cache.db")},
    {"key": "daily_snapshot", "name": "今日快照", "kind": "json_date_field",
     "path": os.path.join(_DATA_DIR, "daily_snapshot.json"), "field": "date"},
    # 校准证据源：prediction_log 最近一次打分日（与决策输入源同等重要，须入守卫）
    {"key": "calibration_evidence", "name": "校准回测样本", "kind": "track_last_scored",
     "path": None},
]


def source_as_of(entry: dict) -> str | None:
    """按注册表条目抽取单一源的真实数据截止日。"""
    k = entry.get("kind")
    if k == "csv_last_date":
        return _csv_last_date_col(entry["path"], entry.get("col", 0))
    if k == "json_date_field":
        return _json_date_field(entry["path"], entry.get("field"))
    if k == "p1_latest_date":
        return _p1_event_latest_date()
    if k == "track_last_scored":
        return _track_last_scored_date()
    if k == "mtime":
        return _mtime_date(entry["path"])
    return None


def assess_all_sources() -> dict:
    """汇总全部决策数据源的新鲜度，返回 ``assess_freshness`` 同构结果。

    ``sources`` 字段为 ``{源名: {as_of, lag_days, status}}``，可直接渲染成健康看板。
    任一源抽取失败 → 该源 status=unknown，但不影响其它源的判定。
    """
    sources = {e["name"]: source_as_of(e) for e in DATA_SOURCES}
    return assess_freshness(sources)


def health_rows() -> list[dict]:
    """看板友好的逐源行：``[{key, name, as_of, lag_days, status}]``。"""
    fr = assess_all_sources()
    rows: list[dict] = []
    for e in DATA_SOURCES:
        s = fr["sources"].get(e["name"], {})
        rows.append({
            "key": e["key"],
            "name": e["name"],
            "as_of": s.get("as_of"),
            "lag_days": s.get("lag_days"),
            "status": s.get("status", "unknown"),
        })
    return rows


# ───────────────────────── 刷新注册表（陈旧→可一键刷新，绝不伪造成功） ─────────────────────────
# 守卫的最后一环：只「暴露滞后」不「自动刷新」＝闭环没真正活起来。
# 这里登记每个源「怎么刷新」，CLI 据此生成去重命令清单 / 尝试执行。
# mode:
#   live     —— 需联网，在本仓可直接跑（沙箱无网会失败，如实报 failed，不伪造成功）
#   external —— 数据来自独立仓库（P1-QuantFactor），本仓无入口，需跨仓流水线
# 注意：当前本仓所有刷新路径都依赖联网/跨仓（market_temp 的 refresh_all_indicators
#       底层走 akshare；shepherd/ladder/snapshot 走 daily_snapshot 联网抓取；
#       event_pool 走 refresh_event_db 抓东财）。沙箱内均会失败——这是诚实现实，
#       不是 bug。CLI --exec 在真机/CI（有网）才会真正刷新成功。
REFRESH_COMMANDS: dict[str, dict] = {
    "daily_snapshot": {
        "cmd": "python scripts/daily_snapshot.py",
        "mode": "live",
        "covers": ["shepherd_sentiment", "ladder", "daily_snapshot"],
        "desc": "抓今日牧羊人指标+连板梯队+推导仓位并落盘（一条命令覆盖 3 源）",
    },
    "event_pool": {
        "cmd": "python scripts/refresh_event_db.py",
        "mode": "live",
        "covers": ["event_pool"],
        "desc": "重抓东方财富新闻→情感分析→追加入库 events.csv",
    },
    "market_temp": {
        "cmd": 'python -c "from modules.market_cache import refresh_all_indicators; refresh_all_indicators(force=True)"',
        "mode": "live",
        "covers": ["market_temp"],
        "desc": "重算市场温度/驱动指标缓存（底层走 akshare，需联网）",
    },
    "p1_event": {
        "cmd": ("# 事件因子信号由独立仓库 P1-QuantFactor 生成 signal_ev_h10.json；\n"
                "# 在该仓库重新生成后，复制/软链回本仓 data/p1_signals/ 即可。"),
        "mode": "external",
        "covers": ["p1_event"],
        "desc": "事件因子信号来自独立仓库 P1-QuantFactor；本仓无刷新入口，需跨仓流水线触发",
    },
    "calibration_evidence": {
        "cmd": "python scripts/daily_snapshot.py --score-only",
        "mode": "live",
        "covers": ["calibration_evidence"],
        "desc": "重新给历史预测打次日涨跌分，刷新校准回测样本 prediction_log（不抓数据）",
    },
}
# 源 key -> 刷新命令 id（与 REFRESH_COMMANDS 对齐）
_SOURCE_REFRESH: dict[str, str] = {
    e["key"]: cid for cid, c in REFRESH_COMMANDS.items()
    for e in DATA_SOURCES if e["key"] in c["covers"]
}


def build_refresh_plan(stale_only: bool = True) -> list[dict]:
    """生成刷新计划（去重）。

    返回 ``[{cmd_id, cmd, mode, desc, covers:[源名], stale_sources:[源名]}]``，
    每个刷新命令只出现一次；``stale_sources`` 为该命令覆盖范围内**当前陈旧**的源。
    ``stale_only=False`` 时连「新鲜」的覆盖源也列入 covers 但 stale_sources 仍只含陈旧的。
    """
    rows = health_rows()
    by_key = {r["key"]: r for r in rows}
    plan: list[dict] = []
    seen: set[str] = set()
    for cid, c in REFRESH_COMMANDS.items():
        covers_names = [_name_of_key(k) for k in c["covers"]]
        stale_names = [n for k, n in zip(c["covers"], covers_names)
                       if by_key.get(k, {}).get("status") == "stale"]
        if stale_only and not stale_names:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        plan.append({
            "cmd_id": cid,
            "cmd": c["cmd"],
            "mode": c["mode"],
            "desc": c["desc"],
            "covers": covers_names,
            "stale_sources": stale_names,
        })
    return plan


def _name_of_key(key: str) -> str:
    for e in DATA_SOURCES:
        if e["key"] == key:
            return e["name"]
    return key

