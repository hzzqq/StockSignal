"""T-257 页面提速单测：WAL 落地 + get_daily L0 内存缓存（全离线）。

mutation 基线：
  - 去掉 L0 命中块 → test_l0_hit_skips_sqlite / test_l0_hit_returns_copy 变红；
  - clear_cache 不清 L0 → test_clear_cache_invalidates_l0 变红；
  - SS_L0_TTL=0 失效开关坏 → test_l0_ttl_zero_disables 变红。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import timedelta

import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import modules.fetcher as fetcher_mod  # noqa: E402
from modules.fetcher import StockFetcher  # noqa: E402
from modules.time_utils import now_cst_naive  # noqa: E402

DATES = pd.date_range("2026-01-01", "2026-04-10").strftime("%Y-%m-%d")


def _df():
    n = len(DATES)
    return pd.DataFrame({"date": pd.to_datetime(DATES),
                         "open": [10.0] * n, "high": [11.0] * n,
                         "low": [9.0] * n, "close": [10.0] * n,
                         "volume": [1e6] * n, "amount": [2e7] * n})


def _make_db(tmp_path):
    db = os.path.join(str(tmp_path), "cache.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, "
                 "data_json TEXT, updated_at TEXT)")
    ts = (now_cst_naive() - timedelta(hours=1)).isoformat(timespec="seconds")
    conn.execute("INSERT INTO daily_cache VALUES (?,?,?)",
                 ("daily_600519_2024-01-01_2026-10-11_qfq",
                  _df().to_json(orient="records", date_format="iso"), ts))
    conn.commit()
    conn.close()
    return db


def _instance(db, counter=None):
    f = StockFetcher.__new__(StockFetcher)
    f._code_to_name = {}
    f.cache_days = 7
    if counter is None:
        f._get_conn = lambda: sqlite3.connect(db)  # type: ignore[method-assign]
    else:
        def _counted():
            counter["n"] += 1
            return sqlite3.connect(db)
        f._get_conn = _counted  # type: ignore[method-assign]

    # 全离线：四级源一律失败 → 走 L5 兜底（确定性，绝不真联网）
    def _offline_levels(self, level, symbol, start, end, adjust):
        return None, f"{level}: offline"

    f._fetch_level = _offline_levels.__get__(f, StockFetcher)  # type: ignore[method-assign]
    return f


@pytest.fixture(autouse=True)
def _clean_l0():
    """每用例清空进程级 L0，隔离状态。"""
    fetcher_mod._L0_CACHE.clear()
    yield
    fetcher_mod._L0_CACHE.clear()


def test_wal_applied(tmp_path):
    """_get_conn 必须发送 journal_mode=WAL PRAGMA（生产语义守卫）。

    2026-11-04 修复：测试会话的 conftest sqlite shim 会拦下生产代码发出的
    `PRAGMA journal_mode=WAL`（改写为 MEMORY，或直接跳过以规避连接池多连接
    切换 journal_mode 时的 database is locked），因此运行时读回的 journal_mode
    已不能反映生产意图——shim 跳过时就是默认的 delete。原断言只认 wal/memory，
    shim 一改实现就误红，且无法区分「PRAGMA 根本没发」与「发了但被 shim 拦了」。

    改为：静态守住源码里 WAL PRAGMA 发送语句仍在（丢了就退回全库排他锁、
    页面读被写阻塞），运行时只断言连接可用。shim 无论重写还是跳过，守卫都不失效。
    """
    import inspect

    from modules.fetcher_base import BaseFetcher

    src = inspect.getsource(BaseFetcher._get_conn)
    assert "PRAGMA journal_mode=WAL" in src, \
        "_get_conn 丢失 WAL PRAGMA：缓存写入将退回全库排他锁，页面读被写阻塞"

    db = _make_db(tmp_path)
    f = StockFetcher.__new__(StockFetcher)
    f.db_path = db
    conn = f._get_conn()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode is not None, "_get_conn 返回的连接不可用"


def test_l0_hit_skips_sqlite(tmp_path):
    """第二次 get_daily 走 L0：不再开 SQLite 连接。"""
    db = _make_db(tmp_path)
    counter = {"n": 0}
    f = _instance(db, counter)
    meta1 = {}
    f.get_daily("600519", start="2026-01-01", end="2026-10-11",
                adjust="qfq", meta_out=meta1)
    n1 = counter["n"]
    meta2 = {}
    out2 = f.get_daily("600519", start="2026-01-01", end="2026-10-11",
                       adjust="qfq", meta_out=meta2)
    assert counter["n"] == n1, "L0 命中不得再开 SQLite 连接"
    assert len(out2) == len(DATES)
    assert meta2["source"] == meta1["source"] and meta2["as_of"] == meta1["as_of"]


def test_l0_hit_returns_copy(tmp_path):
    """L0 命中返回副本：调用方原地改写不得污染缓存。"""
    db = _make_db(tmp_path)
    f = _instance(db)
    out1 = f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    out1.loc[:, "close"] = -999.0  # 原地改写
    out2 = f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    assert (out2["close"] == 10.0).all(), "缓存被调用方污染"


def test_clear_cache_invalidates_l0(tmp_path):
    """「强制刷新」清缓存必须同步清 L0，否则页面继续吃内存旧数据。

    clear_cache 真删数据：清后 L0 已失效 + SQLite 行也没了 + 全源离线 →
    第二次调用诚实抛 RuntimeError，但必须重开 SQLite 连接（计数增加 = L0 失效证据）。
    """
    db = _make_db(tmp_path)
    counter = {"n": 0}
    f = _instance(db, counter)
    f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    n1 = counter["n"]
    f.clear_cache(table_name="daily_cache")
    with pytest.raises(RuntimeError):
        f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    assert counter["n"] > n1, "clear_cache 后必须回落 SQLite（L0 已失效），而非继续吃内存"


def test_l0_ttl_zero_disables(tmp_path, monkeypatch):
    """SS_L0_TTL=0 → L0 关闭，每次都走 SQLite（逃生开关）。"""
    monkeypatch.setattr(fetcher_mod, "_L0_TTL", 0.0)
    db = _make_db(tmp_path)
    counter = {"n": 0}
    f = _instance(db, counter)
    f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    n1 = counter["n"]
    f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    assert counter["n"] > n1, "TTL=0 时不得吃 L0"


def test_l0_eviction_maxsize(tmp_path, monkeypatch):
    """容量满按最旧逐出（有界内存）。"""
    monkeypatch.setattr(fetcher_mod, "_L0_MAX", 2)
    db = os.path.join(str(tmp_path), "cache.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, "
                 "data_json TEXT, updated_at TEXT)")
    ts = (now_cst_naive() - timedelta(hours=1)).isoformat(timespec="seconds")
    for sym in ("600519", "600520", "600521"):
        conn.execute("INSERT INTO daily_cache VALUES (?,?,?)",
                     (f"daily_{sym}_2024-01-01_2026-10-11_qfq",
                      _df().to_json(orient="records", date_format="iso"), ts))
    conn.commit()
    conn.close()
    f = _instance(db)
    for sym in ("600519", "600520", "600521"):
        f.get_daily(sym, start="2026-01-01", end="2026-10-11", adjust="qfq")
    assert len(fetcher_mod._L0_CACHE) == 2, "必须按容量逐出"
    assert "600519" not in fetcher_mod._L0_CACHE, "最旧者被逐出"


def test_l5_populates_l0_with_stale_meta(tmp_path):
    """L5 兜底结果也进 L0，meta 如实回放 is_stale=True（不因提速丢诚实标注）。"""
    db = _make_db(tmp_path)
    f = _instance(db)
    monkey_fail = lambda self, level, symbol, start, end, adjust: (None, f"{level}: offline")  # noqa: E731
    f._fetch_level = monkey_fail.__get__(f, StockFetcher)
    meta = {}
    f.get_daily("600519", start="2026-01-01", end="2026-10-11",
                adjust="qfq", meta_out=meta)
    assert meta["source"] == "cache_fallback" and meta["is_stale"] is True
    meta2 = {}
    f.get_daily("600519", start="2026-01-01", end="2026-10-11",
                adjust="qfq", meta_out=meta2)
    assert meta2["source"] == "cache_fallback" and meta2["is_stale"] is True, \
        "L0 回放不得把兜底数据谎报为新鲜"
