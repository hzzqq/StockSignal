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
    每个刷新命令只出现一次；``stale_sources`` 为该命令覆盖范围内**当前陈旧或停更**的源。
    ``stale_only=False`` 时连「新鲜」的覆盖源也列入 covers 但 stale_sources 仍只含陈旧的。

    注意：判定"是否需要刷新"同时纳入 **stalled**（停更，见 detect_stall）——一个源可能
    lag 还没到 stale 阈值（今天只有 5 天），但 as_of 已连续多日冻结，属"正在坏掉"，
    也应进入刷新计划并提前告警（不等它彻底 stale 才处理）。
    """
    rows = health_rows_enriched()
    by_key = {r["key"]: r for r in rows}
    plan: list[dict] = []
    seen: set[str] = set()
    for cid, c in REFRESH_COMMANDS.items():
        covers_names = [_name_of_key(k) for k in c["covers"]]

        def _is_actionable(k: str) -> bool:
            b = by_key.get(k, {})
            return bool(b.get("status") == "stale" or b.get("stalled"))

        stale_names = [n for k, n in zip(c["covers"], covers_names) if _is_actionable(k)]
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


# ───────────────────────── 源停更检测（Direction #2，区别于 lag-based stale） ─────────────────────────
# 痛点：assess_freshness 只按「as_of 距今天数」判 stale；但一个源"今天 lag=5(还 warn)、
# 却已连续 5 天没推进过 as_of"这种"正在冻结"的状态，靠 lag 看不出来——要等 lag 滚到 8 才报警。
# 停更检测 = 拿"该源历史上最后推进到哪天"和"今天"比：冻结超过 STALL_DAYS 天即 stalled，
# 不等它变成 stale 就提前告警（对应掘金/米筐的"数据质量/Point-in-Time"严谨性）。
import sqlite3 as _sqlite3

STALL_DAYS = 5  # 同一 as_of 冻结超过该自然日数 → 判定停更(stalled)，提前于 stale 报警

_HEALTH_TABLE = "data_source_health"


def _health_db_path() -> str:
    return os.path.join(_DATA_DIR, "market_cache.db")


def _ensure_health_table() -> None:
    try:
        with _sqlite3.connect(_health_db_path()) as conn:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_HEALTH_TABLE} ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " source_key TEXT NOT NULL,"      # 源 key（与 DATA_SOURCES 对齐）
                " observed_at TEXT NOT NULL,"      # 观测写入时间（真实时刻）
                " as_of TEXT,"                     # 该源当时的真实数据截止日
                " status TEXT,"
                " lag_days INTEGER)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{_HEALTH_TABLE}_key_obs"
                f" ON {_HEALTH_TABLE}(source_key, observed_at)"
            )
    except Exception:  # noqa: BLE001
        pass


def record_health_observation(rows: list[dict] | None = None) -> int:
    """把当前逐源健康快照落盘（供停更检测/趋势）。返回写入行数。

    失败（无写权限/锁）静默返回 0，绝不因「记录失败」影响看板/决策渲染。
    """
    rows = rows if rows is not None else health_rows()
    _ensure_health_table()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    try:
        with _sqlite3.connect(_health_db_path()) as conn:
            for r in rows:
                conn.execute(
                    f"INSERT INTO {_HEALTH_TABLE}"
                    "(source_key, observed_at, as_of, status, lag_days) VALUES (?,?,?,?,?)",
                    (r["key"], now, r.get("as_of"), r.get("status"), r.get("lag_days")),
                )
                n += 1
    except Exception:  # noqa: BLE001
        return 0
    return n


def detect_stall(key: str | None = None) -> dict:
    """返回各源停更状态：``{key: {stalled, frozen_days, last_as_of, last_advanced_at}}``。

    ``stalled=True`` 当且仅当：该源有观测历史、其 ``as_of`` **最后一次变大（推进）**的那次
    观测距今 ≥``STALL_DAYS``，且历史最大 ``as_of`` 仍早于今天（确实没推进到今日）。

    与 lag-based ``stale`` 的区别：``stale`` 只看「as_of 距今天数」，一个日更源冻结 5 天
    时 lag 也才 5（还没到 stale 阈值）就已经是「正在坏掉」；本函数按「停更」提前告警。
    观测窗口内 as_of 从未推进时，退化为从**首次观测**算起（否则永远不报警）。
    无历史/异常 → 该源 ``stalled=False``（不误报）；单源查询可用 ``key`` 缩小范围。
    """
    _ensure_health_table()
    keys = [key] if key else [e["key"] for e in DATA_SOURCES]
    out: dict = {}
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with _sqlite3.connect(_health_db_path()) as conn:
            for k in keys:
                # 必须按时间**升序**回溯：要找的是「as_of 最后一次变大」发生在哪一次观测。
                # 若按 DESC 走，第一次命中 max_as_of 的就是最新一次观测，frozen 会退化成
                # 「距上次观测天数」——那就不是"停更"而是"多久没看"，会漏判正在冻结的源。
                cur = conn.execute(
                    f"SELECT observed_at, as_of FROM {_HEALTH_TABLE}"
                    " WHERE source_key=? ORDER BY observed_at ASC",
                    (k,),
                )
                rows = cur.fetchall()
                if not rows:
                    out[k] = {"stalled": False, "frozen_days": None,
                              "last_as_of": None, "last_advanced_at": None}
                    continue
                last_advance_date: str | None = None
                first_obs_date: str | None = None
                prev_asof: str | None = None
                max_as_of: str | None = None
                for obs, ao in rows:
                    obs_date = (obs or "")[:10]
                    if first_obs_date is None and obs_date:
                        first_obs_date = obs_date
                    if ao and (max_as_of is None or ao > max_as_of):
                        max_as_of = ao
                    # 只有 as_of 严格变大才算「推进」，冻结/回退都不更新 last_advance
                    if prev_asof is None or (ao or "") > (prev_asof or ""):
                        last_advance_date = obs_date
                    prev_asof = ao
                # 全程 as_of 从未推进（观测窗口内一直是同一个日期）→ 从首次观测算起，
                # 否则一个"一开始就冻结"的源会因为 last_advance 永远等于最新观测而永不报警。
                ref_date = last_advance_date or first_obs_date
                frozen = None
                if ref_date:
                    try:
                        frozen = (datetime.now() - datetime.strptime(
                            ref_date, "%Y-%m-%d")).days
                    except Exception:  # noqa: BLE001
                        frozen = None
                stalled = bool(
                    ref_date and frozen is not None
                    and frozen >= STALL_DAYS
                    and (max_as_of or "") < today
                )
                out[k] = {"stalled": stalled, "frozen_days": frozen,
                          "last_as_of": max_as_of, "last_advanced_at": last_advance_date}
    except Exception:  # noqa: BLE001
        for k in keys:
            out.setdefault(k, {"stalled": False, "frozen_days": None,
                               "last_as_of": None, "last_advanced_at": None})
    return out


def health_rows_enriched() -> list[dict]:
    """``health_rows`` + 每源 ``stalled``/``frozen_days`` 标记（供 SLA 看板/报警）。"""
    rows = health_rows()
    stalls = detect_stall()
    for r in rows:
        s = stalls.get(r["key"], {})
        r["stalled"] = s.get("stalled", False)
        r["frozen_days"] = s.get("frozen_days")
        r["last_as_of"] = s.get("last_as_of")
    return rows

