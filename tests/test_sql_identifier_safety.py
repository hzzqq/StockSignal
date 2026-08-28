"""tests/test_sql_identifier_safety.py

SQLite **标识符（表名）注入**防护回归。

背景（Cycle 64 审计）：
- ``modules/fetcher.py`` 的缓存层需要动态表名，而 SQLite 的参数绑定（``?``）
  只支持「值」占位，**不支持标识符占位**，因此拼接表名在语法上不可避免。
- 审计确认：全部 10 处 f-string SQL 都只拼接标识符，**值一律走 ``?`` 绑定**；
  且当前所有调用点传入的都是硬编码字面量，暂不可被外部利用。
- 但 ``clear_cache(table_name=...)`` 是公开方法，其参数直接拼进
  ``DELETE FROM {t}``——属于潜在注入汇点（sink）。因此加白名单校验做纵深防御，
  确保将来任何调用方传入污点数据也不会被执行。

本测试锁定三条：
  1. 合法表名（现有缓存表）必须放行，不能因为加了校验而误伤正常功能；
  2. 注入载荷必须被拒绝（ValueError），且绝不进入 SQL；
  3. 源码中所有 ``_init_cache_table``/``clear_cache`` 的硬编码表名都必须合法
     （防止将来新增表名不符合规则被静默拦掉）。

2026-08-28 新增（Cycle 64）。
"""
import ast
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.fetcher import StockFetcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 已知的合法缓存表名（必须与 fetcher.py 中实际使用的一致）
KNOWN_TABLES = [
    "daily_cache", "index_cache", "macro_cache", "commodity_cache",
    "sector_cache", "rt_quote_cache", "stock_name_cache", "all_stocks",
]

EVIL_PAYLOADS = [
    "daily_cache; DROP TABLE users--",
    "daily_cache; DELETE FROM users",
    "daily_cache' OR '1'='1",
    'daily_cache" ; DROP TABLE t; --',
    "daily cache",           # 含空格
    "daily-cache",           # 含连字符
    "daily/cache",           # 含斜杠
    "",                      # 空串
    "1daily_cache",          # 数字开头
]


def _bare_instance():
    """绕过 __init__（避免构造时触发网络/DB 预热），只测标识符校验逻辑。"""
    return StockFetcher.__new__(StockFetcher)


def test_known_cache_tables_accepted():
    for name in KNOWN_TABLES:
        assert StockFetcher._safe_ident(name) == name


def test_safe_ident_rejects_injection_payloads():
    for payload in EVIL_PAYLOADS:
        with pytest.raises(ValueError):
            StockFetcher._safe_ident(payload)
    # 非字符串类型同样拒绝
    for bad in (None, 123, ["daily_cache"], object()):
        with pytest.raises(ValueError):
            StockFetcher._safe_ident(bad)


def test_init_cache_table_blocks_injection_and_keeps_db_intact():
    f = _bare_instance()
    conn = sqlite3.connect(":memory:")
    try:
        # 正常建表
        f._init_cache_table(conn, "daily_cache")
        conn.execute(
            "INSERT INTO daily_cache (cache_key, data_json, updated_at) VALUES (?,?,?)",
            ("k1", "{}", "2026-01-01"),
        )
        conn.commit()

        # 注入载荷必须被拒绝，且不能执行、不能破坏既有表
        for payload in EVIL_PAYLOADS:
            with pytest.raises(ValueError):
                f._init_cache_table(conn, payload)

        # 既有表与数据完好
        n = conn.execute("SELECT COUNT(*) FROM daily_cache").fetchone()[0]
        assert n == 1
    finally:
        conn.close()


def test_clear_cache_validates_table_name():
    """clear_cache 是公开方法，表名必须过校验后再拼进 DELETE。"""
    f = _bare_instance()
    # 不真正连库：只要校验在拼 SQL 之前发生，非法名必然抛 ValueError
    with pytest.raises(ValueError):
        f.clear_cache(table_name="daily_cache; DROP TABLE users--")
    with pytest.raises(ValueError):
        f.clear_cache(table_name="daily cache")


def test_all_hardcoded_table_names_are_valid():
    """源码中所有硬编码表名都必须通过校验（防将来新增表名被静默拦掉）。"""
    path = os.path.join(ROOT, "modules", "fetcher.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name not in ("_init_cache_table", "clear_cache"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append(arg.value)
        for kw in node.keywords:
            if kw.arg in ("table_name", "t") and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    found.append(kw.value.value)

    assert found, "未扫描到任何硬编码表名，疑似解析/路径有误"
    bad = [t for t in set(found) if not StockFetcher._SAFE_IDENT_RE.match(t)]
    assert not bad, f"fetcher.py 中存在不合法的表名字面量（会被校验拦掉）: {bad}"
