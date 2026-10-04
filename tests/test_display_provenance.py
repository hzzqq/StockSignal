# -*- coding: utf-8 -*-
"""tests/test_display_provenance.py — T-215 独立展示溯源通道守卫。

覆盖：单一评分真理源（assess_freshness，零阈值常量）/ 诚实语义（无内容日期→unknown）/
注册表只收「有离线证据」的源（强势榜·财务不登记）/ 零破坏（未登记页 no-op）。
全部离线：不触网；用 tmp SQLite 造展示缓存。
"""
from __future__ import annotations

import ast
import inspect
import json
import sqlite3

import pytest

from modules import display_provenance as dp


# ───────────── 单一真理源（零阈值常量） ─────────────

def test_no_redeclared_thresholds_and_reuses_assess_freshness():
    src = inspect.getsource(dp)
    tree = ast.parse(src)
    assigned: set[str] = set()
    for n in ast.walk(tree):
        targets = n.targets if isinstance(n, ast.Assign) else (
            [n.target] if isinstance(n, ast.AnnAssign) else [])
        for t in targets:
            if isinstance(t, ast.Name):
                assigned.add(t.id)
    assert not any(a.startswith("FRESH_") for a in assigned), \
        f"不得重定义新鲜度阈值常量：{[a for a in assigned if a.startswith('FRESH_')]}"
    called = any(
        isinstance(n, ast.Call) and (
            (isinstance(n.func, ast.Name) and n.func.id == "assess_freshness")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "assess_freshness"))
        for n in ast.walk(tree))
    assert called, "必须调用 decision.assess_freshness（单一评分真理源）"
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and any(
                isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq))
                for op in n.ops):
            for c in n.comparators:
                assert not (isinstance(c, ast.Constant)
                            and isinstance(c.value, (int, float))
                            and not isinstance(c.value, bool)), \
                    f"不得自造数值阈值比较（行 {getattr(n, 'lineno', '?')}）"


def test_build_follows_assess_freshness(monkeypatch, tmp_path):
    monkeypatch.setattr(dp, "_CACHE_DB", str(tmp_path / "none.db"))  # 不读真实 cache.db
    monkeypatch.setattr(dp, "assess_freshness", lambda as_ofs: {
        "status": "stale", "max_lag_days": 9,
        "sources": {"指数行情缓存": {"as_of": "2026-09-25", "lag_days": 9, "status": "stale"}},
    })
    r = dp.build_display_provenance(["index_quote"])[0]
    assert r["as_of"] == "2026-09-25" and r["lag_days"] == 9 and r["status"] == "stale"
    assert r["name"] == "指数行情缓存"


# ───────────── 诚实语义 ─────────────

def test_unknown_key_is_honest_not_fabricated():
    r = dp.build_display_provenance(["__no_such_display_source__"])[0]
    assert r["as_of"] is None and r["lag_days"] is None and r["status"] == "unknown"


def test_missing_db_is_unknown_not_mtime(tmp_path, monkeypatch):
    """缺库 → unknown（刻意不用 mtime 兜底，避免共享 cache.db 假新鲜）。"""
    monkeypatch.setattr(dp, "_CACHE_DB", str(tmp_path / "nope.db"))
    r = dp.build_display_provenance(["index_quote"])[0]
    assert r["status"] == "unknown" and r["as_of"] is None


def test_empty_table_is_unknown_not_mtime(tmp_path, monkeypatch):
    """表存在但无记录 → unknown（不得退回 mtime 谎报新鲜）。"""
    db = tmp_path / "cache.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE index_cache (cache_key TEXT, data_json TEXT, updated_at TEXT)")
    monkeypatch.setattr(dp, "_CACHE_DB", str(db))
    assert dp.build_display_provenance(["index_quote"])[0]["status"] == "unknown"


def test_reads_content_date_index_records(tmp_path, monkeypatch):
    db = tmp_path / "cache.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE index_cache (cache_key TEXT, data_json TEXT, updated_at TEXT)")
        c.execute("INSERT INTO index_cache VALUES (?,?,?)", (
            "index_000001_x",
            json.dumps([{"date": "2026-09-01T00:00:00.000"},
                        {"date": "2026-09-03T00:00:00.000"}]), "t"))
    monkeypatch.setattr(dp, "_CACHE_DB", str(db))
    r = dp.build_display_provenance(["index_quote"])[0]
    assert r["as_of"] == "2026-09-03"


def test_reads_content_date_realtime_field(tmp_path, monkeypatch):
    db = tmp_path / "cache.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE rt_quote_cache (cache_key TEXT, data_json TEXT, updated_at TEXT)")
        c.execute("INSERT INTO rt_quote_cache VALUES (?,?,?)", (
            "rt_quote_601088",
            json.dumps({"ticker": "601088", "datetime": "2026-09-09 13:30:20"}), "t"))
    monkeypatch.setattr(dp, "_CACHE_DB", str(db))
    r = dp.build_display_provenance(["realtime_quote"])[0]
    assert r["as_of"] == "2026-09-09"


def test_bad_identifier_not_in_sql(tmp_path, monkeypatch):
    db = tmp_path / "cache.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE index_cache (cache_key TEXT, data_json TEXT, updated_at TEXT)")
    monkeypatch.setattr(dp, "_CACHE_DB", str(db))
    assert dp._sqlite_json_max_date(str(db), "t; DROP TABLE x") is None


# ───────────── 注册表诚实（宁缺毋滥） ─────────────

def test_no_evidence_sources_not_registered():
    """强势榜 / 个股财务**零落盘无离线 as_of** → 刻意不登记（防硬造 mtime 误导）。"""
    keys = " ".join(dp.source_keys()).lower()
    for bad in ("spot", "strong", "financial", "fundamental", "强势", "财务"):
        assert bad not in keys, f"不应登记无离线证据的展示源：{bad}"


def test_page_sources_subset_of_registry():
    valid = set(dp.source_keys())
    for slug, keys in dp.DISPLAY_PAGE_SOURCES.items():
        unknown = [k for k in keys if k not in valid]
        assert not unknown, f"{slug} 引用了未注册展示源 {unknown}"


def test_sources_for_unmapped_is_empty():
    assert dp.sources_for("__no_such_page__") == []
    assert dp.sources_for("10_行情看板")
