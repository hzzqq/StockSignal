"""widgets 纯助手函数回归测试（无网依赖）。

覆盖：
- password_strength / 新能力 password_checklist（结构化达标明细）
- get_session_remaining（JWT exp 解码；mock token）
- _index_market_status（委托 current_trading_session；TZ 一致性）
- 隐式 bug 修复：_trend_label 无冲高回落/探底回升结构时不再隐式返回 None
"""
import time

import jwt
import pytest

import modules.widgets as W


# ── 密码强度 ──────────────────────────────────────────────
def test_password_strength_empty():
    assert W.password_strength("") == (0, "空")


def test_password_strength_strong():
    score, level = W.password_strength("Abcdef1234!@")
    assert score == 4
    assert level == "很强"


def test_password_checklist_empty():
    c = W.password_checklist("")
    assert c["empty"] is True
    assert c["score"] == 0
    assert c["level"] == "空"


def test_password_checklist_strong():
    c = W.password_checklist("Abcdef1234!@")
    assert c["empty"] is False
    assert c["length8"] and c["length12"]
    assert c["mixed_case"] and c["digit_and_symbol"]
    assert c["score"] == 4


def test_password_checklist_weak():
    c = W.password_checklist("abc")
    assert c["empty"] is False
    assert c["length8"] is False
    assert c["mixed_case"] is False
    assert c["score"] == 0


# ── 会话剩余 ──────────────────────────────────────────────
def test_get_session_remaining_none_token(monkeypatch):
    monkeypatch.setattr(W, "get_token", lambda: None)
    assert W.get_session_remaining() is None


def test_get_session_remaining_valid(monkeypatch):
    token = jwt.encode({"exp": int(time.time()) + 3600}, "s", algorithm="HS256")
    monkeypatch.setattr(W, "get_token", lambda: token)
    remain = W.get_session_remaining()
    assert remain is not None
    assert 3500 <= remain <= 3600


def test_get_session_remaining_expired(monkeypatch):
    token = jwt.encode({"exp": int(time.time()) - 10}, "s", algorithm="HS256")
    monkeypatch.setattr(W, "get_token", lambda: token)
    assert W.get_session_remaining() == 0


# ── 指数市场状态（委托 current_trading_session）──────────
def test_index_market_status_delegation(monkeypatch):
    cases = {
        "weekend": (False, "⚪ 已休市（周末）", 0),
        "morning": (True, "🟢 交易中", 60 * 1000),
        "afternoon": (True, "🟢 交易中", 60 * 1000),
        "lunch": (False, "⚪ 已休市", 0),
        "pre_open": (False, "⚪ 已休市", 0),
        "after_close": (False, "⚪ 已休市", 0),
    }
    for sess, expected in cases.items():
        monkeypatch.setattr("modules.page_widgets.current_trading_session", lambda: sess)
        assert W._index_market_status() == expected


# ── 走势定性（隐式 None 修复）────────────────────────────
def test_trend_label_no_structure_returns_string():
    # 高低点距开盘均 <0.15%，但 high-low 振幅 ≥0.15% 的旧分支会隐式返回 None
    out = W._trend_label(10.0, 10.02, 9.99, 10.0, 10.0)
    assert isinstance(out, str)
    assert out != "None"


def test_trend_label_basic_cases():
    assert W._trend_label(10, 10.2, 9.8, 10.0, 10.0) in ("冲高回落", "探底回升",
                                                            "震荡上行", "震荡下行", "窄幅震荡")
    # 涨跌幅度过小
    assert W._trend_label(10, 10.01, 9.99, 10.0, 10.0) == "窄幅震荡"
    # 无效输入
    assert W._trend_label(0, 0, 0, 0, 0) == "—"
    assert W._trend_label(10, 10.2, 9.8, 10.5, 10.0,
                          spark_y=[10.0, 10.2, 10.1, 9.9, 10.5]) in (
        "冲高回落", "探底回升", "震荡上行", "震荡下行", "窄幅震荡")
