"""Cycle 31 回归：fetcher 缓存读取容错（json 损坏不再炸调用方）。

修复前：get_cached / get_all_stocks 的缓存命中路径直接 `json.loads(row[0])`，
缓存数据一旦损坏（磁盘写半截 / 版本变更）即抛 JSONDecodeError 冒泡到调用方，
导致整个依赖该缓存的函数崩溃。修复后统一走 `_safe_json_loads`，损坏降级为 default。
"""
import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import fetcher


def test_valid_json():
    assert fetcher._safe_json_loads('{"a":1}') == {"a": 1}
    assert fetcher._safe_json_loads('[1,2,3]') == [1, 2, 3]


def test_corrupt_json_returns_default():
    assert fetcher._safe_json_loads('{bad json') is None
    assert fetcher._safe_json_loads('not json!!!') is None


def test_empty_and_none():
    assert fetcher._safe_json_loads('') is None
    assert fetcher._safe_json_loads(None) is None


def test_explicit_default():
    assert fetcher._safe_json_loads('xxx', default={}) == {}
    assert fetcher._safe_json_loads(None, default=[]) == []


def test_non_string_returns_default():
    assert fetcher._safe_json_loads(123) is None
    assert fetcher._safe_json_loads(b'{"a":1}') is None  # bytes 非 str


def test_read_cache_corrupt_json_degrades_to_none():
    """端到端：缓存库里写入损坏 JSON，_read_cache 应降级返回 None 而非崩溃。"""
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "cache.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS daily_cache "
        "(cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT INTO daily_cache VALUES (?,?,?)",
        ("sh600519_daily", "{corrupt", "2026-01-01T00:00:00"),
    )
    conn.commit()

    inst = fetcher.StockFetcher()
    result = inst._read_cache(
        conn, "daily_cache", "sh600519_daily",
        max_age_hours=99999, as_dataframe=False,
    )
    assert result is None  # 损坏 -> 降级为 None，而非抛异常
    conn.close()
