# -*- coding: utf-8 -*-
"""tests/test_display_provenance_bypass_dialect.py — 展示源溯源读库接入 PG17 方言层守卫。

验证 modules/display_provenance.py 的裸 sqlite3.connect 已收敛到 db_dialect 单一真源：
- 默认（无 SS_CACHE_DB_URL / 非 PG）行为与改前逐字段一致（回归底线）；
- 设 SS_CACHE_DB_URL 时读取指向该库而非默认 _CACHE_DB；
- PG 下经 resolve_bypass_url → open_connection，跳过本地 exists 前置（沙箱不真连 psycopg）。

诚实语义不变：抽不到内容日期一律 None/unknown，绝不臆造 mtime 兜底。
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from backend import db_dialect as dbd
from modules import display_provenance as dp

_ROWS = {
    "index_cache": ("index_000001_x", json.dumps([
        {"date": "2026-09-01T00:00:00.000"},
        {"date": "2026-09-03T00:00:00.000"},
    ])),
    "daily_cache": ("daily_600519_qfq", json.dumps([
        {"date": "2026-10-06T00:00:00.000"},
        {"date": "2026-10-08T00:00:00.000"},
    ])),
    "rt_quote_cache": ("rt_quote_601088", json.dumps(
        {"ticker": "601088", "datetime": "2026-09-09 13:30:20"})),
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """每个用例从「无旁路 env / 非 PG」的干净进程态出发。"""
    monkeypatch.delenv("SS_CACHE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _make_db(path, tables, *, with_data=True):
    """在 path 建缓存表；with_data=False 时只建表不写业务行。"""
    with sqlite3.connect(str(path)) as c:
        for t in tables:
            c.execute(
                f"CREATE TABLE {t} (cache_key TEXT, data_json TEXT, updated_at TEXT)")
            if with_data:
                key, payload = _ROWS[t]
                c.execute(
                    f"INSERT INTO {t} VALUES (?,?,?)",
                    (key, payload, "2099-01-01T00:00:00"),  # 未来 mtime：不可被当作数据日
                )


# ───────────── 默认 SQLite：回归底线（字段/取值逐项一致） ─────────────

def test_default_sqlite_reads_real_date_col_array(tmp_path):
    db = tmp_path / "cache.db"
    _make_db(db, ["index_cache"])
    assert dp._sqlite_json_max_date(
        str(db), "index_cache", col="date", prefix="index_") == "2026-09-03"


def test_default_sqlite_reads_real_date_field_object(tmp_path):
    db = tmp_path / "cache.db"
    _make_db(db, ["rt_quote_cache"])
    assert dp._sqlite_json_max_date(
        str(db), "rt_quote_cache", field="datetime", prefix="rt_quote_") == "2026-09-09"


def test_default_sqlite_missing_table_or_empty_data_is_none(tmp_path):
    db = tmp_path / "cache.db"
    _make_db(db, ["index_cache"], with_data=False)  # 表在、无业务行；mtime 未来
    assert dp._sqlite_json_max_date(
        str(db), "index_cache", col="date", prefix="index_") is None
    # 缺表 → None
    assert dp._sqlite_json_max_date(str(db), "no_such_table", col="date") is None


def test_default_build_fields_and_values_unchanged(tmp_path, monkeypatch):
    db = tmp_path / "cache.db"
    _make_db(db, ["index_cache", "daily_cache", "rt_quote_cache"])
    monkeypatch.setattr(dp, "_CACHE_DB", str(db))

    rows = dp.build_display_provenance(["index_quote", "daily_kline", "realtime_quote"])
    assert len(rows) == 3
    expected_fields = {
        "key", "name", "as_of", "lag_days", "status", "is_fallback", "source_chain"}
    for r in rows:
        assert set(r) == expected_fields
        assert r["is_fallback"] is None
        assert r["source_chain"] is None
        assert r["status"] in {"ok", "warn", "stale"}
    by_key = {r["key"]: r for r in rows}
    assert by_key["index_quote"]["as_of"] == "2026-09-03"
    assert by_key["index_quote"]["name"] == "指数行情缓存"
    assert by_key["daily_kline"]["as_of"] == "2026-10-08"
    assert by_key["daily_kline"]["name"] == "个股日线缓存"
    assert by_key["realtime_quote"]["as_of"] == "2026-09-09"


def test_default_build_no_mtime_fallback(tmp_path, monkeypatch):
    """有缓存行但 data_json 无内容日期 → 仍 unknown（未来 mtime 不得冒充）。"""
    db = tmp_path / "cache.db"
    with sqlite3.connect(str(db)) as c:
        c.execute("CREATE TABLE index_cache (cache_key TEXT, data_json TEXT, updated_at TEXT)")
        c.execute("INSERT INTO index_cache VALUES (?,?,?)",
                  ("index_x", json.dumps([{"close": 1}]), "2099-01-01T00:00:00"))
    monkeypatch.setattr(dp, "_CACHE_DB", str(db))
    r = dp.build_display_provenance(["index_quote"])[0]
    assert r["as_of"] is None and r["status"] == "unknown"


# ───────────── SS_CACHE_DB_URL：旁路指向 tmp 库而非默认 _CACHE_DB ─────────────

def test_ss_cache_db_url_redirects_reads(tmp_path, monkeypatch):
    tmp_db = tmp_path / "ss_override.db"
    _make_db(tmp_db, ["index_cache"])
    # 默认库故意塞一个不同日期：若仍读默认库，断言必红
    default_db = tmp_path / "default_cache.db"
    with sqlite3.connect(str(default_db)) as c:
        c.execute("CREATE TABLE index_cache (cache_key TEXT, data_json TEXT, updated_at TEXT)")
        c.execute("INSERT INTO index_cache VALUES (?,?,?)",
                  ("index_x", json.dumps([{"date": "2001-01-01"}]), "t"))

    monkeypatch.setattr(dp, "_CACHE_DB", str(default_db))
    monkeypatch.setenv("SS_CACHE_DB_URL", "sqlite:///" + str(tmp_db))

    r = dp.build_display_provenance(["index_quote"])[0]
    assert r["as_of"] == "2026-09-03", "必须读 SS_CACHE_DB_URL 指向的 tmp 库，而非默认 _CACHE_DB"


def test_bypass_env_skips_local_exists_precheck(tmp_path, monkeypatch):
    """bypass 模式下本地 db_path 不存在也应读到数据（exists 前置被跳过）。"""
    real_db = tmp_path / "real.db"
    _make_db(real_db, ["index_cache"])
    monkeypatch.setenv("SS_CACHE_DB_URL", "sqlite:///" + str(real_db))
    ghost = tmp_path / "does_not_exist.db"

    assert dp._sqlite_json_max_date(
        str(ghost), "index_cache", col="date", prefix="index_",
        bypass_env="SS_CACHE_DB_URL") == "2026-09-03"


# ───────────── PG 方言：走 resolve_bypass_url/open_connection，无本地 exists 检查 ─────────────

def test_pg_dialect_uses_resolved_pg_url_without_local_exists(tmp_path, monkeypatch):
    PG_URL = "postgresql://user:pw@pg17.internal:5432/stocksignal"
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    # 无 SS_CACHE_DB_URL → resolve_bypass_url 应回落到 DATABASE_URL(PG)
    monkeypatch.delenv("SS_CACHE_DB_URL", raising=False)

    ghost = tmp_path / "no_local_cache.db"  # 刻意不创建：PG 下本地文件不存在属正常
    monkeypatch.setattr(dp, "_CACHE_DB", str(ghost))

    calls: list[str] = []

    class _FakeConn:
        """只实现 with / execute().fetchall()，绝不包含 psycopg/SQLAlchemy。"""
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=()):
            class _Result:
                def fetchall(self):
                    return [(json.dumps([{"date": "2026-11-20T09:30:00"}]),)]
            return _Result()

    def _fake_open_connection(url):
        calls.append(url)
        return _FakeConn()

    monkeypatch.setattr(dbd, "open_connection", _fake_open_connection)

    # exists 前置守卫：本用例里任何对 db_path 的本地 exists 探测都视为回退
    real_exists = dp.os.path.exists
    exists_targets: list[str] = []

    def _spy_exists(path):
        exists_targets.append(str(path))
        return real_exists(path)

    monkeypatch.setattr(dp.os.path, "exists", _spy_exists)

    assert dbd.resolve_bypass_url("SS_CACHE_DB_URL", str(ghost)) == PG_URL

    r = dp.build_display_provenance(["index_quote"])[0]
    assert r["as_of"] == "2026-11-20"
    assert calls, "bypass 模式必须经 open_connection 取连接"
    assert all(u == PG_URL for u in calls), f"连接 URL 必须为 resolve_bypass_url 解析出的 PG URL: {calls}"
    assert str(ghost) not in exists_targets, "PG bypass 模式不得做本地 exists 前置检查"
