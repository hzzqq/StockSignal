# -*- coding: utf-8 -*-
"""backend/db_dialect.py
=======================
数据库方言适配层 —— SQLite / PostgreSQL 17 双库支持的**单一真源**。

职责（全仓唯一判定与转换入口，禁止在业务代码散落 `startswith("sqlite")`）：
  1. 方言判定：``dialect_from_url(url)`` / ``current_dialect()`` —— 以
     ``DATABASE_URL`` 为开关（``postgresql://`` / ``postgresql+psycopg://`` →
     PostgreSQL；``sqlite://`` 或缺失 → SQLite，保证默认行为零变化）。
  2. SQL 生成（纯函数，可字符串断言单测，不依赖真库）：
     - ``upsert_sql``：SQLite ``INSERT OR REPLACE`` ↔ PG ``ON CONFLICT (pk) DO UPDATE SET``
     - ``insert_ignore_sql``：SQLite ``INSERT OR IGNORE`` ↔ PG ``ON CONFLICT DO NOTHING``
     - ``table_exists_sql`` / ``list_tables_sql`` / ``column_exists_sql``：
       SQLite ``sqlite_master`` / ``PRAGMA table_info`` ↔ PG ``information_schema``
     - ``placeholder`` / ``now_expr`` / ``autoincrement_pk``：占位符、时间默认值、自增主键
  3. 连接适配：``open_connection`` / ``pg_engine`` —— SQLite 走 ``sqlite3``；
     PG 走 SQLAlchemy（内部 psycopg）。**PG 连接失败一律显式抛错（fail-fast），
     绝不静默回退 SQLite**（诚实红线：防止「以为在用 PG 其实在用 SQLite」的假象）。

旁路库（裸 sqlite3 直连、不受 ORM 管理的独立库，如 data/cache.db、
data/market_cache.db、data/news.db、data/macro_history.db）通过
``resolve_bypass_url`` 跟随主库方言：``DATABASE_URL`` 为 PG 时旁路表建在同一
PG 库内（表名互不冲突），``SS_*_DB_URL`` 模块级 env 可显式覆盖。

设计约束：本模块顶层零重量级依赖（不 import sqlalchemy 到模块级），保证
``modules/`` 在无 Flask 环境下也可安全导入。
"""
from __future__ import annotations

import enum
import os
import sqlite3
from typing import Any, Dict, Optional, Sequence, Tuple  # noqa: UP035

__all__ = [
    "Dialect",
    "dialect_from_url",
    "current_dialect",
    "is_sqlite_url",
    "placeholder",
    "now_expr",
    "autoincrement_pk",
    "upsert_sql",
    "insert_ignore_sql",
    "table_exists_sql",
    "list_tables_sql",
    "column_exists_sql",
    "qmark_to_named",
    "resolve_bypass_url",
    "bypass_dialect",
    "open_sqlite_file_path",
    "open_connection",
    "pg_engine",
    "PgCompatConnection",
    "SQLITE_URL_PREFIXES",
    "POSTGRES_URL_PREFIXES",
]


# ── 1. 方言判定（单一真源）─────────────────────────────────────────────────

SQLITE_URL_PREFIXES: Tuple[str, ...] = ("sqlite://",)
# postgres:// 为 Heroku 风格别名，一并识别；postgresql+psycopg2 兼容旧驱动声明
POSTGRES_URL_PREFIXES: Tuple[str, ...] = (
    "postgresql://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
    "postgres://",
)


class Dialect(str, enum.Enum):
    """数据库方言枚举。"""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


def dialect_from_url(url: Optional[str]) -> Dialect:
    """``DATABASE_URL`` → 方言枚举。

    判定规则表（team-lead 验收点）：
        ================================  ============
        输入                              方言
        ================================  ============
        ``sqlite:///E:/x/app.db``         SQLITE
        ``sqlite:///data/app.db``         SQLITE
        ``sqlite://`` / 内存库            SQLITE
        ``postgresql://...``              POSTGRESQL
        ``postgresql+psycopg://...``      POSTGRESQL
        ``postgres://...``（别名）        POSTGRESQL
        ``None`` / ``""``（缺失/未设）    SQLITE（默认，零回归）
        其他无法识别的串                  SQLITE（默认，零回归）
        ================================  ============
    """
    if not url:
        return Dialect.SQLITE
    u = str(url).strip().lower()
    if u.startswith(POSTGRES_URL_PREFIXES):
        return Dialect.POSTGRESQL
    return Dialect.SQLITE


def current_dialect() -> Dialect:
    """进程级方言判定：读 ``DATABASE_URL`` 环境变量（缺失默认 SQLite）。"""
    return dialect_from_url(os.environ.get("DATABASE_URL"))


def is_sqlite_url(url: Optional[str]) -> bool:
    return dialect_from_url(url) is Dialect.SQLITE


# ── 2. SQL 生成器（纯函数，字符串断言可测）────────────────────────────────

def placeholder(dialect: Dialect) -> str:
    """参数占位符：SQLite ``?`` ↔ PG ``%s``。"""
    return "?" if dialect is Dialect.SQLITE else "%s"


def now_expr(dialect: Dialect) -> str:
    """「当前本地时间」SQL 表达式：``datetime('now','localtime')`` ↔ ``now()``。"""
    return "datetime('now','localtime')" if dialect is Dialect.SQLITE else "now()"


def autoincrement_pk(dialect: Dialect, column: str = "id") -> str:
    """自增主键列定义：``INTEGER PRIMARY KEY AUTOINCREMENT`` ↔ ``BIGSERIAL PRIMARY KEY``。"""
    if dialect is Dialect.SQLITE:
        return f"{column} INTEGER PRIMARY KEY AUTOINCREMENT"
    return f"{column} BIGSERIAL PRIMARY KEY"


def upsert_sql(
    dialect: Dialect,
    table: str,
    columns: Sequence[str],
    conflict_cols: Sequence[str],
    value_exprs: Optional[Sequence[str]] = None,
) -> str:
    """生成 upsert SQL（按主键/唯一键列冲突处理）。

    - SQLite：``INSERT OR REPLACE INTO t (cols) VALUES (?, ...)``（与既有 SQL 逐字节等价）
    - PostgreSQL：``INSERT INTO t (cols) VALUES (%s, ...) ON CONFLICT (pk) DO UPDATE SET
      col = EXCLUDED.col, ...``

    ``value_exprs`` 可选：逐列自定义取值表达式（默认全部用占位符），
    用于 ``updated_at`` 这类带 ``DEFAULT (datetime('now','localtime'))`` /
    ``now()`` 的列。
    """
    cols = ", ".join(columns)
    if value_exprs is None:
        exprs = [placeholder(dialect)] * len(columns)
    else:
        if len(value_exprs) != len(columns):
            raise ValueError(
                f"value_exprs 数量({len(value_exprs)})与 columns({len(columns)})不一致"
            )
        exprs = list(value_exprs)
    phs = ", ".join(exprs)
    if dialect is Dialect.SQLITE:
        return f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({phs})"
    conflict = ", ".join(conflict_cols)
    set_cols = [c for c in columns if c not in conflict_cols]
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in set_cols)
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({phs}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {sets}"
    )


def insert_ignore_sql(
    dialect: Dialect,
    table: str,
    columns: Sequence[str],
    conflict_cols: Optional[Sequence[str]] = None,
) -> str:
    """生成「冲突即跳过」的插入 SQL。

    - SQLite：``INSERT OR IGNORE INTO t (cols) VALUES (?, ...)``
    - PostgreSQL：``INSERT INTO t (cols) VALUES (%s, ...) ON CONFLICT [(pk)] DO NOTHING``
      （PG 15+ 支持无目标的 ``ON CONFLICT DO NOTHING``；指定 ``conflict_cols``
      时生成带目标的形式）
    """
    cols = ", ".join(columns)
    phs = ", ".join([placeholder(dialect)] * len(columns))
    if dialect is Dialect.SQLITE:
        return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({phs})"
    if conflict_cols:
        return (
            f"INSERT INTO {table} ({cols}) VALUES ({phs}) "
            f"ON CONFLICT ({', '.join(conflict_cols)}) DO NOTHING"
        )
    return f"INSERT INTO {table} ({cols}) VALUES ({phs}) ON CONFLICT DO NOTHING"


def table_exists_sql(dialect: Dialect, table: str) -> Tuple[str, Any]:
    """单表存在性探测 SQL。

    - SQLite：``SELECT name FROM sqlite_master WHERE type='table' AND name = ?``（元组参数）
    - PostgreSQL：``SELECT 1 FROM information_schema.tables WHERE table_schema =
      current_schema() AND table_name = :t``（命名参数，供 SQLAlchemy ``text()`` 执行）

    返回 ``(sql, params)``；调用方只需判断结果是否非空。
    """
    if dialect is Dialect.SQLITE:
        return "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    return (
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = :t"
    ), {"t": table}


def list_tables_sql(dialect: Dialect) -> Tuple[str, Any]:
    """列出当前库全部表名。

    - SQLite：``SELECT name FROM sqlite_master WHERE type='table' ORDER BY name``
    - PostgreSQL：``SELECT table_name FROM information_schema.tables WHERE
      table_schema = current_schema() ORDER BY table_name``
    """
    if dialect is Dialect.SQLITE:
        return "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", ()
    return (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() ORDER BY table_name"
    ), {}


def column_exists_sql(dialect: Dialect, table: str, column: str) -> Tuple[str, Any]:
    """列存在性探测 SQL（迁移脚本用）。

    - SQLite：``PRAGMA table_info(t)``（PRAGMA 不支持参数绑定，表名经调用方
      白名单/常量注入，本函数仅接受字面表名）
    - PostgreSQL：``information_schema.columns`` 查询（命名参数）
    """
    if dialect is Dialect.SQLITE:
        return f"PRAGMA table_info({table})", ()
    return (
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}


def qmark_to_named(sql: str, params: Optional[Sequence[Any]]) -> Tuple[str, Dict[str, Any]]:
    """SQLite 风格 ``?`` 占位符 SQL → SQLAlchemy ``text()`` 兼容的 ``:pN`` 命名占位符。

    这是旁路模块（历史上全部用 ``?`` 占位符书写 SQL）跑在 PG 上的适配核心：
    SQL 文本不必改写，由本函数在执行边界做一次转换。占位符数量与参数数量
    必须一致，否则抛 ``ValueError``（防错位绑定）。
    """
    params = tuple(params or ())
    parts = sql.split("?")
    n_ph = len(parts) - 1
    if n_ph != len(params):
        raise ValueError(
            f"占位符数量不匹配: SQL 含 {n_ph} 个 '?', 传入 {len(params)} 个参数"
        )
    if n_ph == 0:
        return sql, {}
    out = parts[0]
    binds: Dict[str, Any] = {}
    for i, seg in enumerate(parts[1:]):
        out += f":p{i}" + seg
        binds[f"p{i}"] = params[i]
    return out, binds


# ── 3. 旁路库 URL 解析 ─────────────────────────────────────────────────────

def resolve_bypass_url(env_var: str, sqlite_default_path: str) -> str:
    """旁路库连接目标解析（优先级：模块级 env > DATABASE_URL(PG) > SQLite 文件路径）。

    - 模块级 env（如 ``SS_CACHE_DB_URL`` / ``SS_MARKET_CACHE_URL``）显式指定 → 直接采用；
    - 否则 ``DATABASE_URL`` 为 PostgreSQL → 旁路表建在同一 PG 库内（跟随主库方言）；
    - 否则 → 默认 SQLite 文件路径（生产默认行为，零变化）。
    """
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit
    if current_dialect() is Dialect.POSTGRESQL:
        return os.environ["DATABASE_URL"]
    return sqlite_default_path


def bypass_dialect(env_var: str, sqlite_default_path: str) -> Dialect:
    """旁路库方言判定（``resolve_bypass_url`` 的方言视图）。"""
    return dialect_from_url(resolve_bypass_url(env_var, sqlite_default_path))


# ── 4. 连接层（PG 失败显式抛错，绝不静默回退 SQLite）───────────────────────

def open_sqlite_file_path(url: str) -> str:
    """``sqlite:///<path>`` → 文件路径（裸路径原样返回，供 ``sqlite3.connect``）。"""
    path = url
    for prefix in ("sqlite:///", "sqlite://"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    return path


_PG_ENGINES: Dict[str, Any] = {}


def pg_engine(url: str):
    """PostgreSQL 引擎（按 URL 进程内缓存）。

    驱动缺失（未安装 psycopg）或后续连接失败 → **显式抛错**，绝不回退 SQLite。
    """
    try:
        from sqlalchemy import create_engine  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - SQLAlchemy 是硬依赖
        raise RuntimeError("SQLAlchemy 未安装，无法连接 PostgreSQL") from e
    engine = _PG_ENGINES.get(url)
    if engine is None:
        try:
            __import__("psycopg")
        except ImportError as e:
            raise RuntimeError(
                "PostgreSQL 方言需要 psycopg 驱动（pip install \"psycopg[binary]\"）。"
                "连接失败即显式报错——绝不静默回退 SQLite（诚实红线）。"
            ) from e
        engine = create_engine(url, pool_pre_ping=True)
        _PG_ENGINES[url] = engine
    return engine


class PgCompatConnection:
    """PostgreSQL 侧的 SQLite-兼容薄适配（包一层 SQLAlchemy ``Connection``）。

    让旁路模块**不改动其 SQL 书写风格**（``?`` 占位符、``executemany``、
    ``executescript``、``row["col"]`` 命名访问、``with conn:`` 事务、
    ``commit/rollback/close``）即可运行在 PG 上：

    - ``Row`` 语义：SQLAlchemy ``Row`` 同时支持索引访问 ``row[0]`` 与映射访问
      ``row["col"]``，覆盖 ``sqlite3.Row`` 的两种用法；
    - ``execute(sql, tuple)``：经 ``qmark_to_named`` 转成 ``text()`` + 命名参数，
      由 SQLAlchemy 负责驱动参数风格与 SQL 内 ``%`` 字面量转义；
    - ``sa_conn`` 属性暴露底层 ``Connection``，供 ``pandas.read_sql_query``
      等需要原生 connectable 的调用方使用。
    """

    ss_dialect = Dialect.POSTGRESQL  # 方言标记（sqlite3 连接无法挂属性）

    def __init__(self, sa_conn: Any) -> None:
        self._sa = sa_conn

    @property
    def sa_conn(self) -> Any:
        return self._sa

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        from sqlalchemy import text  # noqa: PLC0415

        sql_n, binds = qmark_to_named(sql, params)
        return self._sa.execute(text(sql_n), binds)

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Any:
        from sqlalchemy import text  # noqa: PLC0415

        payload = []
        sql_n = sql
        for p in seq_of_params:
            sql_n, binds = qmark_to_named(sql, p)
            payload.append(binds)
        if not payload:
            return None
        return self._sa.execute(text(sql_n), payload, executemany=True)

    def executescript(self, script: str) -> None:
        """按 ``;`` 切分执行 DDL 脚本（旁路库 schema 均为简单建表/建索引语句）。"""
        from sqlalchemy import text  # noqa: PLC0415

        for stmt in script.split(";"):
            s = stmt.strip()
            # 跳过空块与纯注释块（"-- ..." 引导的说明）
            if s and not all(
                line.strip() == "" or line.strip().startswith("--")
                for line in s.splitlines()
            ):
                self._sa.execute(text(s))

    def commit(self) -> None:
        self._sa.commit()

    def rollback(self) -> None:
        self._sa.rollback()

    def close(self) -> None:
        self._sa.close()

    def __enter__(self) -> "PgCompatConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> Any:  # noqa: ANN001
        # 与 sqlite3 ``with conn:`` 语义一致：无异常提交，有异常回滚
        return self._sa.__exit__(exc_type, exc, tb)


def open_connection(url: str) -> Any:
    """按 URL 方言打开数据库连接。

    - SQLite → ``sqlite3.connect``（裸文件路径也接受）；
    - PostgreSQL → :class:`PgCompatConnection`（经 SQLAlchemy / psycopg）。

    **PG 连接失败（驱动缺失 / 连不上）一律显式抛错，绝不静默回退 SQLite。**
    """
    dialect = dialect_from_url(url)
    if dialect is Dialect.SQLITE:
        return sqlite3.connect(open_sqlite_file_path(url))
    return PgCompatConnection(pg_engine(url).connect())
