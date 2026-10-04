"""modules/data_provenance.py — 全站数据来源底账（H1+ 方向 A 核心，单一真理源）。

定位：把「结论怎么来的、可不可信」从 H1 研究智能体回答内，**下沉为可程序化查询的底账**——
给定数据源 key，返回 `{key, name, as_of, lag_days, status, is_fallback, source_chain}`，
供全站卡片挂「ⓘ 数据来源」徽标（`ui_kit.prov_badge`）。

设计铁律：
- **单一真理源（AC-A1）**：新鲜度/滞后口径**全部复用 `modules.data_health`**（其内部复用
  `modules.decision.assess_freshness` 的 FRESH_WARN_DAYS/FRESH_STALE_DAYS）。本模块
  **不定义任何阈值常量**，杜绝第二套口径漂移。
- **诚实语义（AC-A2）**：源取不到 → `as_of=None / status="unknown"`，如实标注、绝不臆造；
  `is_fallback`/`source_chain` 仅在**调用方确知**链路时由 `includes` 传入（缺省 None=未知，
  不编造链路）。
- **零破坏（AC-A5）**：未登记的页面/卡片 `sources_for()` 返回 `[]`，调用方据此 no-op；未知 key
  返回 unknown 行，不抛错。
- **只读**：不触发任何取数/写盘/网络。
"""
from __future__ import annotations

import logging

from modules import data_health

logger = logging.getLogger(__name__)

# ── 页面/卡片 → 依赖源 key（声明式登记）────────────────────────────────
# key 取自 data_health.DATA_SOURCES（源定义**不在此重复**，仅登记「谁依赖谁」）。
# 未登记的页面 = 不渲染徽标（AC-A5 零破坏）。
PAGE_SOURCES: dict[str, list[str]] = {
    # ★ 诚实优先：仅登记「页面的数据**确实**来自 data_health 注册表源」的映射，绝不虚挂。
    #  54_今日决策面板：牧羊人情绪 / P1 事件因子 / 连板晋级率 / 今日快照 / 校准样本
    #  （decision 决策链，见该页 import data_health + render_freshness_badge）。
    "54_今日决策面板": ["shepherd_sentiment", "p1_event", "ladder",
                        "daily_snapshot", "calibration_evidence"],
    # ★ 以下页面**暂不登记**（勘测实证后如实留白，勿猜）：
    #  · 10_行情看板（指数迷你卡 = 实时指数行情）、76_实时强势榜（ems/akshare/腾讯三层）、
    #    24_个股研究（个股实时/财务）等，数据来自**实时行情/三方源**，**不在** data_health
    #    注册表内。若要对它们溯源，须先**扩展注册表**（登记这些源及其 as_of 抽取方式，另立批次），
    #    否则把 decision 源挂上去＝误导用户。
}

# key → 源定义（复用 data_health 注册表，不自建）
_BY_KEY: dict[str, dict] = {e["key"]: e for e in data_health.DATA_SOURCES}


def source_keys() -> list[str]:
    """全部已登记源 key（顺序同 data_health.DATA_SOURCES）。"""
    return list(_BY_KEY)


def sources_for(slug: str) -> list[str]:
    """页面/卡片 slug → 依赖源 key 列表；未登记返回 ``[]``（调用方据此 no-op，AC-A5）。"""
    return list(PAGE_SOURCES.get(slug, []))


def build_provenance(source_key_list: list[str] | None = None, *,
                     includes: dict | None = None) -> list[dict]:
    """构造来源底账（逐源一行）。

    :param source_key_list: 要查询的源 key 列表；None = 全部已登记源。
    :param includes: 可选 `{key: {"is_fallback": bool|None, "source_chain": list|None}}`
        —— 页面**确知**链路/回退时传入；缺省即未知（None），不编造。
    :return: `[{key, name, as_of, lag_days, status, is_fallback, source_chain}]`

    新鲜度**唯一取自** `data_health.assess_all_sources()`（AC-A1）——本函数不做任何
    阈值判定，仅做键映射与字段组装。
    """
    fr = data_health.assess_all_sources()          # 单一真理源（内部复用 assess_freshness）
    keys = list(source_key_list) if source_key_list is not None else source_keys()
    inc_map = includes or {}
    rows: list[dict] = []
    for k in keys:
        e = _BY_KEY.get(k)
        inc = inc_map.get(k, {}) if isinstance(inc_map.get(k, {}), dict) else {}
        if e is None:
            # 未知 key：如实标 unknown（不臆造 name/as_of）
            rows.append({"key": k, "name": k, "as_of": None, "lag_days": None,
                         "status": "unknown", "is_fallback": None, "source_chain": None})
            continue
        s = fr["sources"].get(e["name"], {}) or {}
        rows.append({
            "key": k,
            "name": e["name"],
            "as_of": s.get("as_of"),
            "lag_days": s.get("lag_days"),
            "status": s.get("status", "unknown"),
            "is_fallback": inc.get("is_fallback"),
            "source_chain": inc.get("source_chain"),
        })
    return rows


def summary(rows: list[dict]) -> dict:
    """底账汇总（供徽标一键呈现）：最差状态 + 是否含回退/陈旧源。

    :return: `{status, worst_keys, has_fallback, has_stale, n, n_unknown}`
    """
    _rank = {"ok": 0, "unknown": -1, "warn": 1, "stale": 2}
    rows = rows or []
    worst = "ok"
    known = False
    for r in rows:
        st = r.get("status", "unknown")
        if st != "unknown":
            known = True
        if _rank.get(st, -1) > _rank.get(worst, 0):
            worst = st
    worst_keys = [r["key"] for r in rows if r.get("status") == worst and worst in ("warn", "stale")]
    return {
        "status": worst if known else "unknown",
        "worst_keys": worst_keys,
        "has_fallback": any(r.get("is_fallback") is True for r in rows),
        "has_stale": any(r.get("status") == "stale" for r in rows),
        "n": len(rows),
        "n_unknown": sum(1 for r in rows if r.get("status") == "unknown"),
    }
