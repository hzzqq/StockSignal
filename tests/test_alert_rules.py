"""G6 告警引擎守卫：规则三值逻辑 + 持久化 + 页面渲染/离线降级。"""
from __future__ import annotations

import os

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

from modules.alert_rules import (
    channel_status, evaluate_all, evaluate_condition, evaluate_rule, load_rules, save_rules,
)

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(_PROJECT_ROOT, "pages", "74_告警引擎.py")


def test_evaluate_condition_ops():
    snap = {"x": 50.0}
    assert evaluate_condition({"metric": "x", "op": "gt", "value": 40}, snap) is True
    assert evaluate_condition({"metric": "x", "op": "lt", "value": 40}, snap) is False
    assert evaluate_condition({"metric": "x", "op": "eq", "value": 50}, snap) is True


def test_condition_missing_metric_is_unknown():
    assert evaluate_condition({"metric": "nope", "op": "gt", "value": 1}, {"x": 1}) is None
    assert evaluate_condition({"metric": "x", "op": "bad", "value": 1}, {"x": 1}) is None


def test_and_with_unknown_does_not_trigger():
    rule = {"logic": "AND", "conditions": [
        {"metric": "x", "op": "gt", "value": 1},
        {"metric": "missing", "op": "gt", "value": 1},
    ]}
    trig, detail = evaluate_rule(rule, {"x": 5})
    assert trig is False, "AND 遇未知条件不得触发（宁漏勿误）"
    assert len(detail["unknown"]) == 1


def test_or_triggers_on_any_known_true():
    rule = {"logic": "OR", "conditions": [
        {"metric": "x", "op": "gt", "value": 1},
        {"metric": "missing", "op": "gt", "value": 1},
    ]}
    trig, _ = evaluate_rule(rule, {"x": 5})
    assert trig is True


def test_and_all_true_triggers():
    rule = {"logic": "AND", "conditions": [
        {"metric": "x", "op": "gt", "value": 1},
        {"metric": "y", "op": "lt", "value": 10},
    ]}
    trig, _ = evaluate_rule(rule, {"x": 5, "y": 3})
    assert trig is True


def test_evaluate_all_shape():
    rules = [{"id": "a", "name": "A", "logic": "AND",
              "conditions": [{"metric": "x", "op": "gt", "value": 1}]}]
    out = evaluate_all(rules, {"x": 2})
    assert out[0]["triggered"] is True and "detail" in out[0]


def test_load_save_rules_roundtrip(tmp_path):
    p = str(tmp_path / "rules.json")
    rules = [{"id": "z", "name": "Z", "logic": "OR",
              "conditions": [{"metric": "m", "op": "gt", "value": 0}]}]
    assert save_rules(rules, p) is True
    assert load_rules(p) == rules


def test_channel_status_keys():
    cs = channel_status()
    assert set(cs) == {"log", "wecom", "feishu"}
    assert cs["log"][1] is True, "日志通道默认可用"


def _offline_stub(monkeypatch):
    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")
    for tgt in (requests, requests.Session):
        for attr in ("get", "post", "request"):
            try:
                monkeypatch.setattr(tgt, attr, _boom, raising=True)
            except AttributeError:
                pass


def _patch_snapshot(monkeypatch):
    import pandas as pd
    import modules.shepherd as _sh
    import modules.market_regime as _mr
    df = pd.DataFrame([{"zt_fail_ratio": 45.0, "limit_up": 90, "limit_down": 3, "median_chg": -0.5}])
    monkeypatch.setattr(_sh, "get_shepherd_indicators", lambda *a, **k: (df, {}), raising=True)
    monkeypatch.setattr(_sh, "load_latest_snapshot", lambda: {"temperature": 12.0, "cycle": "冰点"}, raising=True)
    monkeypatch.setattr(_mr, "regime_report", lambda *a, **k: {"available": True, "latest": {"state": "冰点", "confidence": 0.7}}, raising=True)


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
def test_alert_page_renders_with_snapshot(authed, monkeypatch):
    _patch_snapshot(monkeypatch)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"告警引擎页渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_alert_page_offline_graceful(authed, monkeypatch, tmp_path):
    # 隔离规则文件，避免污染真实 data/
    import modules.alert_rules as ar
    monkeypatch.setattr(ar, "_RULES_PATH", str(tmp_path / "rules.json"), raising=False)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"离线应优雅降级而非崩溃: {[str(e) for e in at.exception]}"
