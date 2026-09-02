# -*- coding: utf-8 -*-
"""tests/test_sqlite_memory_journal.py — 治本方案验证：测试库不生成 WAL 兄弟文件。

对应咨询文档《StockSignal 回收站洪流「治本」方案》：
conftest._install_sqlite_memory_journal 在测试会话把 `PRAGMA journal_mode=WAL`
改写为 `PRAGMA journal_mode=MEMORY`，覆盖 raw sqlite3（market_cache / news / fetcher）
与 SQLAlchemy 文件库（backend）。本文件断言四处连接都不产生 -wal / -shm 兄弟文件，
即回收站刷屏源头被消除。

运行：pytest tests/test_sqlite_memory_journal.py -q（离线）
"""

from __future__ import annotations

import sqlite3


def test_conftest_patch_active_direct_wal_rewritten(tmp_path):
    """conftest 注入生效：直接走 sqlite3.connect + WAL PRAGMA 不产生兄弟文件。"""
    db = tmp_path / "verify.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")  # 应被 conftest 改写为 MEMORY
    conn.execute("CREATE TABLE t(x)")
    conn.execute("INSERT INTO t VALUES(1)")
    conn.commit()
    conn.close()
    assert not (tmp_path / "verify.db-wal").exists(), "WAL 兄弟文件未被消除"
    assert not (tmp_path / "verify.db-shm").exists(), "SHM 兄弟文件未被消除"


def test_market_cache_no_wal_siblings(tmp_path, monkeypatch):
    """market_cache._get_conn 显式 WAL → 改写后无 -wal/-shm。"""
    import modules.market_cache as mc
    db = tmp_path / "market_cache.db"
    monkeypatch.setattr(mc, "_DB_PATH", str(db))
    monkeypatch.setattr(mc, "_DATA_DIR", str(tmp_path))
    conn = mc._get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS t(x)")
    conn.execute("INSERT INTO t VALUES(1)")
    conn.commit()
    conn.close()
    assert not (tmp_path / "market_cache.db-wal").exists()
    assert not (tmp_path / "market_cache.db-shm").exists()


def test_news_no_wal_siblings(tmp_path, monkeypatch):
    """news.NewsDatabase._get_conn 显式 WAL → 改写后无 -wal/-shm。"""
    from modules.news import NewsDatabase
    sn = NewsDatabase(db_path=str(tmp_path / "news.db"))
    conn = sn._get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS t(x)")
    conn.commit()
    conn.close()
    assert not (tmp_path / "news.db-wal").exists()
    assert not (tmp_path / "news.db-shm").exists()


def test_backend_file_db_no_wal_siblings(tmp_path):
    """backend SQLAlchemy 文件库（走 WAL connect 事件）→ 改写后无 -wal/-shm。"""
    from sqlalchemy import text

    from backend.app import create_app, db
    from backend.config import Config

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'b.db'}"
        TESTING = True
        RATE_LIMIT_ENABLED = False

    app = create_app(_TestConfig)
    with app.app_context():
        db.create_all()
        db.session.execute(text("CREATE TABLE IF NOT EXISTS z(x)"))
        db.session.commit()
    assert not (tmp_path / "b.db-wal").exists(), "backend 文件库 WAL 兄弟文件未被消除"
    assert not (tmp_path / "b.db-shm").exists()
