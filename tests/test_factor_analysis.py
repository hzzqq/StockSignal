"""G3 因子分析守卫：纯函数契约 + 页面渲染 + 离线降级。

纯函数覆盖：rank_ic（完全正/负相关、小样本）、ic_summary、layered_returns（单调性）、
long_short、build_panels（标的不足不出结论）。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

from modules.factor_analysis import (
    build_panels, ic_series, ic_summary, layered_returns, long_short, rank_ic,
)

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(_PROJECT_ROOT, "pages", "71_因子分析.py")


# ── 纯函数契约 ─────────────────────────────────────────────────────────
def test_rank_ic_perfect_positive():
    s = pd.Series([1, 2, 3, 4, 5], dtype="float64")
    assert abs(rank_ic(s, s) - 1.0) < 1e-9


def test_rank_ic_perfect_negative():
    a = pd.Series([1, 2, 3, 4, 5], dtype="float64")
    b = pd.Series([5, 4, 3, 2, 1], dtype="float64")
    assert abs(rank_ic(a, b) + 1.0) < 1e-9


def test_rank_ic_small_sample_is_nan():
    a = pd.Series([1.0, 2.0])
    assert np.isnan(rank_ic(a, a))


def test_ic_series_and_summary_shapes():
    dates = pd.date_range("2026-01-01", periods=15)
    cols = list("ABCDE")
    f = pd.DataFrame({c: np.arange(15) + i for i, c in enumerate(cols)}, index=dates)
    r = pd.DataFrame({c: np.arange(15) * 0.01 + i for i, c in enumerate(cols)}, index=dates)
    ic = ic_series(f, r, forward=1)
    assert len(ic) == 14
    summ = ic_summary(ic)
    assert summ["n"] == 14 and -1.0 <= summ["ic_mean"] <= 1.0


def test_layered_returns_monotonic_and_long_short():
    dates = pd.date_range("2026-01-01", periods=20)
    cols = list("ABCD")
    # 因子值各列恒定 1/2/3/4，收益各列恒定 0.01/0.02/0.03/0.04 → 完美单调
    f = pd.DataFrame({c: np.full(20, i + 1.0) for i, c in enumerate(cols)}, index=dates)
    r = pd.DataFrame({c: np.full(20, (i + 1) * 0.01) for i, c in enumerate(cols)}, index=dates)
    lay = layered_returns(f, r, n_layers=4, forward=1)
    assert not lay.empty
    last = lay.iloc[-1]
    assert last[sorted(last.index)[-1]] > last[sorted(last.index)[0]], "分层应单调"
    ls = long_short(lay)
    assert (ls > 0).all(), "多空应恒正"


def test_build_panels_insufficient_returns_none():
    def _fetch(code):
        return pd.DataFrame({"日期": pd.date_range("2026-01-01", periods=40),
                             "收盘": np.arange(40) + 1.0})
    fp, ret, errs = build_panels(["a", "b"], 40, "momentum", _fetch)  # 仅 2 只
    assert fp is None and ret is None


def test_build_panels_with_fake_fetcher():
    def _fetch(code):
        return pd.DataFrame({"日期": pd.date_range("2026-01-01", periods=60),
                             "收盘": np.linspace(10, 20, 60) + hash(code) % 5,
                             "换手率": np.linspace(1, 3, 60)})
    fp, ret, errs = build_panels(["a", "b", "c", "d"], 60, "momentum", _fetch)
    assert fp is not None and not fp.empty
    assert set(fp.columns) == {"a", "b", "c", "d"}


# ── 页面运行时 ─────────────────────────────────────────────────────────
def _fake_panels():
    dates = pd.date_range("2026-01-01", periods=25)
    cols = list("ABCDE")
    f = pd.DataFrame({c: np.arange(25) * 0.01 + i for i, c in enumerate(cols)}, index=dates)
    r = pd.DataFrame({c: np.sin(np.arange(25) / 5 + i) * 0.02 for i, c in enumerate(cols)}, index=dates)
    return f, r, []


def _offline_stub(monkeypatch):
    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")
    for tgt in (requests, requests.Session):
        for attr in ("get", "post", "request"):
            try:
                monkeypatch.setattr(tgt, attr, _boom, raising=True)
            except AttributeError:
                pass


def _auth_session(at):
    from modules.site_config import TEST_SMOKE_SECRET
    import jwt, time
    tok = jwt.encode(
        {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
        TEST_SMOKE_SECRET, algorithm="HS256",
    )
    at.session_state["auth_token"] = tok
    at.session_state["auth_user"] = {"id": 1, "username": "demo", "role": "admin"}


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_factor_page_renders_with_fake_data(authed, monkeypatch):
    import modules.factor_analysis as fa
    monkeypatch.setattr(fa, "build_panels", lambda *a, **k: _fake_panels(), raising=True)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=180)
    if authed:
        _auth_session(at)
    at.run()
    if authed:
        at.button[0].click().run()
    assert not at.exception, f"因子分析页渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_factor_page_offline_graceful(authed, monkeypatch):
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=180)
    if authed:
        _auth_session(at)
    at.run()
    if authed:
        at.button[0].click().run()
    assert not at.exception, f"离线应优雅降级而非崩溃: {[str(e) for e in at.exception]}"
