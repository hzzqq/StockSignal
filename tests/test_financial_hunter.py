"""G10 财报猎手守卫：信号分级/筛选纯逻辑 + 页面渲染/离线降级。"""
from __future__ import annotations

import os

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

from modules.financial_hunter import annotate, scan, signal_of

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(_PROJECT_ROOT, "pages", "77_财报猎手.py")


def test_signal_of_mapping():
    assert signal_of("预增") == "利好"
    assert signal_of("扭亏") == "利好"
    assert signal_of("略增") == "偏多"
    assert signal_of("预减") == "利空"
    assert signal_of("首亏") == "利空"
    assert signal_of("不确定") == "中性"
    assert signal_of(None) == "中性"


def _fake_yjyg():
    return pd.DataFrame([
        ["600000", "甲公司", "预增", 120.0, "主营增长", "2026-07-10"],
        ["600001", "乙公司", "扭亏", 300.0, "降本增效", "2026-07-11"],
        ["600002", "丙公司", "预减", -60.0, "需求下滑", "2026-07-12"],
        ["600003", "丁公司", "略增", 15.0, "订单增加", "2026-07-13"],
    ], columns=["股票代码", "股票简称", "预告类型", "业绩变动幅度", "业绩变动原因", "公告日期"])


def test_annotate_and_scan():
    d = annotate(_fake_yjyg())
    assert list(d["_signal"]) == ["利好", "利好", "利空", "偏多"]
    assert d["_pct"].iloc[1] == 300.0
    hit = scan(_fake_yjyg(), min_pct=100.0, signals=["利好"])
    assert len(hit) == 2
    assert list(hit["_pct"]) == [300.0, 120.0], "应按变动幅度降序"


def test_scan_empty():
    assert scan(pd.DataFrame()).empty


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
def test_fh_page_renders_with_fake_data(authed, monkeypatch):
    import modules.fundflow as ff
    monkeypatch.setattr(ff, "get_earnings_forecast", lambda *a, **k: _fake_yjyg(), raising=True)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"财报猎手页渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_fh_page_offline_graceful(authed, monkeypatch):
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"离线应优雅降级而非崩溃: {[str(e) for e in at.exception]}"
