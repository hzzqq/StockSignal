"""
市场驱动力数据持久化缓存层

解决痛点：
  1. akshare 等 API 偶发不可用（网络/代理/DNS）→ 页面全白「暂无数据」
  2. 21 个指标取数耗时长（串行需 30-60s）→ 每次刷新都重取浪费时间
  3. 需要定时自动更新 → 不能依赖用户手动刷新

设计：
  - SQLite 存储在 data/market_cache.db，每个指标一张宽表（date + value）
  - 写入策略：get_market_drivers() 成功后，将结果 upsert 到本地表
  - 读取策略：market_drivers 先走网络；失败时降级到缓存（带时间戳警告）
  - 定时任务：通过 WorkBuddy automation 或后台线程每日收盘后自动刷新
  - 缓存表结构统一：(indicator_key TEXT PK, date TEXT PK, value REAL, updated_at TEXT)

使用方式：
  from modules.market_cache import (
      save_drivers_to_cache, load_drivers_from_cache,
      get_cache_status, refresh_all_indicators,
  )
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 缓存 DB 路径 ──────────────────────────────────────────────
# 跟随 SS_DATA_DIR 隔离（与 decision/shepherd_ladder 一致）；未设时回落到仓库 data/，
# 生产默认行为完全不变，仅测试会话（conftest 设 SS_DATA_DIR）自动隔离到临时目录。
_DATA_DIR = os.environ.get("SS_DATA_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data")
_DB_PATH = os.path.join(_DATA_DIR, "market_cache.db")

# 缓存有效期：宏观/估值类低频指标 24h，资金/情绪类高频指标 4h
_CACHE_TTL_HOURS = {
    # 高频（交易日每 4h 刷新一次够用）
    "adl": 4, "adr": 4, "nhnl": 4,
    "vix": 4, "pcr": 4, "zt_ratio": 4,
    "north_net": 4, "margin_net": 4, "margin_balance": 4,
    # 低频（日更即可）
    "pe_pct": 24, "div_yield": 24,
    # 宏观（月更/季更，缓存久一点）
    "m2_yoy": 72, "shr_zgm": 72, "yield_spread": 72, "pmi": 168,
    # 技术（本地计算，随指数数据刷新）
    "idx_ma5": 4, "idx_ma20": 4, "rsi": 4, "boll": 4, "bias": 4,
}
_DEFAULT_TTL = 6  # 默认 6 小时

# 全局锁：防止多线程并发写 DB
_DB_LOCK = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（线程安全，自动建表）。

    注意：PRAGMA 必须容错。若 _DB_PATH 指向的文件被损坏 / 不是合法 sqlite 文件，
    `PRAGMA journal_mode=WAL` 会立刻抛 sqlite3.DatabaseError。历史实现把它放在
    调用方 try 之外，导致「缓存文件损坏 → 整页崩溃」而非优雅降级。
    这里吞掉 PRAGMA 异常，让真正的读写在调用方的 try/except 内失败并正常降级。
    """
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    for pragma in ("PRAGMA journal_mode=WAL", "PRAGMA busy_timeout=5000"):
        try:
            conn.execute(pragma)
        except sqlite3.Error as e:
            logger.warning("[market_cache] %s 执行失败（DB 可能损坏）: %s", pragma, e)
            break
    return conn


def _ensure_table(conn: sqlite3.Connection):
    """确保缓存表存在（幂等）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_indicator_cache (
            key       TEXT NOT NULL,
            date      TEXT NOT NULL,
            value     REAL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (key, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_refresh_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            refreshed_at TEXT DEFAULT (datetime('now','localtime')),
            status     TEXT NOT NULL,
            available  TEXT DEFAULT '[]',
            unavailable TEXT DEFAULT '[]',
            duration_sec REAL,
            note       TEXT DEFAULT ''
        )
    """)
    # 索引加速按 key 查询
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_key ON market_indicator_cache(key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_date ON market_indicator_cache(date)")
    conn.commit()


# ── 写入 ───────────────────────────────────────────────────────

def save_drivers_to_cache(df: pd.DataFrame, meta: Optional[Dict] = None) -> int:
    """将 get_market_drivers() 的结果写入持久化缓存。

    Args:
        df: 市场驱动力宽表（含 date 列和各指标列）
        meta: 可选的 meta 字典（记录可用/不可用信息）

    Returns:
        成功写入的 (key, date) 行数。
    """
    if df is None or df.empty or "date" not in df.columns:
        logger.warning("[market_cache] save_drivers_to_cache: 空 df 或缺 date 列")
        return 0

    with _DB_LOCK:
        conn = None
        try:
            conn = _get_conn()
            _ensure_table(conn)
            count = 0
            # 逐列写入（跳过 date 和非指标列）
            for col in df.columns:
                if col in ("date", "ref"):
                    continue
                s = df[col].dropna()
                if s.empty:
                    continue
                rows = [
                    (col, str(pd.to_datetime(d).date())[:10], float(v))
                    for d, v in zip(df["date"].iloc[s.index], s.values)
                    if pd.notna(d) and pd.notna(v)
                ]
                if not rows:
                    continue
                conn.executemany(
                    "INSERT OR REPLACE INTO market_indicator_cache (key, date, value, updated_at) "
                    "VALUES (?, ?, ?, datetime('now','localtime'))",
                    rows,
                )
                count += len(rows)

            # 记录刷新日志
            avail = []
            unavail = []
            if meta:
                for dim, info in meta.items():
                    avail.extend(info.get("available", []))
                    unavail.extend(info.get("unavailable", []))
            conn.execute(
                "INSERT INTO market_refresh_log (status, available, unavailable, note) "
                "VALUES (?, ?, ?, ?)",
                ("OK", json.dumps(avail), json.dumps(unavail),
                 f"写入 {count} 行, {len(df.columns)-1} 个指标"),
            )
            conn.commit()
            logger.info("[market_cache] 缓存已更新：%d 行, %d 个指标", count, len(df.columns)-1)
            return count
        except Exception as e:
            logger.error("[market_cache] 写入缓存失败: %s", e)
            if conn is not None:
                try:
                    conn.rollback()
                except Exception as e:
                    logger.warning(f"[market_cache] 处理异常: {e}")
                    pass
            return 0
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"[market_cache] 处理异常: {e}")
                    pass


def save_single_series(key: str, series: pd.Series) -> int:
    """写入单条指标序列（供单独刷新某个指标用）。"""
    if series is None or series.empty:
        return 0
    s = series.dropna()
    if s.empty:
        return 0
    s.index = pd.to_datetime(s.index, errors="coerce")
    rows = [
        (key, str(d.date())[:10], float(v))
        for d, v in zip(s.index, s.values)
        if pd.notna(d) and pd.notna(v)
    ]
    if not rows:
        return 0
    with _DB_LOCK:
        conn = None
        try:
            conn = _get_conn()
            _ensure_table(conn)
            conn.executemany(
                "INSERT OR REPLACE INTO market_indicator_cache (key, date, value, updated_at) "
                "VALUES (?, ?, ?, datetime('now','localtime'))",
                rows,
            )
            conn.commit()
            return len(rows)
        except Exception as e:
            logger.error("[market_cache] save_single '%s' 失败: %s", key, e)
            if conn is not None:
                try:
                    conn.rollback()
                except Exception as e:
                    logger.warning(f"[market_cache] 处理异常: {e}")
                    pass
            return 0
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"[market_cache] 处理异常: {e}")
                    pass


# ── 读取 ───────────────────────────────────────────────────────

def load_drivers_from_cache(days: int = 180) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    """从缓存加载市场驱动力数据。

    Returns:
        (df, meta) —— 与 get_market_drivers() 相同签名。
        df 为空或 None 表示无缓存数据。
        meta 含缓存时间戳信息供 UI 展示。
    """
    with _DB_LOCK:
        conn = None
        try:
            conn = _get_conn()
            _ensure_table(conn)
            # 查询最近 days 天的所有指标
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            df_raw = pd.read_sql_query(
                "SELECT key, date, value, updated_at FROM market_indicator_cache "
                "WHERE date >= ? ORDER BY key, date",
                conn, params=(cutoff,),
            )
            conn.close()
        except Exception as e:
            logger.error("[market_cache] 读取缓存失败: %s", e)
            if conn is not None:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"[market_cache] 处理异常: {e}")
                    pass
            return None, {"cache_status": "error", "message": f"缓存不可读: {e}"}

    if df_raw.empty:
        return None, {"cache_status": "empty", "message": "无缓存数据"}

    # pivot → 宽表
    try:
        df_pivot = df_raw.pivot(index="date", columns="key", values="value")
        df_pivot = df_pivot.reset_index().rename(columns={"index": "date"})
        df_pivot["date"] = pd.to_datetime(df_pivot["date"])
        df_pivot = df_pivot.sort_values("date").reset_index(drop=True)
    except Exception as e:
        logger.error("[market_cache] pivot 失败: %s", e)
        return None, {"cache_status": "error", "message": f"缓存格式异常: {e}"}

    # 构造 meta（含各指标的缓存新鲜度）
    meta = {"cache_status": "ok", "cached_keys": [], "stale_keys": []}
    now = datetime.now()
    for col in df_pivot.columns:
        if col == "date":
            continue
        last_update = df_raw[df_raw["key"] == col]["updated_at"].max()
        ttl_h = _CACHE_TTL_HOURS.get(col, _DEFAULT_TTL)
        try:
            dt = datetime.strptime(last_update[:19], "%Y-%m-%d %H:%M:%S") if last_update else now
            age_h = (now - dt).total_seconds() / 3600
        except Exception as e:
            logger.warning(f"[market_cache] 处理异常: {e}")
            age_h = 0
        if age_h > ttl_h:
            meta["stale_keys"].append((col, f"缓存 {age_h:.0f}h 前 (TTL={ttl_h}h)"))
        else:
            meta["cached_keys"].append(col)

    return df_pivot, meta


def get_cache_status() -> Dict[str, Any]:
    """返回缓存状态摘要（供调试 / 状态页展示）。"""
    with _DB_LOCK:
        conn = None
        try:
            conn = _get_conn()
            _ensure_table(conn)
            # 各指标最新日期 & 记录数
            summary = pd.read_sql_query(
                "SELECT key, COUNT(*) as cnt, MAX(date) as latest_date, "
                "MAX(updated_at) as last_update "
                "FROM market_indicator_cache GROUP BY key ORDER BY key",
                conn,
            )
            # 最近刷新日志
            log = pd.read_sql_query(
                "SELECT * FROM market_refresh_log ORDER BY id DESC LIMIT 5",
                conn,
            )
            total_rows = conn.execute(
                "SELECT COUNT(*) FROM market_indicator_cache"
            ).fetchone()[0]
            conn.close()
            return {
                "total_rows": total_rows,
                "indicators": summary.to_dict(orient="records"),
                "recent_logs": log.to_dict(orient="records"),
                "db_path": _DB_PATH,
                "db_size_mb": round(os.path.getsize(_DB_PATH) / 1048576, 2) if os.path.exists(_DB_PATH) else 0,
            }
        except Exception as e:
            logger.warning(f"[market_cache] 处理异常: {e}")
            if conn is not None:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"[market_cache] 处理异常: {e}")
                    pass
            return {"error": str(e), "db_path": _DB_PATH}


# ── 刷新调度 ───────────────────────────────────────────────────

def refresh_all_indicators(force: bool = False) -> Dict[str, Any]:
    """刷新全部指标并写入缓存。

    这是定时任务的核心入口：
    1. 调用 get_market_drivers() 取最新数据
    2. 将结果写入 SQLite 缓存
    3. 返回刷新报告

    Args:
        force: 是否强制刷新（忽略 TTL）

    Returns:
        刷新报告 dict。
    """
    t0 = time.time()
    try:
        from modules.market_drivers import get_market_drivers
        df, meta = get_market_drivers(days=365)  # 缓存多存一点历史
    except Exception as e:
        logger.error("[market_cache] refresh get_market_drivers 失败: %s", e)
        return {
            "status": "fetch_failed",
            "error": str(e),
            "duration_sec": round(time.time() - t0, 1),
        }

    if df is None or df.empty:
        return {
            "status": "empty_data",
            "meta": meta,
            "duration_sec": round(time.time() - t0, 1),
        }

    n_saved = save_drivers_to_cache(df, meta)
    return {
        "status": "ok",
        "rows_cached": n_saved,
        "indicators": len([c for c in df.columns if c != "date"]),
        "date_range": f"{df['date'].min()} ~ {df['date'].max()}" if "date" in df.columns else "?",
        "duration_sec": round(time.time() - t0, 1),
        "meta": meta,
    }


def clear_stale_cache(days: int = 90) -> int:
    """清理超过 N 天的旧缓存数据，释放空间。"""
    with _DB_LOCK:
        conn = None
        try:
            conn = _get_conn()
            _ensure_table(conn)
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            cur = conn.execute(
                "DELETE FROM market_indicator_cache WHERE date < ?", (cutoff,)
            )
            deleted = cur.rowcount
            conn.execute("VACUUM")
            conn.commit()
            conn.close()
            logger.info("[market_cache] 清理了 %d 条超过 %d 天的旧数据", deleted, days)
            return deleted
        except Exception as e:
            logger.error("[market_cache] 清理失败: %s", e)
            if conn is not None:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"[market_cache] 处理异常: {e}")
                    pass
            return 0


# ── 降级读取器（给 market_drivers.py 用） ──────────────────────

class CacheFallbackReader:
    """包装 get_market_drivers()，在网络失败时自动降级到缓存。

    用法：
        reader = CacheFallbackReader()
        df, meta = reader.get(days=180)   # 优先网络，失败走缓存
    """

    def __init__(self, prefer_cache: bool = False):
        self.prefer_cache = prefer_cache

    def get(self, days: int = 180) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        """获取市场驱动力数据（网络优先，缓存兜底）。"""
        from modules.market_drivers import get_market_drivers

        # 尝试网络源
        if not self.prefer_cache:
            try:
                df, meta = get_market_drivers(days=days)
                if df is not None and not df.empty:
                    # 网络成功 → 更新缓存（异步不阻塞返回）
                    try:
                        save_drivers_to_cache(df, meta)
                    except Exception as e:
                        logger.debug("[market_cache] 后台写缓存失败（不影响返回）: %s", e)
                    return df, meta
            except Exception as e:
                logger.info("[market_cache] 网络取数失败，降级到缓存: %s", str(e)[:100])

        # 降级到缓存
        cached_df, cached_meta = load_drivers_from_cache(days=days)
        if cached_df is not None and not cached_df.empty:
            # 注入缓存标记到 meta
            if cached_meta is None:
                cached_meta = {}
            cached_meta["_from_cache"] = True
            cached_meta["_cache_message"] = "当前展示为最近一次成功缓存的数据（网络暂时不可用）"
            return cached_df, cached_meta

        # 双双失败
        return None, {"_from_cache": False, "_cache_message": "无可用数据（网络+缓存均失败）"}
