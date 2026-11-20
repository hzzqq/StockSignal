# -*- coding: utf-8 -*-
"""backend/db_dialect.py 单一真源单测（SQLite / PostgreSQL 17 双库支持）。

设计原则（team-lead 验收点）：**不依赖真 PostgreSQL**——
- 方言判定、SQL 生成、占位符转换全部是无副作用纯函数，用字符串断言验证；
- PG 连接层只验证「fail-fast 显式报错、绝不静默回退 SQLite」的诚实红线
  （本沙箱无 psycopg / 无真 PG，真库连通性验证如实标记为遗留风险）；
- 生产接线验证：fetcher_base._write_cache / market_cache / macro_store 的
  upsert SQL 在 SQLite 方言下与既有语句**逐字节等价**；
- 反向验证：注入缺陷 → 断言变红；还原 → 恢复绿。
"""
from __future__ import annotations

import json
import sqlite3

import pytest

import backend.db_dialect as dbd
from backend.db_dialect import (
    Dialect,
    autoincrement_pk,
    bypass_dialect,
    column_exists_sql,
    current_dialect,
    dialect_from_url,
    insert_ignore_sql,
    list_tables_sql,
    now_expr,
    open_connection,
    open_sqlite_file_path,
    placeholder,
    qmark_to_named,
    resolve_bypass_url,
    table_exists_sql,
    upsert_sql,
)


# ── 1. 方言判定（DATABASE_URL → 枚举）───────────────────────────────────────

@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite:///E:/x/app.db", Dialect.SQLITE),
        ("sqlite:///data/app.db", Dialect.SQLITE),
        ("sqlite://", Dialect.SQLITE),
        ("sqlite:///:memory:", Dialect.SQLITE),
        ("postgresql://user:pw@localhost:5432/stocksignal", Dialect.POSTGRESQL),
        ("postgresql+psycopg://user:pw@localhost:5432/stocksignal", Dialect.POSTGRESQL),
        ("postgres://user:pw@localhost:5432/stocksignal", Dialect.POSTGRESQL),  # 别名
        (None, Dialect.SQLITE),   # 缺失 → 默认 SQLite（零回归）
        ("", Dialect.SQLITE),     # 空串 → 默认 SQLite
        ("mysql://x/y", Dialect.SQLITE),  # 无法识别 → 默认 SQLite
    ],
)
def test_dialect_from_url_matrix(url, expected):
    assert dialect_from_url(url) is expected


def test_current_dialect_reads_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert current_dialect() is Dialect.SQLITE  # 缺省零回归
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert current_dialect() is Dialect.POSTGRESQL
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/x.db")
    assert current_dialect() is Dialect.SQLITE


# ── 2. 基础片段（占位符 / 时间 / 自增主键）──────────────────────────────────

def test_placeholder_now_expr_autoincrement():
    assert placeholder(Dialect.SQLITE) == "?"
    assert placeholder(Dialect.POSTGRESQL) == "%s"
    assert now_expr(Dialect.SQLITE) == "datetime('now','localtime')"
    assert now_expr(Dialect.POSTGRESQL) == "now()"
    assert autoincrement_pk(Dialect.SQLITE) == "id INTEGER PRIMARY KEY AUTOINCREMENT"
    assert autoincrement_pk(Dialect.POSTGRESQL) == "id BIGSERIAL PRIMARY KEY"


# ── 3. upsert 生成器：SQLite 输出必须与既有 SQL 逐字节等价 ──────────────────

FETCHER_LEGACY = (
    "INSERT OR REPLACE INTO cache_probe (cache_key, data_json, updated_at) "
    "VALUES (?, ?, ?)"
)
MARKET_LEGACY = (
    "INSERT OR REPLACE INTO market_indicator_cache (key, date, value, updated_at) "
    "VALUES (?, ?, ?, datetime('now','localtime'))"
)


def test_upsert_sql_sqlite_byte_identical_fetcher():
    sql = upsert_sql(
        Dialect.SQLITE, "cache_probe",
        ("cache_key", "data_json", "updated_at"), ("cache_key",),
    )
    assert sql == FETCHER_LEGACY  # 逐字节等价（含空格与占位符数量）


def test_upsert_sql_sqlite_byte_identical_market_indicator():
    d = Dialect.SQLITE
    sql = upsert_sql(
        d, "market_indicator_cache",
        ("key", "date", "value", "updated_at"), ("key", "date"),
        value_exprs=[placeholder(d), placeholder(d), placeholder(d), now_expr(d)],
    )
    assert sql == MARKET_LEGACY  # 逐字节等价（含 datetime('now','localtime') 默认值）


def test_upsert_sql_postgresql_on_conflict_by_pk():
    sql = upsert_sql(
        Dialect.POSTGRESQL, "cache_probe",
        ("cache_key", "data_json", "updated_at"), ("cache_key",),
    )
    assert sql == (
        "INSERT INTO cache_probe (cache_key, data_json, updated_at) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (cache_key) DO UPDATE SET "
        "data_json = EXCLUDED.data_json, updated_at = EXCLUDED.updated_at"
    )


def test_upsert_sql_postgresql_market_indicator_composite_pk():
    d = Dialect.POSTGRESQL
    sql = upsert_sql(
        d, "market_indicator_cache",
        ("key", "date", "value", "updated_at"), ("key", "date"),
        value_exprs=[placeholder(d), placeholder(d), placeholder(d), now_expr(d)],
    )
    assert "INSERT INTO market_indicator_cache (key, date, value, updated_at)" in sql
    assert "VALUES (%s, %s, %s, now())" in sql
    assert "ON CONFLICT (key, date) DO UPDATE SET" in sql
    assert "value = EXCLUDED.value" in sql
    assert "updated_at = EXCLUDED.updated_at" in sql


def test_upsert_sql_value_exprs_length_mismatch():
    with pytest.raises(ValueError, match="数量"):
        upsert_sql(
            Dialect.SQLITE, "t", ("a", "b"), ("a",),
            value_exprs=["?"],
        )


def test_insert_ignore_sql_both_dialects():
    assert insert_ignore_sql(
        Dialect.SQLITE, "t", ("a", "b"),
    ) == "INSERT OR IGNORE INTO t (a, b) VALUES (?, ?)"
    assert insert_ignore_sql(
        Dialect.POSTGRESQL, "t", ("a", "b"), ("a",),
    ) == "INSERT INTO t (a, b) VALUES (%s, %s) ON CONFLICT (a) DO NOTHING"
    assert insert_ignore_sql(
        Dialect.POSTGRESQL, "t", ("a", "b"),
    ) == "INSERT INTO t (a, b) VALUES (%s, %s) ON CONFLICT DO NOTHING"


# ── 4. 表/列存在性探测：双分支 SQL 字符串断言 ────────────────────────────────

def test_table_exists_sql_both_dialects():
    sql_sq, params_sq = table_exists_sql(Dialect.SQLITE, "price_alert")
    assert sql_sq == "SELECT name FROM sqlite_master WHERE type='table' AND name = ?"
    assert params_sq == ("price_alert",)

    sql_pg, params_pg = table_exists_sql(Dialect.POSTGRESQL, "price_alert")
    assert "information_schema.tables" in sql_pg
    assert "table_name = :t" in sql_pg
    assert params_pg == {"t": "price_alert"}


def test_list_tables_sql_both_dialects():
    sql_sq, params_sq = list_tables_sql(Dialect.SQLITE)
    assert sql_sq == "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    assert params_sq == ()

    sql_pg, params_pg = list_tables_sql(Dialect.POSTGRESQL)
    assert "information_schema.tables" in sql_pg
    assert "table_name" in sql_pg
    assert params_pg == {}


def test_column_exists_sql_both_dialects():
    sql_sq, params_sq = column_exists_sql(Dialect.SQLITE, "stocks", "asset_type")
    assert sql_sq == "PRAGMA table_info(stocks)"
    assert params_sq == ()

    sql_pg, params_pg = column_exists_sql(Dialect.POSTGRESQL, "stocks", "asset_type")
    assert "information_schema.columns" in sql_pg
    assert "table_name = :t" in sql_pg
    assert "column_name = :c" in sql_pg
    assert params_pg == {"t": "stocks", "c": "asset_type"}


# ── 5. qmark_to_named：PG 执行边界的占位符转换 ──────────────────────────────

def test_qmark_to_named_basic():
    sql_n, binds = qmark_to_named(
        "SELECT * FROM t WHERE a = ? AND b LIKE ?", ("x", "%y%")
    )
    assert sql_n == "SELECT * FROM t WHERE a = :p0 AND b LIKE :p1"
    assert binds == {"p0": "x", "p1": "%y%"}


def test_qmark_to_named_no_placeholder():
    sql_n, binds = qmark_to_named("SELECT COUNT(*) FROM t", None)
    assert sql_n == "SELECT COUNT(*) FROM t"
    assert binds == {}


def test_qmark_to_named_count_mismatch():
    with pytest.raises(ValueError, match="数量不匹配"):
        qmark_to_named("INSERT INTO t VALUES (?, ?, ?)", ("x",))


# ── 6. 旁路库 URL 解析（模块级 env > DATABASE_URL(PG) > SQLite 路径）────────

def test_resolve_bypass_url_priority(monkeypatch, tmp_path):
    default = str(tmp_path / "cache.db")
    monkeypatch.delenv("SS_TEST_BYPASS_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # ① 无任何 env → SQLite 默认路径（生产行为零变化）
    assert resolve_bypass_url("SS_TEST_BYPASS_URL", default) == default
    assert bypass_dialect("SS_TEST_BYPASS_URL", default) is Dialect.SQLITE
    # ② DATABASE_URL 为 PG → 旁路库跟随主库方言
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert resolve_bypass_url("SS_TEST_BYPASS_URL", default) == "postgresql://u:p@h/db"
    assert bypass_dialect("SS_TEST_BYPASS_URL", default) is Dialect.POSTGRESQL
    # ③ 模块级 env 显式指定 → 最高优先级
    monkeypatch.setenv("SS_TEST_BYPASS_URL", "postgresql://u:p@h/other")
    assert resolve_bypass_url("SS_TEST_BYPASS_URL", default) == "postgresql://u:p@h/other"


def test_open_sqlite_file_path():
    assert open_sqlite_file_path("sqlite:///E:/x/app.db") == "E:/x/app.db"
    assert open_sqlite_file_path("data/cache.db") == "data/cache.db"  # 裸路径原样


def test_open_connection_sqlite_branch():
    conn = open_connection("sqlite:///:memory:")
    assert isinstance(conn, sqlite3.Connection)
    conn.close()
    conn = open_connection(":memory:")  # 裸路径也接受
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


# ── 7. 诚实红线：PG 连接失败必须显式报错，绝不静默回退 SQLite ────────────────

def test_pg_connection_fail_fast_no_silent_fallback():
    try:
        import psycopg  # noqa: F401
        has_driver = True
    except ImportError:
        has_driver = False
    if has_driver:
        pytest.skip("本环境已安装 psycopg，『驱动缺失显式报错』分支不适用；"
                    "真库连通性验证需真 PostgreSQL，属遗留风险另行验证")
    pg_url = "postgresql://user:pw@127.0.0.1:5432/stocksignal"
    with pytest.raises(RuntimeError, match="psycopg"):
        dbd.pg_engine(pg_url)
    with pytest.raises(RuntimeError):
        open_connection(pg_url)  # 绝不回退 sqlite3.connect


# ── 8. 生产接线：SQLite 方言下与既有 SQL 逐字节等价 ──────────────────────────

def test_market_cache_upsert_sql_dialect_aware(monkeypatch):
    from modules.market_cache import _indicator_upsert_sql

    monkeypatch.delenv("SS_MARKET_CACHE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _indicator_upsert_sql() == MARKET_LEGACY  # 逐字节等价（绿）

    monkeypatch.setenv("SS_MARKET_CACHE_URL", "postgresql://u:p@h/db")
    sql = _indicator_upsert_sql()
    assert sql.startswith("INSERT INTO market_indicator_cache")
    assert "VALUES (%s, %s, %s, now())" in sql
    assert "ON CONFLICT (key, date) DO UPDATE SET" in sql


def test_macro_store_upsert_sql_dialect_aware(monkeypatch):
    from modules.macro_store import _upsert_macro_sql

    # 原语句历史上是 macro_history( 无空格拼接形式 —— 必须逐字节保持
    macro_legacy = (
        "INSERT OR REPLACE INTO macro_history"
        "(key, date, value, prev, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?)"
    )
    monkeypatch.delenv("MACRO_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _upsert_macro_sql() == macro_legacy

    monkeypatch.setenv("MACRO_DB_URL", "postgresql://u:p@h/db")
    sql = _upsert_macro_sql()
    assert sql.startswith("INSERT INTO macro_history (key, date,")
    assert "VALUES (%s, %s, %s, %s, %s, %s)" in sql
    assert "ON CONFLICT (key, date) DO UPDATE SET" in sql


class _RecordingConn:
    """记录 execute 调用的桩连接（无需真库）。"""

    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params) if params is not None else params))
        return None

    def commit(self):
        pass


def test_fetcher_write_cache_wiring_and_reverse_verification(monkeypatch):
    """fetcher_base._write_cache 生产接线 + 反向验证（注入缺陷→红 / 还原→绿）。"""
    import modules.fetcher_base as fb

    f = object.__new__(fb.BaseFetcher)
    f.db_path = "data/cache_probe.db"
    f._init_cache_table = lambda conn, table: None  # 桩：建表另行覆盖
    conn = _RecordingConn()

    # ── 基线（绿）：SQLite 方言输出与既有 SQL 逐字节等价 ──
    f._write_cache(conn, "cache_probe", "k1", {"a": 1})
    sql, params = conn.calls[-1]
    assert sql == FETCHER_LEGACY
    assert params[0] == "k1"
    assert json.loads(params[1]) == {"a": 1}
    assert params[2]  # updated_at 非空

    # ── 反向验证①：注入缺陷（丢失 OR REPLACE 的 upsert 语义）→ 断言必须变红 ──
    real_upsert = dbd.upsert_sql

    def broken_upsert(dialect, table, columns, conflict_cols, value_exprs=None):
        return real_upsert(dialect, table, columns, conflict_cols, value_exprs).replace(
            "INSERT OR REPLACE", "INSERT"
        )

    monkeypatch.setattr(dbd, "upsert_sql", broken_upsert)
    f._write_cache(conn, "cache_probe", "k2", {"b": 2})
    assert conn.calls[-1][0] != FETCHER_LEGACY  # 缺陷已传导到生产调用点（红）

    # ── 反向验证②：还原缺陷 → 同一断言恢复绿 ──
    monkeypatch.setattr(dbd, "upsert_sql", real_upsert)
    f._write_cache(conn, "cache_probe", "k3", {"c": 3})
    assert conn.calls[-1][0] == FETCHER_LEGACY  # 还原后（绿）


def test_config_sqlite_engine_options_unchanged():
    """测试会话 DATABASE_URL 为 SQLite → 引擎选项保持既有 connect_args（零回归）。"""
    from backend.config import Config

    uri = Config.SQLALCHEMY_DATABASE_URI
    assert dialect_from_url(uri) is Dialect.SQLITE
    assert Config.SQLALCHEMY_ENGINE_OPTIONS["connect_args"] == {
        "check_same_thread": False,
        "timeout": 30,
    }
    assert Config.SQLALCHEMY_ENGINE_OPTIONS["pool_pre_ping"] is True
    assert Config.SQLALCHEMY_ENGINE_OPTIONS["pool_size"] == 10
    assert Config.SQLALCHEMY_ENGINE_OPTIONS["max_overflow"] == 20
