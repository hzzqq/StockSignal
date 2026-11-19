# -*- coding: utf-8 -*-
"""行业实体映射层离线确定性测试（零真实网络、绝不改 sectors 原表）。"""
import json
import logging
import sqlite3
import sys
import types

import pytest

from modules import sector_map as sm
from modules import sector_map_fetch as fetcher


def _make_probe_db(path):
    """造一个含 sectors 精编表（1 行半导体）的隔离库，模拟真实 data/news.db。"""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE sectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            keywords TEXT NOT NULL,
            stock_codes TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute(
        "INSERT INTO sectors (name, keywords, stock_codes, description) "
        "VALUES (?, ?, ?, ?)",
        ("半导体", "人工精编关键词-" * 25,
         ",".join(f"{i:06d}" for i in range(1, 80)), "人工精编"),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "news.db"
    monkeypatch.setenv("SECTOR_MAP_DB_PATH", str(path))
    _make_probe_db(path)
    sm.init_table()
    return path


def _sectors_rows(path):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT name, keywords, stock_codes FROM sectors").fetchall()
    finally:
        conn.close()


def _fake_resp(payload):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _Resp()


# ── 建表 / 写入 ────────────────────────────────────────────────────────────

def test_01_init_table_idempotent(db):
    sm.init_table()
    sm.init_table()
    conn = sqlite3.connect(str(db))
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='sector_entity_map'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_02_upsert_idempotent(db):
    assert sm.upsert_sector({"board_name": "证券", "member_count": 3,
                             "fetch_status": "ok"}) is True
    assert sm.upsert_sector({"board_name": "证券", "member_count": 5,
                             "fetch_status": "ok"}) is True
    rows = sm.list_sectors()
    assert len(rows) == 1
    assert rows[0]["member_count"] == 5


def test_03_unique_name_and_type(db):
    assert sm.upsert_sector({"board_name": "军工", "board_type": "industry"}) is True
    assert sm.upsert_sector({"board_name": "军工", "board_type": "concept"}) is True
    assert len(sm.list_sectors()) == 2


def test_04_upsert_missing_name_returns_false(db):
    assert sm.upsert_sector({"keywords": "无名称"}) is False
    assert sm.list_sectors() == []


# ── resolve 优先级 ─────────────────────────────────────────────────────────

def test_05_resolve_manual_first(db):
    r = sm.resolve_sector("半导体")
    assert r is not None
    assert r["source"] == "manual"
    assert "人工精编" in r["keywords"]


def test_06_resolve_falls_back_to_map(db):
    sm.upsert_sector({"board_name": "光伏"})
    r = sm.resolve_sector("光伏")
    assert r is not None
    assert r["source"] == "rule_l1"
    assert "太阳能" in r["keywords"]


def test_07_resolve_missing_returns_none(db):
    assert sm.resolve_sector("根本不存在的行业") is None


def test_08_resolve_manual_wins_over_map(db):
    sm.upsert_sector({"board_name": "半导体", "member_count": 9, "fetch_status": "ok"})
    assert sm.resolve_sector("半导体")["source"] == "manual"


# ── keywords 诚实分级 ──────────────────────────────────────────────────────

def test_09_build_keywords_l1():
    kw, source = sm.build_keywords("半导体")
    assert "芯片" in kw
    assert "集成电路" in kw
    assert source == "rule_l1"


def test_10_build_keywords_l0():
    kw, source = sm.build_keywords("冷门行业XYZ")
    assert kw == "冷门行业XYZ"
    assert source == "rule_l0"


# ── 清单抓取（假 akshare） ────────────────────────────────────────────────

def test_11_fetch_names_from_ths(monkeypatch):
    import pandas as pd

    names = [f"测试行业{i}" for i in range(90)]
    fake_ak = types.ModuleType("akshare")
    fake_ak.stock_board_industry_summary_ths = lambda: pd.DataFrame({"板块": names})
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    out = fetcher.fetch_industry_names()
    assert len(out) == 90
    assert out[0]["source"] == "ths"
    assert out[0]["name"] == "测试行业0"


def test_12_fetch_names_fallback_filters_concepts(monkeypatch):
    import pandas as pd

    fake_ak = types.ModuleType("akshare")

    def _boom():
        raise RuntimeError("THS 不可达")
    fake_ak.stock_board_industry_summary_ths = _boom
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    def _fake_json(url):
        if "pn=1" in url:
            return {"data": {"diff": [
                {"f12": "BK0001", "f14": "酿酒概念"},
                {"f12": "BK0002", "f14": "算力租赁"},
                {"f12": "BK0003", "f14": "证券"},
            ]}}
        return {"data": {"diff": []}}
    monkeypatch.setattr(fetcher, "_http_get_json", _fake_json)

    out = fetcher.fetch_industry_names()
    assert [i["name"] for i in out] == ["证券"]
    assert out[0]["source"] == "em"
    assert out[0]["code"] == "BK0003"


# ── 成分股抓取（假 urllib） ───────────────────────────────────────────────

def test_13_fetch_members_success(monkeypatch):
    payload = {"data": {"diff": [
        {"f12": "1", "f14": "平安银行"},
        {"f12": "600519", "f14": "贵州茅台"},
    ]}}
    monkeypatch.setattr(fetcher, "_urlopen", lambda url, timeout=15: _fake_resp(payload))
    out = fetcher.fetch_members("BK0425", delay=0, retries=1)
    assert out == [
        {"code": "000001", "name": "平安银行"},
        {"code": "600519", "name": "贵州茅台"},
    ]


def test_14_fetch_members_failure_returns_empty_and_logs(monkeypatch, caplog):
    def _boom(url, timeout=15):
        raise OSError("boom")
    monkeypatch.setattr(fetcher, "_urlopen", _boom)
    with caplog.at_level(logging.WARNING):
        out = fetcher.fetch_members("BK0001", delay=0, retries=2)
    assert out == []
    assert "BK0001" in caplog.text


def test_15_fetch_members_empty_diff_is_failure(monkeypatch, caplog):
    monkeypatch.setattr(fetcher, "_urlopen",
                        lambda url, timeout=15: _fake_resp({"data": {"diff": []}}))
    with caplog.at_level(logging.WARNING):
        out = fetcher.fetch_members("BK0001", delay=0, retries=1)
    assert out == []
    assert "BK0001" in caplog.text


def test_16_fetch_members_exponential_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: sleeps.append(s))

    def _boom(url, timeout=15):
        raise OSError("boom")
    monkeypatch.setattr(fetcher, "_urlopen", _boom)
    fetcher.fetch_members("BK0001", delay=1.5, retries=3)
    assert sleeps == [1.5, 3.0]


# ── refresh 统计 / resume / 诚实 ──────────────────────────────────────────

def _patch_refresh(monkeypatch, names, codes, member_fn):
    monkeypatch.setattr(fetcher, "fetch_industry_names",
                        lambda: [{"name": n, "source": "ths"} for n in names])
    monkeypatch.setattr(fetcher, "_fetch_em_board_index",
                        lambda **kw: dict(codes))
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)
    calls = []

    def _members(code, *, delay=1.5, retries=3):
        calls.append(code)
        return member_fn(code)
    monkeypatch.setattr(fetcher, "fetch_members", _members)
    return calls


def test_17_refresh_partial_success_and_failure(db, monkeypatch):
    calls = _patch_refresh(
        monkeypatch,
        ["甲", "乙", "丙"],
        {"甲": "BK0001", "乙": "BK0002", "丙": "BK0003"},
        lambda code: [] if code == "BK0002" else [{"code": "000001", "name": "样本"}],
    )
    out = fetcher.refresh_sector_map(limit=3, resume=False)
    assert out["ok"] == 2
    assert out["failed"] == 1
    assert out["total"] == 3
    rows = {r["board_name"]: r for r in sm.list_sectors()}
    assert rows["乙"]["fetch_status"] == "failed"
    assert rows["乙"]["stock_codes"] == ""
    assert rows["乙"]["member_count"] == 0
    assert rows["甲"]["fetch_status"] == "ok"
    assert len(calls) == 3


def test_18_resume_only_refetches_failed(db, monkeypatch):
    _patch_refresh(
        monkeypatch,
        ["甲", "乙", "丙"],
        {"甲": "BK0001", "乙": "BK0002", "丙": "BK0003"},
        lambda code: [] if code == "BK0002" else [{"code": "000001", "name": "样本"}],
    )
    fetcher.refresh_sector_map(limit=3, resume=False)

    calls = []
    monkeypatch.setattr(fetcher, "fetch_members",
                        lambda code, *, delay=1.5, retries=3: (
                            calls.append(code) or [{"code": "000002", "name": "补抓"}]
                        ))
    out = fetcher.refresh_sector_map(limit=3, resume=True)
    assert calls == ["BK0002"]
    assert out["skipped"] >= 2
    assert out["ok"] == 1
    assert sm.resolve_sector("乙")["fetch_status"] == "ok"


def test_19_no_ok_row_with_zero_members(db, monkeypatch):
    _patch_refresh(
        monkeypatch,
        ["甲", "乙"],
        {"甲": "BK0001", "乙": "BK0002"},
        lambda code: [] if code == "BK0002" else [{"code": "000001", "name": "样本"}],
    )
    fetcher.refresh_sector_map(limit=2, resume=False)
    for r in sm.list_sectors():
        assert not (r["fetch_status"] == "ok" and r["member_count"] == 0)
        if r["member_count"] == 0 and r["stock_codes"] == "":
            assert r["fetch_status"] == "failed"


def test_20_missing_board_code_marks_failed(db, monkeypatch):
    _patch_refresh(monkeypatch, ["无代码行业"], {}, lambda code: [])
    out = fetcher.refresh_sector_map(limit=1, resume=False)
    assert out["failed"] == 1
    assert sm.list_sectors()[0]["fetch_status"] == "failed"


# ── 红线：不改 sectors / 不补 0 / 不泄漏连接 ──────────────────────────────

def test_21_sectors_table_never_touched(db, monkeypatch):
    before = _sectors_rows(db)
    assert len(before) == 1
    sm.upsert_sector({"board_name": "半导体", "member_count": 3})
    sm.mark_failed("半导体")
    _patch_refresh(monkeypatch, ["半导体"], {"半导体": "BK0001"},
                   lambda code: [{"code": "000001", "name": "样本"}])
    fetcher.refresh_sector_map(limit=1, resume=False)
    assert _sectors_rows(db) == before


def test_22_no_or_zero_fallback_in_source():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("modules/sector_map.py", "modules/sector_map_fetch.py"):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            assert "or 0" not in f.read(), f"{rel} 出现 or 0 补零反模式"


def test_23_repeated_calls_do_not_lock_db(db):
    for _ in range(20):
        sm.init_table()
        sm.list_sectors()
        sm.sector_map_stats()
        sm.resolve_sector("半导体")
        sm.mark_failed("临时行业")
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM sector_entity_map").fetchone()[0] >= 1
    finally:
        conn.close()


def test_24_stats_shape(db):
    sm.upsert_sector({"board_name": "甲", "fetch_status": "ok", "member_count": 2})
    sm.mark_failed("乙")
    s = sm.sector_map_stats()
    assert s["total"] == 2
    assert s["ok"] == 1
    assert s["failed"] == 1
    assert s["manual_sectors"] == 1
