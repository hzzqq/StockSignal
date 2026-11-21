# -*- coding: utf-8 -*-
"""T-248 旁路库方言接线守卫：消除「数据写 PG、清理却盯着本地 SQLite 文件」割裂。

锁死不变量：
1. 无 bypass_env 时 prune_sqlite_cache / prune_daily_cache_duplicates 的字段口径
   与改前完全一致（含 VACUUM 照常执行、不多加 vacuum 字段）；
2. 设 SS_CACHE_DB_URL=sqlite:///<tmp> 时清理作用于 tmp 库而非默认路径；
3. PG 场景（DATABASE_URL 为 PG 且无对应 env）：连接走 resolve_bypass_url 解析出的
   PG URL、不执行本地 exists 前置、不执行 VACUUM、如实标注
   vacuum=skipped_pg_autovacuum 且 freed_bytes=0；PG 的 "does not exist" 文案
   与 SQLite 的 "no such table" 同等视为「该表从未写入」。
4. 全程不真连 psycopg（沙箱未装），open_connection 被 monkeypatch 捕获。
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backend.db_dialect as bd  # noqa: E402
import modules.cache_maintenance as cm  # noqa: E402


# ── 通用桩 ────────────────────────────────────────────────────────────

class _ConnProxy:
    """记录 SQL 的 sqlite3 连接代理（C 类型连接不可 setattr，故用代理包装）。"""

    def __init__(self, conn, seen):
        self._conn, self._seen = conn, seen

    def execute(self, sql, params=()):
        self._seen.append(sql)
        return self._conn.execute(sql, params)

    def executemany(self, sql, seq):
        self._seen.append(sql)
        return self._conn.executemany(sql, seq)

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()


def _make_cache_db(path, old_rows=5, new_rows=3, date_col="updated_at", blob=200):
    """造 cache.db 风格 daily_cache：old_rows 行早于 cutoff、new_rows 行晚于 cutoff。"""
    conn = sqlite3.connect(str(path))
    conn.execute(
        f"CREATE TABLE daily_cache "
        f"(cache_key TEXT PRIMARY KEY, data_json TEXT, {date_col} TEXT)"
    )
    old_date = "2000-01-01" if date_col == "date" else "2000-01-01T00:00:00"
    new_date = "2099-01-01" if date_col == "date" else "2099-01-01T00:00:00"
    payload = "x" * blob
    for i in range(old_rows):
        conn.execute("INSERT OR REPLACE INTO daily_cache VALUES (?,?,?)",
                     (f"old_{i}", payload, old_date))
    for i in range(new_rows):
        conn.execute("INSERT OR REPLACE INTO daily_cache VALUES (?,?,?)",
                     (f"new_{i}", payload, new_date))
    conn.commit()
    conn.close()


def _make_dup_db(path, symbols=1, windows=5, blob=300):
    """造 R-08 风格 daily_cache：每个 symbol 有 windows 份不同窗口 key。"""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)"
    )
    for s in range(symbols):
        sym = f"6000{s:02d}"
        for w in range(windows):
            key = f"daily_{sym}_2026-01-{w + 1:02d}_2026-10-{w + 1:02d}_qfq"
            conn.execute("INSERT OR REPLACE INTO daily_cache VALUES (?,?,?)",
                         (key, "y" * blob, f"2026-10-{w + 1:02d}T00:00:00"))
    conn.commit()
    conn.close()


class _FakeCursor:
    rowcount = 2


class _FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _pg_capture(monkeypatch, *, rows=None, raise_sql=None):
    """安装 PG 桩：捕获 open_connection 调用与全部 SQL；返回记录 dict。"""
    calls = {"url": None, "sql": [], "executemany": [], "closed": False}

    class _FakeConn:
        def execute(self, sql, params=()):
            calls["sql"].append(sql)
            if raise_sql and raise_sql in sql.upper():
                raise RuntimeError('relation "daily_cache" does not exist')
            if sql.lstrip().upper().startswith("SELECT"):
                return _FakeRows(rows or [])
            return _FakeCursor()

        def executemany(self, sql, seq):
            calls["sql"].append(sql)
            calls["executemany"].extend(seq)

        def commit(self):
            calls["sql"].append("COMMIT")

        def close(self):
            calls["closed"] = True

    def fake_open(url):
        calls["url"] = url
        return _FakeConn()

    monkeypatch.setattr(bd, "open_connection", fake_open)
    return calls


# ── 1. SQLite 默认：字段口径与改前一致 + VACUUM 照常 ──────────────────

def test_sqlite_default_prune_fields_and_vacuum(tmp_path, monkeypatch):
    db = tmp_path / "cache.db"
    _make_cache_db(db, old_rows=40, new_rows=3)
    seen = []
    real = sqlite3.connect
    monkeypatch.setattr(cm.sqlite3, "connect",
                        lambda *a, **k: _ConnProxy(real(*a, **k), seen))

    res = cm.prune_sqlite_cache(db, ["daily_cache"], days=90)

    assert res["error"] is None
    assert res["deleted"] == 40
    assert res["freed_bytes"] >= 0          # 口径：实测前后体积差
    assert "vacuum" not in res              # SQLite 分支不多加字段
    assert sorted(res) == sorted(
        ["db", "deleted", "freed_bytes", "error", "tables", "date_col"])
    assert any(s.strip().upper().startswith("VACUUM") for s in seen)  # 照常 VACUUM


def test_sqlite_default_dedupe_fields_and_vacuum(tmp_path, monkeypatch):
    db = tmp_path / "cache.db"
    _make_dup_db(db, symbols=1, windows=5)
    seen = []
    real = sqlite3.connect
    monkeypatch.setattr(cm.sqlite3, "connect",
                        lambda *a, **k: _ConnProxy(real(*a, **k), seen))

    res = cm.prune_daily_cache_duplicates(db, keep_per_symbol=2)

    assert res["error"] is None
    assert res["deleted"] == 3
    assert res["kept"] == 2
    assert res["symbols"] == 1
    assert res["freed_bytes"] >= 0
    assert "vacuum" not in res
    assert sorted(res) == sorted(
        ["db", "deleted", "kept", "freed_bytes", "symbols", "error"])
    assert any("VACUUM" in s.upper() for s in seen)


# ── 2. bypass_env=SQLite：清理作用于 env 指向的临时库 ──────────────────

def test_bypass_sqlite_env_targets_tmp_db(tmp_path, monkeypatch):
    default_db = tmp_path / "default_cache.db"   # 故意不存在
    tmp_db = tmp_path / "tmp_cache.db"
    _make_cache_db(tmp_db, old_rows=6, new_rows=2)
    monkeypatch.setenv("SS_CACHE_DB_URL", f"sqlite:///{tmp_db}")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    res = cm.prune_sqlite_cache(default_db, ["daily_cache"], days=90,
                                bypass_env="SS_CACHE_DB_URL")

    assert res["error"] is None                # 本地默认路径不存在不再误判 missing
    assert res["deleted"] == 6                 # 清理落在 tmp 库
    assert res["db"] == str(default_db)        # 报告字段仍为传入路径（口径不变）
    assert "vacuum" not in res
    assert not default_db.exists()             # 默认路径未被创建/触碰

    conn = sqlite3.connect(str(tmp_db))
    old = conn.execute("SELECT COUNT(*) FROM daily_cache WHERE cache_key LIKE 'old_%'").fetchone()[0]
    new = conn.execute("SELECT COUNT(*) FROM daily_cache WHERE cache_key LIKE 'new_%'").fetchone()[0]
    conn.close()
    assert old == 0 and new == 2


# ── 3. PG 场景：URL / 无 exists / 无 VACUUM / 如实标注 ─────────────────

def test_pg_prune_uses_resolved_url_and_skips_exists_vacuum(tmp_path, monkeypatch):
    pg_url = "postgresql://u:p@dbhost:5432/ssdb"
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.delenv("SS_CACHE_DB_URL", raising=False)
    default_db = tmp_path / "never_created.db"
    calls = _pg_capture(monkeypatch)

    res = cm.prune_sqlite_cache(default_db, ["daily_cache", "index_cache"], days=90,
                                bypass_env="SS_CACHE_DB_URL")

    # (a) 使用 resolve_bypass_url 解析出的 PG URL
    assert calls["url"] == bd.resolve_bypass_url("SS_CACHE_DB_URL", str(default_db)) == pg_url
    # (b) 未执行本地 exists 前置：本地库不存在也不报 missing
    assert res["error"] is None
    assert res["deleted"] == 4               # 两张表各 2 行（桩 rowcount=2）
    assert not default_db.exists()
    # (c) 未执行 VACUUM + 如实标注 + freed_bytes=0
    assert not any("VACUUM" in s.upper() for s in calls["sql"])
    assert res["vacuum"] == "skipped_pg_autovacuum"
    assert res["freed_bytes"] == 0
    assert calls["closed"] is True


def test_pg_dedupe_uses_resolved_url_and_skips_exists_vacuum(tmp_path, monkeypatch):
    pg_url = "postgresql://u:p@dbhost/ssdb"
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.delenv("SS_CACHE_DB_URL", raising=False)
    default_db = tmp_path / "never_created.db"
    rows = [
        ("daily_600028_2026-01-01_2026-10-01_qfq", "2026-10-01T00:00:00"),
        ("daily_600028_2026-01-02_2026-10-02_qfq", "2026-10-02T00:00:00"),
        ("daily_600028_2026-01-03_2026-10-03_qfq", "2026-10-03T00:00:00"),
    ]
    calls = _pg_capture(monkeypatch, rows=rows)

    res = cm.prune_daily_cache_duplicates(default_db, keep_per_symbol=1,
                                          bypass_env="SS_CACHE_DB_URL")

    assert calls["url"] == bd.resolve_bypass_url("SS_CACHE_DB_URL", str(default_db)) == pg_url
    assert res["error"] is None
    assert res["deleted"] == 2 and res["kept"] == 1 and res["symbols"] == 1
    assert len(calls["executemany"]) == 2     # 删除经 executemany 原样下发
    assert not any("VACUUM" in s.upper() for s in calls["sql"])
    assert res["vacuum"] == "skipped_pg_autovacuum"
    assert res["freed_bytes"] == 0
    assert not default_db.exists()


def test_pg_missing_table_does_not_exist_is_expected(tmp_path, monkeypatch):
    """PG 的 'relation ... does not exist' 与 SQLite 的 'no such table' 同等跳过。"""
    pg_url = "postgresql://u:p@dbhost/ssdb"
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.delenv("SS_CACHE_DB_URL", raising=False)
    default_db = tmp_path / "never_created.db"
    # 单独桩：让 DELETE 抛 PG 的 "does not exist" 文案
    calls = {"sql": []}

    class _Boom:
        def execute(self, sql, params=()):
            calls["sql"].append(sql)
            raise RuntimeError('relation "daily_cache" does not exist')

        def commit(self):
            calls["sql"].append("COMMIT")

        def close(self):
            pass

    monkeypatch.setattr(bd, "open_connection", lambda url: _Boom())

    res = cm.prune_sqlite_cache(default_db, ["daily_cache"], days=90,
                                bypass_env="SS_CACHE_DB_URL")

    assert res["error"] is None
    assert res["deleted"] == 0
    assert res["vacuum"] == "skipped_pg_autovacuum"
    assert res["freed_bytes"] == 0
