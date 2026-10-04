# -*- coding: utf-8 -*-
"""tests/test_prov_badge.py — H1+ 方向 A「数据来源徽标」基元守卫。

覆盖 spec AC-A2（诚实语义）/ AC-A3（无 rerun）/ AC-A4（风格变量）/ AC-A5（零破坏）。
全部离线：需要取数的用例把 data_health.assess_all_sources 换成假结果。
"""
from __future__ import annotations

import inspect

from modules import data_health, ui_kit as uk


# ───────────── AC-A3 无 rerun（纯前端）─────────────

def test_badge_uses_no_rerun():
    """AC-A3：徽标为纯前端 <details>，基元内不得出现 st.rerun。"""
    src = inspect.getsource(uk.prov_badge) + inspect.getsource(uk._prov_badge_html)
    assert "st.rerun" not in src and ".rerun(" not in src
    assert "<details" in inspect.getsource(uk._prov_badge_html)


# ───────────── AC-A4 风格自适应（变量驱动）─────────────

def test_css_variable_driven():
    """AC-A4：徽标 CSS 全走主题变量（--ss-*），随六风格自适应。"""
    assert ".ss-prov" in uk._KIT_CSS
    seg = uk._KIT_CSS[uk._KIT_CSS.index(".ss-prov"):]
    seg = seg[:seg.index("</style>")]
    assert "var(--ss-" in seg, "徽标样式必须走主题变量"


# ───────────── AC-A2 诚实语义 ─────────────

def test_unknown_shown_honestly_not_ok():
    """AC-A2：无数据日的源显示「未取到/未知」，绝不显示为「正常」。"""
    h = uk._prov_badge_html([{"key": "k", "name": "源X", "as_of": None,
                              "lag_days": None, "status": "unknown", "is_fallback": None}])
    assert "未知" in h and "未取到" in h
    assert "正常" not in h


def test_stale_flagged_in_header():
    """AC-A2：含偏旧/陈旧源 → 摘要处显式警示。"""
    h = uk._prov_badge_html([{"key": "k", "name": "源X", "as_of": "2026-09-20",
                              "lag_days": 14, "status": "stale", "is_fallback": None}])
    assert "陈旧" in h and "⚠️" in h and "滞后 14 天" in h


def test_fallback_source_marked():
    """AC-A2：回退源显式标记（is_fallback=True）。"""
    h = uk._prov_badge_html([{"key": "k", "name": "源Y", "as_of": "2026-10-01",
                              "lag_days": 1, "status": "ok", "is_fallback": True}])
    assert "回退源" in h


# ───────────── AC-A5 零破坏 + 安全 ─────────────

def test_empty_rows_is_noop_html():
    assert uk._prov_badge_html([]) == ""
    assert uk._prov_badge_html(None) == ""


def test_unmapped_slug_renders_nothing(monkeypatch):
    """AC-A5：未登记页面 → 不渲染任何内容（零破坏）。"""
    cap: list = []
    monkeypatch.setattr(uk.st, "markdown", lambda *a, **k: cap.append(a))
    uk.prov_badge(slug="__no_such_page__")
    assert cap == []


def test_mapped_slug_renders(monkeypatch):
    """已登记页面 → 渲染徽标（复用 data_provenance → data_health）。"""
    monkeypatch.setattr(data_health, "assess_all_sources", lambda: {
        "status": "ok", "max_lag_days": 0,
        "sources": {"牧羊人情绪": {"as_of": "2026-10-04", "lag_days": 0, "status": "ok"}},
    })
    cap: list = []
    monkeypatch.setattr(uk.st, "markdown", lambda s, **k: cap.append(s))
    uk.prov_badge(slug="54_今日决策面板")
    assert cap and "ss-prov" in cap[-1]


def test_escapes_hostile_text():
    """安全：源名/as_of 为外部数据，必须转义（防注入）。"""
    h = uk._prov_badge_html([{"key": "k", "name": "<script>alert(1)</script>",
                              "as_of": "<b>x</b>", "lag_days": 0,
                              "status": "ok", "is_fallback": None}])
    assert "<script>" not in h and "&lt;script&gt;" in h
    assert "<b>x</b>" not in h
