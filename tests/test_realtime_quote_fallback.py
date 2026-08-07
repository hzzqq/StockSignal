"""实时行情「过期缓存兜底」契约测试（任务 #81）。

验证：当新浪实时行情数据源全部不可用（网络失败）时，`get_realtime_quote`
应回退到本地 SQLite 的「过期缓存」旧值，而不是返回 None（避免行情卡白）。
不依赖真实网络——用 stub 强制 urlopen 失败 + 预置过期缓存行。
"""
import datetime
import json
import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def isolated_fetcher(monkeypatch):
    """构造一个指向临时 cache.db 的 StockFetcher，预置一笔 2 天前的实时行情。"""
    import urllib.request as _urllib_req
    import socket as _sock

    from modules.fetcher import StockFetcher

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "cache.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rt_quote_cache "
        "(cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)"
    )
    stale = {
        "ticker": "000021", "name": "深科技", "open": 10.0, "prev_close": 9.9,
        "current": 11.2, "high": 11.5, "low": 9.8, "volume": 1000, "amount": 11000,
        "bid": [], "ask": [], "datetime": "2026-08-05 15:00:00",
    }
    conn.execute(
        "INSERT OR REPLACE INTO rt_quote_cache VALUES (?,?,?)",
        ("rt_quote_000021", json.dumps(stale, ensure_ascii=False),
         (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat()),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(StockFetcher, "_get_conn", lambda self: sqlite3.connect(db))
    # 强制网络失败，逼出降级
    monkeypatch.setattr(_urllib_req, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(_sock, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))

    f = StockFetcher()
    f._test_db = db  # 供测试直接读写同一临时库
    return f


def test_realtime_quote_falls_back_to_stale_cache(isolated_fetcher):
    """数据源全挂时，实时行情必须回退过期缓存（current=11.2），不得返回 None。"""
    q = isolated_fetcher.get_realtime_quote("000021")
    assert q is not None, "实时行情在数据源失败时未回退过期缓存"
    assert q.get("current") == 11.2, f"回退值异常: {q}"
    assert q.get("ticker") == "000021"


def test_realtime_quote_fresh_cache_hit(isolated_fetcher):
    """存在新鲜缓存（10 秒内）时直接命中，不触网。"""
    import sqlite3

    conn = sqlite3.connect(isolated_fetcher._test_db)
    fresh = {
        "ticker": "600519", "name": "贵州茅台", "open": 1700.0, "prev_close": 1690.0,
        "current": 1720.0, "high": 1730.0, "low": 1680.0, "volume": 500, "amount": 900000,
        "bid": [], "ask": [], "datetime": "2026-08-07 09:35:00",
    }
    conn.execute(
        "INSERT OR REPLACE INTO rt_quote_cache VALUES (?,?,?)",
        ("rt_quote_600519", json.dumps(fresh, ensure_ascii=False),
         datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    q = isolated_fetcher.get_realtime_quote("600519")
    assert q is not None
    assert q.get("current") == 1720.0


def test_realtime_quote_no_cache_returns_none(isolated_fetcher):
    """既无新鲜缓存、无过期缓存、又网络失败 → 明确返回 None（不崩）。"""
    q = isolated_fetcher.get_realtime_quote("999999")  # 无任何缓存
    assert q is None
