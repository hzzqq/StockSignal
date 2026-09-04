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
