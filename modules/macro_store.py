# -*- coding: utf-8 -*-
"""宏观指标历史存储（macro_history 表）。

背景（2026-11-08 勘察取证）：
- 改库前 `modules/macro_data.py` 的 22 个宏观指标**完全不落盘**：每次
  `fetch_indicator()` 都是裸调 akshare 现取现用。
- 后果一（慢）：`pages/84_宏观数据.py` 遍历注册表逐个取，单页首屏实测
  3~8 秒（单指标 159ms~2.2s，`bond_zh_us_rate` 最慢 2.2s）。
- 后果二（不可复现）：`modules/event_factor.py:683` 的 `global_regime_score()`
  直接实时调网络 → 事件因子的宏观分**今天和上个月跑的不一样**，历史回测
  无法归因；`data/daily_snapshot.json` 的 indicators/scenario/event_factor
  三块里宏观相关 key 数量为 0 → 宏观分根本没进快照，无留痕。

本模块提供宏观序列的持久化，使宏观分可回放、可复现。

诚实红线：
- 取不到 / 缺失一律写 NULL 或不写行，**绝不补 0、绝不用 now() 当数据日期**。
- `date` 一律是**数据内容日期**（序列末项的日期），不是抓取时间。
- 抓取时间单独存 `fetched_at`，两者语义严格分离。
- TTL 判定按指标自身频率（日/周/月/年），不硬编码统一天数。

表结构（SQLite 与后续 PostgreSQL 通用方言）：
    macro_history(key TEXT, date TEXT, value REAL, prev REAL,
                  source TEXT, fetched_at TEXT,
                  PRIMARY KEY(key, date))
    idx_macro_history_key_date ON macro_history(key, date)
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── 表结构与连接 ────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_history (
    key        TEXT NOT NULL,
    date       TEXT NOT NULL,
    value      REAL,
    prev       REAL,
    source     TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (key, date)
);
CREATE INDEX IF NOT EXISTS idx_macro_history_key_date
    ON macro_history(key, date);
"""


def _db_path() -> str:
    """宏观历史库路径（与主库同目录，独立文件，便于单独备份/清理）。

    默认 `<repo>/data/macro_history.db`；可用环境变量 `MACRO_DB_PATH` 覆盖
    （测试用探针库隔离，避免与运行中的服务抢锁）。
    """
    override = os.environ.get("MACRO_DB_PATH")
    if override:
        return override
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo, "data", "macro_history.db")


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    return conn


def init_macro_db() -> None:
    """建表（幂等）。启动时调用一次。"""
    conn = _get_conn()
    try:
        conn.commit()
    finally:
        conn.close()


# ── 频率 → TTL（依据指标自身发布节奏，不硬编码统一天数）────────────────────

# 日频：收盘后当日线失效 → 保留 1 天（跨日即重取）
TTL_DAILY = timedelta(days=1)
# 周频：周度数据 → 保留 7 天
TTL_WEEKLY = timedelta(days=7)
# 月频：月度数据（PMI/CPI/M2/GDP）→ 保留 45 天（覆盖跨月发布间隔）
TTL_MONTHLY = timedelta(days=45)
# 年频/季度频：保守保留 120 天
TTL_QUARTERLY = timedelta(days=120)

# 指标频率登记表（key → TTL）。未登记的指标默认按日频（最保守，最常刷新）。
FREQUENCY_TTL: dict[str, timedelta] = {
    # 日频：汇率 / 指数 / 美债收益率
    "usd_cny": TTL_DAILY,
    "usd_cnh": TTL_DAILY,
    "dxy": TTL_DAILY,
    "us_sp500": TTL_DAILY,
    "us_nasdaq": TTL_DAILY,
    "hsi": TTL_DAILY,
    "us_treasury_10y": TTL_DAILY,
    "us_treasury_2y": TTL_DAILY,
    "cn_treasury_10y": TTL_DAILY,
    # 日频（美官方日度发布）：非农 / 失业率 / ISM / 零售
    "us_nonfarm": TTL_DAILY,
    "us_unemployment": TTL_DAILY,
    "us_ism_pmi": TTL_DAILY,
    # 月频：中国与美国的月度宏观
    "pmi": TTL_MONTHLY,
    "cpi": TTL_MONTHLY,
    "ppi": TTL_MONTHLY,
    "gdp": TTL_MONTHLY,
    "m2": TTL_MONTHLY,
    "lpr": TTL_MONTHLY,
    "us_cpi": TTL_MONTHLY,
    "us_ppi": TTL_MONTHLY,
    "us_gdp": TTL_MONTHLY,
    # 利率决议（不定期）
    "fed_funds_rate": TTL_QUARTERLY,
}


def ttl_for(key: str) -> timedelta:
    """指标 TTL（未登记 → 日频，最保守）。"""
    return FREQUENCY_TTL.get(key, TTL_DAILY)


def is_fresh(key: str, fetched_at: str) -> bool:
    """按指标频率判定缓存是否仍在 TTL 内。

    `fetched_at` 为 ISO 字符串。解析失败一律判**过期**（宁可重取，不吃坏数据）。
    """
    try:
        ts = datetime.fromisoformat(fetched_at)
    except (TypeError, ValueError):
        return False
    return (datetime.now() - ts) <= ttl_for(key)


# ── 写 ──────────────────────────────────────────────────────────────────────

def write_macro_point(key: str, date: str, value, prev=None, source: str = "") -> bool:
    """写入单条宏观观测。返回是否成功写入。

    `date` 必须是数据内容日期（ISO 或 'YYYY-MM-DD'）；取不到 → 返回 False
    （**不写行**，避免污染出无日期的脏数据）。
    """
    if not key or not date:
        return False
    d = str(date)[:10]
    v = _to_float(value)
    p = _to_float(prev)
    if v is None and p is None:
        # 值与前值都缺 → 无有效观测，不写
        return False
    fetched_at = datetime.now().isoformat()
    try:
        conn = _get_conn()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO macro_history"
                    "(key, date, value, prev, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, d, v, p, source or None, fetched_at),
                )
            return True
        finally:
            conn.close()
    except sqlite3.Error as e:  # noqa: BLE001 - 落盘失败不阻断取数主流程
        logger.warning(f"[macro_store] 写入宏观历史失败 key={key} date={d}: {e}")
        return False


def write_macro_series(key: str, points: list[dict], source: str = "") -> int:
    """批量写入宏观序列（回填用）。points 每项须含 date / value（prev 可选）。

    返回实际写入条数。**逐条独立提交**：单条坏数据不影响其余条目。
    """
    n = 0
    for pt in points or []:
        if not isinstance(pt, dict):
            continue
        d = pt.get("date")
        if not d:
            continue
        if write_macro_point(key, str(d), pt.get("value"), pt.get("prev"), source):
            n += 1
    return n


# ── 读 ──────────────────────────────────────────────────────────────────────

def read_macro_latest(key: str):
    """读某指标最新一条观测。

    返回 dict：`{key, date, value, prev, source, fetched_at}`；
    无数据返回 **None**（不返回空 dict 冒充成功）。
    """
    try:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT key, date, value, prev, source, fetched_at "
                "FROM macro_history WHERE key = ? ORDER BY date DESC LIMIT 1",
                (key,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:  # noqa: BLE001
        logger.warning(f"[macro_store] 读宏观历史失败 key={key}: {e}")
        return None
    if row is None:
        return None
    return {
        "key": row["key"],
        "date": row["date"],
        "value": row["value"],
        "prev": row["prev"],
        "source": row["source"],
        "fetched_at": row["fetched_at"],
    }


def read_macro_series(key: str, start: str | None = None, end: str | None = None) -> list[dict]:
    """读某指标历史序列（按 date 升序）。可选起止日期过滤（ISO 字符串比较）。"""
    sql = "SELECT key, date, value, prev, source, fetched_at FROM macro_history WHERE key = ?"
    params: list = [key]
    if start:
        sql += " AND date >= ?"
        params.append(str(start)[:10])
    if end:
        sql += " AND date <= ?"
        params.append(str(end)[:10])
    sql += " ORDER BY date ASC"
    try:
        conn = _get_conn()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:  # noqa: BLE001
        logger.warning(f"[macro_store] 读宏观序列失败 key={key}: {e}")
        return []
    return [
        {
            "key": r["key"],
            "date": r["date"],
            "value": r["value"],
            "prev": r["prev"],
            "source": r["source"],
            "fetched_at": r["fetched_at"],
        }
        for r in rows
    ]


def macro_store_stats() -> dict:
    """库内统计（供数据源健康页 / 运维展示）。"""
    try:
        conn = _get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM macro_history").fetchone()[0]
            keys = conn.execute(
                "SELECT key, COUNT(*) AS n, MAX(date) AS last_date, MAX(fetched_at) AS last_fetch "
                "FROM macro_history GROUP BY key ORDER BY key"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:  # noqa: BLE001
        logger.warning(f"[macro_store] 统计失败: {e}")
        return {"total": 0, "keys": []}
    return {
        "total": total,
        "keys": [
            {
                "key": r["key"],
                "count": r["n"],
                "last_date": r["last_date"],
                "last_fetch": r["last_fetch"],
            }
            for r in keys
        ],
    }


def _to_float(v):
    """宽松数值转换：None/NaN/非法 → None（绝不补 0）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f
