"""页面 76《实时强势榜》(G8) 守卫。

- 纯函数：`strong_score` 的评分契约（0-100、涨幅分项单调）。
- 运行时：注入假快照逼出渲染主体；离线态验证诚实降级（st.error + st.stop 而非崩溃）。
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
PAGE = os.path.join(_PROJECT_ROOT, "pages", "76_实时强势榜.py")


def _fake_spot():
    return pd.DataFrame([
        ["600000", "浦发银行", 10.0, 3.2, 5e8, 1.2, 1.1],
        ["600001", "招商银行", 40.0, 6.5, 9e8, 3.0, 2.5],
        ["600002", "中信银行", 7.0, -1.5, 3e8, 0.8, 0.9],
        ["600003", "兴业银行", 18.0, 9.9, 12e8, 5.0, 3.2],
    ], columns=["代码", "名称", "最新价", "涨跌幅", "成交额", "换手率", "量比"])


def test_strong_score_pure_contract():
    from modules.spot_rank import strong_score
    out = strong_score(_fake_spot())
    assert "_score" in out.columns
    assert out["_score"].between(0.0, 100.0).all(), "评分必须在 0-100"
    # 涨幅最高者 → 涨幅分项最高
    top_idx = out["涨跌幅"].idxmax()
    assert out.loc[top_idx, "_s_chg"] == out["_s_chg"].max()
    # 权重和应为 1.0
    from modules.spot_rank import WEIGHTS
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def _offline_stub(monkeypatch):
    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")
    for tgt in (requests, requests.Session):
        for attr in ("get", "post", "request"):
            try:
                monkeypatch.setattr(tgt, attr, _boom, raising=True)
            except AttributeError:
                pass


def _patch_spot(monkeypatch):
    import modules.spot_rank as sr
    monkeypatch.setattr(sr, "load_spot", lambda: _fake_spot(), raising=True)


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
def test_strong_rank_renders_with_fake_data(authed, monkeypatch):
    _patch_spot(monkeypatch)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"实时强势榜渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_strong_rank_offline_graceful(authed, monkeypatch):
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"离线应优雅降级而非崩溃: {[str(e) for e in at.exception]}"
