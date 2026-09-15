"""页面 73《自定义看板 / 工作区》(G5) 渲染回归测试。

- test_pages_smoke 只保证「导入不炸」，抓不到模块渲染函数里的 NameError/KeyError。
- 本测试注入假数据逼出各模块的渲染路径；另一态**不注入**，验证取数失败时
  逐模块诚实降级（「未就绪」）而非整页崩溃——这正是「诚实降级」红线的守卫。
"""
from __future__ import annotations

import os

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(_PROJECT_ROOT, "pages", "73_自定义看板.py")

_FAKE_DAYS = ["20260915", "20260912", "20260911"]


def _fake_snap():
    return {"cycle": "主升", "temperature": 60.0, "position": 55.0, "date": "20260915"}


def _fake_ladder():
    return {"distribution": [(3, 1), (2, 2), (1, 5)], "total_connect": 3, "max_boards": 3}


def _fake_ind_df():
    return pd.DataFrame([
        {"date": d, "zt_fail_ratio": 28.0, "limit_up": 40, "median_chg": 0.8 + i * 0.1}
        for i, d in enumerate(_FAKE_DAYS)
    ])


def _fake_regime():
    return {"available": True, "latest": {"state": "主升", "confidence": 0.8}}


def _offline_stub(monkeypatch):
    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")
    for tgt in (requests, requests.Session):
        for attr in ("get", "post", "request"):
            try:
                monkeypatch.setattr(tgt, attr, _boom, raising=True)
            except AttributeError:
                pass


def _patch_sources(monkeypatch):
    import modules.shepherd as _sh
    import modules.market_regime as _mr
    monkeypatch.setattr(_sh, "load_latest_snapshot", lambda: _fake_snap(), raising=True)
    monkeypatch.setattr(_sh, "_trading_days", lambda n: list(_FAKE_DAYS[:n]), raising=True)
    monkeypatch.setattr(_sh, "get_zt_ladder", lambda *a, **k: _fake_ladder(), raising=True)
    monkeypatch.setattr(_sh, "get_shepherd_indicators", lambda *a, **k: (_fake_ind_df(), {}), raising=True)
    monkeypatch.setattr(_mr, "regime_report", lambda *a, **k: _fake_regime(), raising=True)


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
def test_dashboard_renders_with_fake_data(authed, monkeypatch):
    _patch_sources(monkeypatch)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"自定义看板渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_dashboard_offline_graceful(authed, monkeypatch):
    """不注入假数据：各模块取数失败须逐模块降级，整页不得抛未捕获异常。"""
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"离线应逐模块降级而非崩溃: {[str(e) for e in at.exception]}"
