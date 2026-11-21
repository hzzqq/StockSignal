# -*- coding: utf-8 -*-
"""data_health 旁路缓存连接接进 PG17 方言层的契约测试。

锁死两条底线：
1. 默认 SQLite 下所有既有口径与改前完全一致（回归底线）。
2. SS_MARKET_CACHE_URL / DATABASE_URL=PG 时连接与 URL 由 backend.db_dialect
   单一真源决定，绝不静默回退本地 SQLite；cache_db_footprint 在 PG 下本地
   文件缺失时如实标 unknown（不谎报 missing / 0）。

全部离线、确定性；PG 用例只 monkeypatch open_connection 断言 URL，不真连 psycopg。
"""
from __future__ import annotations

import datetime as _dt
import sqlite3

import modules.data_health as DH

PG_URL = "postgresql://u:p@localhost:5432/stocksignal"


def _clean_env(monkeypatch):
    """隔离方言相关 env，保证每个用例从「默认 SQLite」基线出发。"""
    for k in ("SS_MARKET_CACHE_URL", "DATABASE_URL", "SS_DATA_DIR"):
        monkeypatch.delenv(k, raising=False)


# ── 1. SQLite 默认：既有口径一字不改 ─────────────────────────
def test_sqlite_default_sqlite_col_max_date_reads_content(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    db = tmp_path / "mc.db"
    with sqlite3.connect(str(db)) as c:
        c.execute("CREATE TABLE market_indicator_cache (key TEXT, date TEXT, value REAL)")
        c.executemany("INSERT INTO market_indicator_cache VALUES (?,?,?)",
                      [("a", "2026-09-30", 1.0), ("a", "2026-10-02", 2.0)])
    assert DH._sqlite_col_max_date(str(db), "market_indicator_cache", "date") == "2026-10-02"
    # bypass_env 缺省时「本地文件不存在 → None」的原行为不变
    assert DH._sqlite_col_max_date(str(tmp_path / "absent.db"), "t", "date") is None


def test_ensure_health_table_sqlite_ddl_unchanged(tmp_path, monkeypatch):
    """SQLite 下 _ensure_health_table 的建表 DDL 与改前逐字节一致。"""
    _clean_env(monkeypatch)
    db = tmp_path / "market_cache.db"
    monkeypatch.setattr(DH, "_health_db_path", lambda: str(db))
    DH._ensure_health_table()
    with sqlite3.connect(str(db)) as c:
        ddl = c.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (DH._HEALTH_TABLE,),
        ).fetchone()[0]
    assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in ddl
    assert "BIGSERIAL" not in ddl
    idx = sqlite3.connect(str(db)).execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (f"idx_{DH._HEALTH_TABLE}_key_obs",),
    ).fetchone()
    assert idx is not None


def test_record_health_observation_and_detect_stall_sqlite(tmp_path, monkeypatch):
    """record 返真实行数、detect_stall 读同一库的历史，口径与改前一致。"""
    _clean_env(monkeypatch)
    db = tmp_path / "market_cache.db"
    monkeypatch.setattr(DH, "_health_db_path", lambda: str(db))
    rows = [
        {"key": "market_temp", "as_of": "2026-11-20", "status": "ok", "lag_days": 1},
        {"key": "event_pool", "as_of": "2026-11-20", "status": "ok", "lag_days": 1},
    ]
    n = DH.record_health_observation(rows)
    assert n == 2
    with sqlite3.connect(str(db)) as c:
        cnt = c.execute(f"SELECT COUNT(*) FROM {DH._HEALTH_TABLE}").fetchone()[0]
    assert cnt == 2
    # 造一段「冻结」历史：30 天前首次观测，as_of 之后再未推进
    old = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
    with sqlite3.connect(str(db)) as c:
        c.execute(
            f"INSERT INTO {DH._HEALTH_TABLE}"
            "(source_key, observed_at, as_of, status, lag_days) VALUES (?,?,?,?,?)",
            ("frozen_src", f"{old} 09:00:00", old, "warn", 30),
        )
    stalls = DH.detect_stall("frozen_src")
    assert stalls["frozen_src"]["stalled"] is True
    assert stalls["frozen_src"]["last_as_of"] == old
    assert stalls["frozen_src"]["frozen_days"] >= DH.STALL_DAYS


# ── 2. SS_MARKET_CACHE_URL=sqlite:///<tmp> → 连接指向 tmp 而非默认路径 ──
def test_open_market_cache_respects_ss_market_cache_url(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    default_db = tmp_path / "default_market_cache.db"
    target_db = tmp_path / "target_market_cache.db"
    monkeypatch.setattr(DH, "_health_db_path", lambda: str(default_db))
    monkeypatch.setenv("SS_MARKET_CACHE_URL", f"sqlite:///{target_db}")

    conn = DH._open_market_cache()
    try:
        conn.execute("CREATE TABLE probe (x INTEGER)")
        conn.execute("INSERT INTO probe VALUES (1)")
        conn.commit()
    finally:
        conn.close()
    assert target_db.exists(), "连接必须落在 SS_MARKET_CACHE_URL 指定的 tmp 库"
    assert not default_db.exists(), "不得再连默认路径的本地库"


def test_sqlite_col_max_date_bypass_env_uses_bypass_url(tmp_path, monkeypatch):
    """bypass_env 给定时跳过 os.path.exists 前置，直接读 bypass URL 的内容。"""
    _clean_env(monkeypatch)
    absent = tmp_path / "absent.db"  # 故意不存在：PG/旁路场景下这是正常的
    bypass_db = tmp_path / "bypass.db"
    with sqlite3.connect(str(bypass_db)) as c:
        c.execute("CREATE TABLE t (date TEXT)")
        c.execute("INSERT INTO t VALUES ('2026-11-19')")
    monkeypatch.setenv("SS_TEST_BYPASS_URL", f"sqlite:///{bypass_db}")
    assert DH._sqlite_col_max_date(str(absent), "t", "date",
                                    bypass_env="SS_TEST_BYPASS_URL") == "2026-11-19"


def test_market_temp_registry_declares_bypass_env_and_source_as_of_passes_it(monkeypatch):
    e = next(e for e in DH.DATA_SOURCES if e["key"] == "market_temp")
    assert e["bypass_env"] == "SS_MARKET_CACHE_URL"
    seen = {}

    def fake(path, table, col="date", bypass_env=None):
        seen.update(path=path, table=table, col=col, bypass_env=bypass_env)
        return "2026-11-20"

    monkeypatch.setattr(DH, "_sqlite_col_max_date", fake)
    assert DH.source_as_of(e) == "2026-11-20"
    assert seen["bypass_env"] == "SS_MARKET_CACHE_URL"
    assert seen["table"] == "market_indicator_cache"


# ── 3. DATABASE_URL=PG 且无 SS_MARKET_CACHE_URL → 连接 URL 必须是 PG ──
def test_pg_deployment_open_connection_gets_pg_url(monkeypatch):
    """monkeypatch open_connection 断言收到 PG URL；绝不真连 psycopg。"""
    _clean_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    import backend.db_dialect as dbd

    captured = {}
    sentinel = object()

    def fake_open_connection(url):
        captured["url"] = url
        return sentinel

    monkeypatch.setattr(dbd, "open_connection", fake_open_connection)
    assert DH._open_market_cache() is sentinel
    assert captured["url"] == PG_URL


def test_pg_deployment_sqlite_col_max_date_gets_pg_url(monkeypatch):
    """bypass_env 分支同样把 PG URL 交给 open_connection，且本地文件不存在也不前置拦截。"""
    _clean_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    import backend.db_dialect as dbd

    captured = {}

    class _FakeResult:
        def fetchone(self):
            return ("2026-11-19",)

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql):
            captured["sql"] = sql
            return _FakeResult()

    def fake_open_connection(url):
        captured["url"] = url
        return _FakeConn()

    monkeypatch.setattr(dbd, "open_connection", fake_open_connection)
    got = DH._sqlite_col_max_date("/no/such/local.db", "market_indicator_cache", "date",
                                   bypass_env="SS_MARKET_CACHE_URL")
    assert got == "2026-11-19"
    assert captured["url"] == PG_URL
    assert "market_indicator_cache" in captured["sql"]


# ── 4. cache_db_footprint：PG 下本地文件缺失标 unknown，SQLite 口径不变 ──
def test_cache_db_footprint_pg_local_absent_is_unknown(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))  # 目录存在，但无 db 文件
    entries = DH.cache_db_footprint()
    assert entries and len(entries) == 2
    for e in entries:
        assert e["status"] == "unknown", e
        assert e["size_mb"] is None
        assert "同一 PG 实例" in e["note"] and "口径不适用" in e["note"]


def test_cache_db_footprint_sqlite_missing_unchanged(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    entries = DH.cache_db_footprint()
    for e in entries:
        assert e["status"] == "missing", "SQLite 下本地文件缺失仍标 missing（零回归）"
        assert e["size_mb"] is None
