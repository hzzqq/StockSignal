# -*- coding: utf-8 -*-
"""tests/test_data_provenance.py — H1+ 方向 A「全站来源底账」守卫。

覆盖 spec AC-A1（单一真理源）/ AC-A2（诚实语义）/ AC-A5（零破坏）。
全部离线：autouse 夹具把 `data_health.assess_all_sources` 换成确定性假结果，不读盘。
"""
from __future__ import annotations

import ast
import inspect

import pytest

from modules import data_health, data_provenance as dp

_FAKE = {
    "status": "warn",
    "max_lag_days": 5,
    "sources": {
        "牧羊人情绪": {"as_of": "2026-09-30", "lag_days": 5, "status": "warn"},
        "市场温度缓存": {"as_of": None, "lag_days": None, "status": "unknown"},
    },
}


@pytest.fixture(autouse=True)
def _fake_health(monkeypatch):
    """离线确定性：默认把单一真理源换成假结果（不读盘/不联网）。"""
    monkeypatch.setattr(data_health, "assess_all_sources", lambda: _FAKE)


# ───────────── AC-A1 单一真理源 ─────────────

def test_no_redeclared_thresholds_and_reuses_data_health():
    """AC-A1：不得重定义新鲜度阈值；必须复用 data_health.assess_all_sources。"""
    src = inspect.getsource(dp)
    tree = ast.parse(src)
    # 不得「赋值重定义」FRESH_* 阈值常量（仅文档提及不算）
    assigned: set[str] = set()
    for n in ast.walk(tree):
        targets = n.targets if isinstance(n, ast.Assign) else (
            [n.target] if isinstance(n, ast.AnnAssign) else [])
        for t in targets:
            if isinstance(t, ast.Name):
                assigned.add(t.id)
    assert not any(a.startswith("FRESH_") for a in assigned), \
        f"不得重定义新鲜度阈值常量：{[a for a in assigned if a.startswith('FRESH_')]}"
    # 必须复用 data_health（单一真理源）
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "assess_all_sources" in attrs, "必须复用 data_health.assess_all_sources（单一真理源）"
    # 不得出现 `lag >= <数字>` 之类的自造数值阈值比较（仅有序比较 + 数值常量才算阈值）
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and any(
                isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE)) for op in n.ops):
            for c in n.comparators:
                assert not (isinstance(c, ast.Constant)
                            and isinstance(c.value, (int, float))
                            and not isinstance(c.value, bool)), \
                    f"不得自造数值阈值比较（行 {getattr(n,'lineno','?')}）"


def test_build_provenance_follows_data_health(monkeypatch):
    """AC-A1：底账字段必须原样来自 data_health（证明单一真理源，而非另算）。"""
    monkeypatch.setattr(data_health, "assess_all_sources", lambda: {
        "status": "stale", "max_lag_days": 9,
        "sources": {"牧羊人情绪": {"as_of": "2026-09-25", "lag_days": 9, "status": "stale"}},
    })
    r = dp.build_provenance(["shepherd_sentiment"])[0]
    assert r["as_of"] == "2026-09-25" and r["lag_days"] == 9 and r["status"] == "stale"
    assert r["name"] == "牧羊人情绪"


# ───────────── AC-A2 诚实语义 ─────────────

def test_unknown_key_is_honest_not_fabricated():
    """AC-A2：未知源 key → as_of/lag 均 None、status=unknown，绝不臆造。"""
    r = dp.build_provenance(["__no_such_source__"])[0]
    assert r["as_of"] is None and r["lag_days"] is None and r["status"] == "unknown"


def test_missing_as_of_stays_unknown():
    """AC-A2：源无数据日 → unknown（不得默认 0/当天）。"""
    r = dp.build_provenance(["market_temp"])[0]
    assert r["status"] == "unknown" and r["as_of"] is None


def test_includes_passthrough_defaults_none():
    """AC-A2：链路/回退仅由调用方确知时传入；缺省 None（不编造链路）。"""
    r0 = dp.build_provenance(["market_temp"])[0]
    assert r0["is_fallback"] is None and r0["source_chain"] is None
    r1 = dp.build_provenance(
        ["market_temp"],
        includes={"market_temp": {"is_fallback": True,
                                  "source_chain": ["ems", "akshare", "qq"]}})[0]
    assert r1["is_fallback"] is True and r1["source_chain"] == ["ems", "akshare", "qq"]


# ───────────── AC-A5 零破坏 ─────────────

def test_sources_for_unmapped_is_empty():
    """AC-A5：未登记页面 → []（调用方据此 no-op）；已登记页非空。"""
    assert dp.sources_for("__no_such_page__") == []
    assert dp.sources_for("54_今日决策面板"), "已登记页应有依赖源"


def test_all_page_source_keys_exist():
    """AC-A5：登记映射引用的 key 必须都在 data_health 注册表内（防拼写漂移）。"""
    valid = set(dp.source_keys())
    for slug, keys in dp.PAGE_SOURCES.items():
        unknown = [k for k in keys if k not in valid]
        assert not unknown, f"{slug} 引用了未注册源 {unknown}"


# ───────────── summary ─────────────

def test_summary_worst_and_flags():
    rows = [{"key": "a", "status": "ok", "is_fallback": False},
            {"key": "b", "status": "stale", "is_fallback": True},
            {"key": "c", "status": "unknown", "is_fallback": None}]
    s = dp.summary(rows)
    assert s["status"] == "stale" and s["has_fallback"] is True and s["has_stale"] is True
    assert s["n"] == 3 and s["n_unknown"] == 1 and "b" in s["worst_keys"]
