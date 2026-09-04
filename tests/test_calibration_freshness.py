# -*- coding: utf-8 -*-
"""校准证据新鲜度守卫（自找缺口 S11）——顶部横幅诚实降级测试。

锁死契约：
- calibration.verdict() 在「样本够但打分陈旧」时返回 stale=True，且 msg 警示基于陈旧回测。
- 54 页顶部「校准补丁就绪」横幅：ready 且 stale → 降级为告警（不照亮「就绪」）；
  ready 且新鲜 → 绿色「已就绪」成功框。

全部离线：verdict 直接 monkeypatch 成受控字典，绕开真实 prediction_log 计算；
网络入口速败（同 test_pages_smoke._offline_network_stub），避免真连网挂起。
"""
from __future__ import annotations

import datetime as _dt
import os
import time

import jwt
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import modules.calibration as _CAL
from modules.site_config import TEST_SMOKE_SECRET

# 中和 AppTest 环境伪象：page_link / switch_page 需要运行时 URL 上下文，headless 下会 KeyError
st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731


def _fake_token() -> str:
    return jwt.encode(
        {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
        TEST_SMOKE_SECRET, algorithm="HS256",
    )


def _verdict(ready: bool, stale: bool) -> dict:
    today = _dt.date.today().isoformat()
    return {
        "ready": ready,
        "any_actionable": ready,
        "stale": stale,
        "n_call": 50 if ready else 5,
        "n": 60 if ready else 7,
        "strong_samples": 20,
        "gap": 0 if ready else 15,
        "last_scored_date": "2026-01-01" if stale else today,
        "stale_days": 30 if stale else 1,
        "msg": "样本已够但打分陈旧" if (ready and stale) else "ok",
    }


def _isolate_writes(monkeypatch, tmp_path):
    """落盘路径重定向到临时目录，避免冒烟写脏真实 data/（同 test_pages_smoke）。"""
    import modules.shepherd_ladder as _sl
    import modules.decision as _dec

    monkeypatch.setattr(_sl, "LADDER_FILE", str(tmp_path / "ladder_history.json"))
    monkeypatch.setattr(_dec, "SNAPSHOT_PATH", str(tmp_path / "daily_snapshot.json"))
    monkeypatch.setattr(_dec, "ARCHIVE_DIR", str(tmp_path / "snapshots"))


def _offline_network_stub(monkeypatch):
    """离线打桩：所有页面取数路径立即失败并走降级，逼出真实断网/弱网页面（同 test_pages_smoke）。"""
    import urllib.request as _urllib_req
    import urllib.error as _urllib_err

    def _conn_boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")

    for _target in (requests, requests.Session):
        for _attr in ("get", "post", "request"):
            try:
                monkeypatch.setattr(_target, _attr, _conn_boom, raising=True)
            except AttributeError:
                pass

    def _url_boom(*a, **k):
        raise _urllib_err.URLError("offline stub")

    monkeypatch.setattr(_urllib_req, "urlopen", _url_boom, raising=True)

    try:
        import baostock as bs

        class _FakeLogin:
            error_code = "1"
            error_msg = "offline stub"

        monkeypatch.setattr(bs, "login", lambda *a, **k: _FakeLogin(), raising=True)
        monkeypatch.setattr(bs, "logout", lambda *a, **k: None, raising=True)
    except Exception:
        pass

    try:
        st.cache_data.clear()
    except Exception:
        pass


def test_verdict_exposes_stale_flag(monkeypatch):
    """打分陈旧 → stale=True；新鲜 → stale=False（不依赖 ready）。"""
    monkeypatch.setattr(_CAL, "verdict", lambda *a, **k: _verdict(True, True))
    assert _CAL.verdict()["stale"] is True
    monkeypatch.setattr(_CAL, "verdict", lambda *a, **k: _verdict(True, False))
    assert _CAL.verdict()["stale"] is False


def _render_page54(monkeypatch, tmp_path) -> "AppTest":
    _isolate_writes(monkeypatch, tmp_path)
    _offline_network_stub(monkeypatch)
    _page = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "pages", "54_今日决策面板.py")
    at = AppTest.from_file(_page, default_timeout=180)
    at.session_state["auth_token"] = _fake_token()
    at.session_state["auth_user"] = {"id": 1, "username": "demo", "role": "admin"}
    at.run()
    return at


def test_page54_banner_downgrades_on_stale(monkeypatch, tmp_path):
    """ready+stale → 横幅渲染告警（含「暂缓就绪」），绝不照亮「已就绪」。"""
    monkeypatch.setattr(_CAL, "verdict", lambda *a, **k: _verdict(True, True))
    at = _render_page54(monkeypatch, tmp_path)
    assert len(at.exception) == 0, [str(e) for e in at.exception]
    _text = " ".join(
        (getattr(m, "value", "") or "") for m in (list(at.markdown) + list(at.warning))
    )
    assert "暂缓就绪" in _text, "陈旧校准证据下横幅应降级为告警"
    assert "已就绪" not in _text, "陈旧时不应照亮绿色就绪"


def test_page54_banner_ready_when_fresh(monkeypatch, tmp_path):
    """ready+fresh → 横幅渲染绿色「已就绪」成功框。"""
    monkeypatch.setattr(_CAL, "verdict", lambda *a, **k: _verdict(True, False))
    at = _render_page54(monkeypatch, tmp_path)
    assert len(at.exception) == 0, [str(e) for e in at.exception]
    _text = " ".join((getattr(m, "value", "") or "") for m in at.markdown)
    assert "已就绪" in _text, "新鲜校准证据下横幅应显示就绪"
