"""G7 题材热点守卫：生命周期/换手分位纯逻辑 + 页面渲染/离线降级。"""
from __future__ import annotations

import os

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

from modules.theme_heat import lifecycle_label, turnover_pct

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(_PROJECT_ROOT, "pages", "75_题材热点.py")


def test_lifecycle_label_rules():
    assert lifecycle_label(5.0, 90.0) == "高潮"
    assert lifecycle_label(2.0, 50.0) == "发酵"
    assert lifecycle_label(-2.0, 70.0) == "退潮"
    assert lifecycle_label(0.5, 20.0) == "平淡"
    assert lifecycle_label(None, 50.0) == "未知"
    assert lifecycle_label(float("nan"), 50.0) == "未知"


def test_turnover_pct_range():
    df = pd.DataFrame({"换手率": [1.0, 2.0, 3.0, 4.0]})
    p = turnover_pct(df)
    assert p.min() > 0 and p.max() == 100.0


def _fake_loaded():
    d = pd.DataFrame([
        ["AI算力", 5.2, 1e11, 4.0, "龙头A"],
        ["白酒", -1.5, 5e11, 1.2, "龙头B"],
        ["光伏", 2.0, 8e10, 3.5, "龙头C"],
    ], columns=["板块名称", "涨跌幅", "总市值", "换手率", "领涨股票"])
    d["_chg"] = d["涨跌幅"]
    d["_turnover_p"] = [90.0, 20.0, 60.0]
    d["_life"] = ["高潮", "平淡", "退潮"]
    return d


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
def test_theme_heat_renders_with_fake_data(authed, monkeypatch):
    import modules.theme_heat as th
    monkeypatch.setattr(th, "load_concepts", lambda: _fake_loaded(), raising=True)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"题材热点页渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_theme_heat_offline_graceful(authed, monkeypatch):
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"离线应优雅降级而非崩溃: {[str(e) for e in at.exception]}"
