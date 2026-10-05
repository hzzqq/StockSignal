"""modules/display_provenance.py — 独立「展示源」溯源通道（H1+ 方向 A 续，T-215）。

定位：`modules/data_provenance`（决策源底账）只覆盖 `data_health.DATA_SOURCES` 的**决策源**；
而行情看板 / 个股研究等页依赖**展示源**（实时行情 / 指数 / 日线缓存）——它们的 `as_of`
证据在 `data/cache.db`，但**不属于决策健康**：纳入 decision 注册表会污染「决策健康判定」
（CI 门禁被展示缓存新旧左右），且注册表契约要求「每源有可执行刷新命令」而行情缓存由运行时
按需写入、无独立入口。故本模块为这类展示源**另立解耦通道**。

设计铁律（承 AC-A1/A2 精神）：
- **单一评分真理源**：新鲜度/滞后一律调 `modules.decision.assess_freshness`（与 `data_health`
  同源同阈值），本模块**零阈值常量**（防第二套口径漂移）。
- **诚实语义**：抽不到内容日期 → `as_of=None/status="unknown"`，如实标注、绝不臆造。
  **刻意不用 mtime 兜底**——展示源共享 `data/cache.db`（多写者），mtime 恒被无关写入刷新＝假新鲜。
  **无离线证据的源（实时强势榜 / 个股财务）不登记**（宁缺毋滥）。
- **零破坏**：未知/未登记的页面 `sources_for()` 返回 `[]`，调用方据此 no-op。
- **只读**：不触网、不写盘。
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3

from modules.decision import assess_freshness

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_CACHE_DB = os.path.join(_PROJECT_ROOT, "data", "cache.db")

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sqlite_json_max_date(db_path: str, table: str, *, field: str = None,
                          col: str = "date", prefix: str = None) -> str | None:
    """从 SQLite 表 ``data_json`` 内容里取最大日期；取不到返回 None（诚实 unknown）。

    - ``field`` 指定 → ``data_json`` 为对象，取其 ``field``（如 rt_quote_cache 的 ``datetime``）。
    - 否则 → ``data_json`` 为记录数组，取每条的 ``col``（如 index_cache/daily_cache 的 ``date``）。
    - ``prefix`` 限定 ``cache_key`` 前缀。表名做标识符白名单校验（非法不拼 SQL）。

    **不做 mtime 兜底**：展示源共享 cache.db，其 mtime 被无关写入刷新，不代表数据日期。
    """
    if not _IDENT.match(table or "") or not os.path.exists(db_path):
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            if prefix:
                rows = conn.execute(
                    f"SELECT data_json FROM {table} WHERE cache_key LIKE ?",
                    (f"{prefix}%",),
                ).fetchall()
            else:
                rows = conn.execute(f"SELECT data_json FROM {table}").fetchall()
        dates: list[str] = []
        for (dj,) in rows:
            try:
                obj = json.loads(dj)
            except Exception:  # noqa: BLE001
                continue
            if field:
                if isinstance(obj, dict) and obj.get(field):
                    dates.append(str(obj[field])[:10])
            elif isinstance(obj, list):
                for it in obj:
                    if isinstance(it, dict) and it.get(col):
                        dates.append(str(it[col])[:10])
        if dates:
            return max(dates)
    except Exception as e:  # noqa: BLE001
        logger.debug("[display_provenance] 读取 %s 失败: %s", table, e)
    return None


# ── 展示源注册表（仅登记**有离线 as_of 证据**者；无证据者一律不登记）────────────
DISPLAY_SOURCES: list[dict] = [
    {"key": "index_quote", "name": "指数行情缓存", "table": "index_cache",
     "col": "date", "prefix": "index_"},
    {"key": "realtime_quote", "name": "实时行情缓存", "table": "rt_quote_cache",
     "field": "datetime", "prefix": "rt_quote_"},
    {"key": "daily_kline", "name": "个股日线缓存", "table": "daily_cache",
     "col": "date", "prefix": "daily_"},
    # 注：实时强势榜（spot_rank 三层）/ 个股财务（akshare 新浪三表）**零落盘缓存**，
    # 无任何离线 as_of——**刻意不登记**（登记只能标 unknown，无价值；硬造 mtime＝误导）。
]

# 页面 slug → 依赖展示源（仅登记**有证据**的展示源；未登记页 → no-op）
DISPLAY_PAGE_SOURCES: dict[str, list[str]] = {
    "10_行情看板": ["index_quote", "realtime_quote"],
    "24_个股研究": ["daily_kline", "realtime_quote"],
    "14_智能盯盘": ["realtime_quote"],
}

_BY_KEY: dict[str, dict] = {e["key"]: e for e in DISPLAY_SOURCES}


def source_keys() -> list[str]:
    """全部已登记展示源 key（顺序同 DISPLAY_SOURCES）。"""
    return list(_BY_KEY)


def sources_for(slug: str) -> list[str]:
    """页面 slug → 依赖展示源 key 列表；未登记返回 ``[]``（调用方 no-op）。"""
    return list(DISPLAY_PAGE_SOURCES.get(slug, []))


def _as_of(entry: dict) -> str | None:
    """按注册表条目抽取展示源的真实数据截止日（内容优先，退回 mtime）。"""
    return _sqlite_json_max_date(
        _CACHE_DB, entry.get("table", ""),
        field=entry.get("field"), col=entry.get("col", "date"),
        prefix=entry.get("prefix"),
    )


def build_display_provenance(source_key_list: list[str] | None = None) -> list[dict]:
    """构造展示源底账（逐源一行），形状同 `data_provenance.build_provenance`。

    :param source_key_list: 要查询的源 key 列表；None = 全部已登记展示源。
    :return: `[{key, name, as_of, lag_days, status, is_fallback, source_chain}]`

    新鲜度**唯一取自** `modules.decision.assess_freshness`（与 data_health 同源同阈值）——
    本函数不做任何阈值判定，仅做取值与字段组装。
    """
    keys = list(source_key_list) if source_key_list is not None else source_keys()
    as_ofs = {e["name"]: _as_of(e) for e in DISPLAY_SOURCES}  # 一次性抽数（按需取用）
    fr = assess_freshness(as_ofs)
    rows: list[dict] = []
    for k in keys:
        e = _BY_KEY.get(k)
        if e is None:
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
            "is_fallback": None,   # 展示源不臆造回退链（除非调用方确知并另传）
            "source_chain": None,
        })
    return rows
