"""G4 六维评分守卫：纯函数契约 + 解析 + 页面渲染/离线降级。"""
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

from modules.six_dim import (
    clamp_score, compose, compute_dims, parse_fin, score_capital, score_cycle,
    score_fundamental, score_growth, score_technical, score_value,
)

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(_PROJECT_ROOT, "pages", "72_六维评分.py")


def test_clamp_score_basic_and_missing():
    assert clamp_score(5, 0, 10) == 50.0
    assert clamp_score(-100, 0, 10) == 0.0
    assert clamp_score(100, 0, 10) == 100.0
    assert clamp_score(None, 0, 10) is None
    assert clamp_score(float("nan"), 0, 10) is None
    # hi<lo：越小越好
    assert clamp_score(8, 80, 8) == 100.0
    assert clamp_score(80, 80, 8) == 0.0


def test_score_technical_uptrend_beats_downtrend():
    up = pd.Series(np.linspace(10, 20, 80))
    down = pd.Series(np.linspace(20, 10, 80))
    assert score_technical(up) > score_technical(down)


def test_score_technical_insufficient_data():
    assert score_technical(pd.Series([1.0, 2.0, 3.0])) is None


def test_score_value_negative_pe_is_missing():
    assert score_value(-5.0, 1.2) is not None  # PB 有效 → 仍有分
    assert score_value(-5.0, None) is None     # 全缺失 → None
    assert score_value(10.0, 1.0) > score_value(60.0, 6.0)


def test_score_capital_growth_fundamental_cycle():
    assert 0 <= score_capital(3.0, 1.5) <= 100
    assert score_growth(50) > score_growth(0) > score_growth(-20)
    assert score_fundamental(18) > score_fundamental(2)
    assert score_cycle("主升", 10) > score_cycle("退潮", -10)


def test_compose_renormalizes_and_none_when_empty():
    r = compose({"technical": 80, "capital": None, "value": 60,
                 "growth": None, "fundamental": None, "cycle": None})
    assert r["coverage"] == 2
    assert abs(r["overall"] - 70.0) < 1e-6
    assert compose({k: None for k in
                    ["technical", "capital", "value", "growth", "fundamental", "cycle"]})["overall"] is None


def test_parse_fin_extracts_roe_and_yoy():
    fin = pd.DataFrame({
        "选项": ["指标", "指标"],
        "指标": ["净资产收益率", "归母净利润同比增长率"],
        "2025-12-31": ["15.2", "23.5"],
        "2024-12-31": ["14.0", "20.0"],
    })
    roe, yoy = parse_fin(fin)
    assert abs(roe - 15.2) < 1e-6
    assert abs(yoy - 23.5) < 1e-6
    assert parse_fin(None) == (None, None)


def test_compute_dims_with_fake_fetchers():
    hist = pd.DataFrame({"收盘": np.linspace(10, 20, 80)})
    spot = {"换手率": 3.0, "量比": 1.5, "市盈率-动态": 15.0, "市净率": 1.5}
    fin = pd.DataFrame({"选项": ["指标", "指标"], "指标": ["净资产收益率", "归母净利润同比增长率"],
                        "2025-12-31": ["18.0", "25.0"]})
    result, raw = compute_dims("600519", lambda c: hist, lambda c: spot, lambda c: fin,
                               lambda: "主升")
    assert result["coverage"] == 6
    assert result["overall"] is not None
    assert raw["state"] == "主升"


# ── 页面运行时 ─────────────────────────────────────────────────────────
def _fake_result():
    dims = {"technical": 80.0, "capital": 60.0, "value": 50.0,
            "growth": 70.0, "fundamental": 65.0, "cycle": 55.0}
    return compose(dims), {"pe": 10, "pb": 1.2, "roe": 15, "profit_yoy": 20,
                           "state": "主升", "turnover": 2, "vol_ratio": 1.5, "pos60": 5.0}


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
def test_six_dim_page_renders_with_fake_data(authed, monkeypatch):
    import modules.six_dim as sd
    monkeypatch.setattr(sd, "compute_dims", lambda *a, **k: _fake_result(), raising=True)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=180)
    if authed:
        _auth_session(at)
    at.run()
    if authed:
        at.button[0].click().run()
    assert not at.exception, f"六维评分页渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_six_dim_page_offline_graceful(authed, monkeypatch):
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=180)
    if authed:
        _auth_session(at)
    at.run()
    if authed:
        at.button[0].click().run()
    assert not at.exception, f"离线应优雅降级而非崩溃: {[str(e) for e in at.exception]}"
