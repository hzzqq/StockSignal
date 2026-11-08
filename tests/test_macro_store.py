# -*- coding: utf-8 -*-
"""宏观历史入库（modules/macro_store.py + macro_data 库优先）守卫。

2026-11-08 改造要点：
- 宏观指标此前**完全不落盘**（每次现取现用）→ 宏观页首屏 3~8s，
  且事件因子的宏观分无法复现（历史回测不可归因）。
- 改造后：`fetch_indicator` **库优先**（TTL 内零网络），miss 才取数并回写。

本文件锁以下不变量：
1. `macro_store` 读写往返 + 缺失返 None（不返回空 dict 冒充成功）。
2. TTL 按指标频率判定；`fetched_at` 解析失败一律判过期（宁可重取不吃坏数据）。
3. `fetch_indicator` 库优先命中时**零网络**（monkeypatch 掉 akshare 仍能返值）。
4. 库未命中 → 走网络取数并**回写库**（下次可命中）。
5. 日期归一化：`2026年10月份` / `2026年第1季度` / `2026年第1-3季度`（累计季度）
   → 统一 ISO；无法解析 → None（不编造）。
6. 取数失败 → 返回 None，**不写库**（不污染出无值行）。
7. 诚实红线：`value`/`prev` 缺失 → None，绝不补 0。
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import macro_store  # noqa: E402
from modules.macro_data import _normalize_macro_date  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_macro_db(tmp_path, monkeypatch):
    """每个用例用独立的宏观库文件，避免污染真实 data/macro_history.db。

    同时**显式打开**库优先开关（tests/conftest.py 默认关闭它，
    以免既有「取数逻辑」单测读到真实库的值）。
    """
    db = tmp_path / "macro_test.db"
    monkeypatch.setenv("MACRO_DB_PATH", str(db))
    monkeypatch.setenv("MACRO_STORE_ENABLED", "1")
    macro_store.init_macro_db()
    yield str(db)


# ── 1. 读写往返与缺失语义 ───────────────────────────────────────────────────

def test_write_and_read_latest_roundtrip():
    ok = macro_store.write_macro_point("usd_cnh", "2026-11-06", 6.6738, 6.6652, "东财")
    assert ok is True
    row = macro_store.read_macro_latest("usd_cnh")
    assert row is not None
    assert row["key"] == "usd_cnh"
    assert row["date"] == "2026-11-06"
    assert abs(row["value"] - 6.6738) < 1e-9
    assert abs(row["prev"] - 6.6652) < 1e-9
    assert row["source"] == "东财"
    assert row["fetched_at"]  # 抓取时间与数据日期分离


def test_read_latest_missing_returns_none():
    """缺失必须返回 None —— 不能返回空 dict 冒充成功。"""
    assert macro_store.read_macro_latest("not_exist_key") is None


def test_write_without_date_returns_false():
    """无日期不写行（避免污染出无日期脏数据）。"""
    assert macro_store.write_macro_point("k", "", 1.0, None, "s") is False
    assert macro_store.write_macro_point("k", None, 1.0, None, "s") is False


def test_write_with_all_none_values_returns_false():
    """value 与 prev 都缺 → 无有效观测，不写。"""
    assert macro_store.write_macro_point("k", "2026-01-01", None, None, "s") is False


def test_nan_value_treated_as_none():
    """NaN 必须视为缺失（绝不写 NaN 进库）。"""
    assert macro_store.write_macro_point("k", "2026-01-01", float("nan"), None, "s") is False


def test_read_series_sorted_and_filterable():
    macro_store.write_macro_point("s", "2026-01-01", 1.0)
    macro_store.write_macro_point("s", "2026-03-01", 3.0)
    macro_store.write_macro_point("s", "2026-02-01", 2.0)
    series = macro_store.read_macro_series("s")
    assert [r["date"] for r in series] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    # 区间过滤
    part = macro_store.read_macro_series("s", start="2026-02-01")
    assert [r["date"] for r in part] == ["2026-02-01", "2026-03-01"]


def test_write_series_counts_and_skips_bad_points():
    n = macro_store.write_macro_series(
        "s",
        [
            {"date": "2026-01-01", "value": 1.0},
            {"date": "", "value": 2.0},          # 无日期 → 跳过
            {"date": "2026-02-01", "value": None},  # 无值 → 跳过
            {"not_dict": 1},                      # 非法 → 跳过
        ],
        source="s",
    )
    assert n == 1


def test_same_key_date_overwrites_not_duplicates():
    macro_store.write_macro_point("k", "2026-01-01", 1.0)
    macro_store.write_macro_point("k", "2026-01-01", 2.0)
    series = macro_store.read_macro_series("k")
    assert len(series) == 1
    assert series[0]["value"] == 2.0


# ── 2. TTL 判定 ─────────────────────────────────────────────────────────────

def test_ttl_uses_indicator_frequency():
    """日频 TTL 最短、月频最长（按指标自身发布节奏，不统一硬编码）。"""
    assert macro_store.ttl_for("usd_cnh") == macro_store.TTL_DAILY
    assert macro_store.ttl_for("pmi") == macro_store.TTL_MONTHLY
    assert macro_store.ttl_for("fed_funds_rate") == macro_store.TTL_QUARTERLY
    # 未登记指标 → 日频（最保守，最常刷新）
    assert macro_store.ttl_for("unknown_key") == macro_store.TTL_DAILY


def test_is_fresh_within_and_out_of_ttl():
    from datetime import datetime, timedelta
    now = datetime.now()
    assert macro_store.is_fresh("usd_cnh", (now - timedelta(hours=2)).isoformat()) is True
    assert macro_store.is_fresh("usd_cnh", (now - timedelta(days=3)).isoformat()) is False


def test_is_fresh_bad_timestamp_is_false():
    """fetched_at 解析失败 → 判过期（宁可重取，不吃坏数据）。"""
    assert macro_store.is_fresh("usd_cnh", "not-a-date") is False
    assert macro_store.is_fresh("usd_cnh", "") is False


# ── 3~4. fetch_indicator 库优先 + 回写 ──────────────────────────────────────

def _patch_akshare(monkeypatch, payload):
    """把 akshare 换成只提供指定 fn 的假实现。"""
    import akshare as ak

    class _Fake:
        def __getattr__(self, name):
            if name == payload["fn"]:
                def _fn(*_a, **_k):
                    if payload.get("raise"):
                        raise RuntimeError("boom")
                    return payload["df"]
                return _fn
            raise AttributeError(name)

    monkeypatch.setattr(ak, "__dict__", {})
    monkeypatch.setitem(ak.__dict__, payload["fn"], payload["df"])


def test_fetch_indicator_uses_cache_without_network(monkeypatch):
    """库命中且 TTL 内 → 零网络返回（monkeypatch 掉 akshare 仍能返值）。"""
    macro_store.write_macro_point("pmi", "2026-10-01", 53.0, 52.5, "国家统计局")

    def _boom(*_a, **_k):
        raise AssertionError("库命中时不应发起网络请求")

    monkeypatch.setattr("modules.macro_data._fetch_via", _boom)

    from modules.macro_data import fetch_indicator
    r = fetch_indicator("pmi")
    assert r is not None
    assert r["value"] == 53.0
    assert r["prev"] == 52.5
    assert r["date"] == "2026-10-01"
    assert r["from_cache"] is True
    assert r["stale"] is False
    assert r["change"] == 0.5


def test_fetch_indicator_miss_fetches_and_persists(monkeypatch):
    """库未命中 → 走取数并**回写库**（下次可命中）。"""
    import pandas as pd

    df = pd.DataFrame([
        {"月份": "2026年09月份", "制造业-指数": 52.0},
        {"月份": "2026年10月份", "制造业-指数": 53.0},
    ])

    calls = {"n": 0}

    def _fake_fetch_via(spec, key, fn_name, args, parse):
        calls["n"] += 1
        return {
            "key": key, "name": spec["name"], "unit": spec["unit"], "freq": spec["freq"],
            "source": spec["source"], "region": spec.get("region", "国内"),
            "desc": spec["desc"], "value": 53.0, "prev": 52.0, "change": 1.0,
            "date": "2026-10-01",
        }

    monkeypatch.setattr("modules.macro_data._fetch_via", _fake_fetch_via)

    from modules.macro_data import fetch_indicator
    r = fetch_indicator("pmi")
    assert r is not None
    assert calls["n"] == 1
    assert r["from_cache"] is False
    # 已回写库
    row = macro_store.read_macro_latest("pmi")
    assert row is not None
    assert row["date"] == "2026-10-01"
    assert row["value"] == 53.0


def test_fetch_indicator_failure_returns_none_and_does_not_write(monkeypatch):
    """取数失败 → None 且**不写库**（不污染出无值行）。"""
    def _fail(spec, key, fn_name, args, parse):
        return None

    monkeypatch.setattr("modules.macro_data._fetch_via", _fail)

    from modules.macro_data import fetch_indicator
    assert fetch_indicator("pmi") is None
    assert macro_store.read_macro_latest("pmi") is None


def test_fetch_indicator_expired_cache_refetches(monkeypatch):
    """库有数据但已过 TTL → 走网络重取，不拿过期值冒充最新。"""
    # 写入一个很旧的 fetched_at（手工改库）
    macro_store.write_macro_point("usd_cnh", "2020-01-01", 6.9)
    import sqlite3
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(days=30)).isoformat()
    conn = sqlite3.connect(os.environ["MACRO_DB_PATH"])
    with conn:
        conn.execute("UPDATE macro_history SET fetched_at=? WHERE key=?", (old, "usd_cnh"))
    conn.close()

    def _fake_fetch_via(spec, key, fn_name, args, parse):
        return {
            "key": key, "name": spec["name"], "unit": spec["unit"], "freq": spec["freq"],
            "source": spec["source"], "region": spec.get("region", "国内"),
            "desc": spec["desc"], "value": 6.67, "prev": 6.66, "change": 0.01,
            "date": "2026-11-06",
        }

    monkeypatch.setattr("modules.macro_data._fetch_via", _fake_fetch_via)
    from modules.macro_data import fetch_indicator
    r = fetch_indicator("usd_cnh")
    assert r is not None
    assert r["date"] == "2026-11-06"   # 用了新取的值，不是库里旧的 2020-01-01
    assert r["from_cache"] is False


def test_fetch_indicator_unknown_key_returns_none():
    from modules.macro_data import fetch_indicator
    assert fetch_indicator("__no_such_indicator__") is None


# ── 5. 日期归一化 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("2026-11-06", "2026-11-06"),
    ("2026/11/06", "2026-11-06"),
    ("2026-11-06 00:00:00", "2026-11-06"),
    ("2026年10月份", "2026-10-01"),
    ("2026年第1季度", "2026-01-01"),
    ("2026年第3季度", "2026-07-01"),
    ("2026年第1-3季度", "2026-07-01"),   # 累计季度 → 归一到区间末季首月
    ("2026年第1-2季度", "2026-04-01"),
    ("2026-11", "2026-11-01"),
])
def test_normalize_macro_date(raw, expected):
    assert _normalize_macro_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "not-a-date", "无数据"])
def test_normalize_macro_date_unparseable_returns_none(raw):
    """无法解析 → None（不编造日期）。"""
    assert _normalize_macro_date(raw) is None


def test_normalize_macro_date_accepts_datetime():
    from datetime import date
    assert _normalize_macro_date(date(2026, 11, 6)) == "2026-11-06"
