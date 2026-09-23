"""
T-158 前端静默续期守卫：token 过期不再直接踢出，先试 POST /api/auth/refresh。

【契约】
  1. is_authenticated()：exp 过期 → _try_refresh()
     - 续期成功（200 + 新 token + user）→ 三层存储更新（session_state/URL/localStorage）
       且返回 True，用户无感；
     - 后端明确拒绝（401：超窗/禁用/伪造）→ 清登录态返回 False（原踢出语义）；
     - 网络瞬态（异常/5xx）→ 保留登录态返回 True（与「token 校验网络异常不踢」
       既有语义一致——后端不可达时踢人只会放大故障）。
  2. _verify_token()：401 且 body.code == "token_expired" → 返回 _TOKEN_EXPIRED
     哨兵（可续期）；其余 401/403 → _TOKEN_INVALID（不可续期）。
  3. _restore_from_query_params()：恢复登录态遇过期 → 续期成功即完成恢复。

纯函数部分（_verify_token）直测；涉及 st.session_state 的行为用 AppTest 桩页面。
"""
from __future__ import annotations

import os
import sys
import time

import jwt as pyjwt
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import session as sess  # noqa: E402

PROBE = os.path.join(os.path.dirname(__file__), "_stubs", "refresh_probe.py")

NEW_TOKEN = "new.token.value"
USER = {"username": "alice", "uid": 1, "role": "user"}


def _expired_token(minutes_ago: int = 10) -> str:
    """签名随意（前端不验签）但 exp 真实过期、iat 在 7 天窗口内的 JWT。"""
    now = int(time.time())
    return pyjwt.encode(
        {"sub": "alice", "uid": 1, "exp": now - minutes_ago * 60, "iat": now - 3600},
        "any", algorithm="HS256",
    )


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


# ───────────────────────── _verify_token 哨兵区分 ─────────────────────────
def test_verify_token_maps_expired_code(monkeypatch):
    """401 + code=token_expired → _TOKEN_EXPIRED（可续期），不得混入 INVALID。"""
    monkeypatch.setattr(sess, "http_get", lambda *a, **k: _Resp(
        401, {"status": "error", "code": "token_expired"}))
    assert sess._verify_token("t") is sess._TOKEN_EXPIRED


def test_verify_token_maps_other_401_invalid(monkeypatch):
    monkeypatch.setattr(sess, "http_get", lambda *a, **k: _Resp(
        401, {"status": "error", "code": "invalid_token"}))
    assert sess._verify_token("t") is sess._TOKEN_INVALID


def test_verify_token_non_json_401_is_invalid(monkeypatch):
    """401 body 无 code（旧后端/代理兜底页）→ 保守按 INVALID。"""
    monkeypatch.setattr(sess, "http_get", lambda *a, **k: _Resp(401, {}))
    assert sess._verify_token("t") is sess._TOKEN_INVALID


# ───────────────────────── is_authenticated 静默续期 ─────────────────────────
def test_expired_token_refreshes_silently(monkeypatch):
    """过期 token + refresh 成功 → True，且新 token 写回 session_state/URL。"""
    monkeypatch.setattr(sess, "http_post", lambda *a, **k: _Resp(
        200, {"status": "ok", "data": {"token": NEW_TOKEN, "user": USER}}))
    at = AppTest.from_file(PROBE)
    at.session_state[sess.KEY_TOKEN] = _expired_token()
    at.run()
    # 真断言：token 已被换新（三层中的两层：session_state 与 URL）
    assert at.session_state[sess.KEY_TOKEN] == NEW_TOKEN
    assert at.query_params.get("token") == [NEW_TOKEN]


def test_expired_token_rejected_then_cleared(monkeypatch):
    """后端明确拒绝续期（超窗）→ 清登录态（原踢出语义保留）。"""
    monkeypatch.setattr(sess, "http_post", lambda *a, **k: _Resp(
        401, {"status": "error", "code": "token_expired"}))
    at = AppTest.from_file(PROBE)
    at.session_state[sess.KEY_TOKEN] = _expired_token()
    at.run()
    assert not at.session_state[sess.KEY_TOKEN]
    assert not at.session_state[sess.KEY_USER]


def test_expired_token_network_failure_kept(monkeypatch):
    """后端不可达（网络瞬态）→ 不踢，保留现有登录态待后端恢复。"""
    def _boom(*a, **k):
        raise ConnectionError("backend down")
    monkeypatch.setattr(sess, "http_post", _boom)
    at = AppTest.from_file(PROBE)
    tok = _expired_token()
    at.session_state[sess.KEY_TOKEN] = tok
    at.run()
    assert at.session_state[sess.KEY_TOKEN] == tok


def test_valid_token_no_refresh_call(monkeypatch):
    """未过期的 token 不应触发 refresh 请求（省一次往返）。"""
    called = []

    def _spy(*a, **k):
        called.append(1)
        return _Resp(200, {"status": "ok", "data": {"token": NEW_TOKEN, "user": USER}})

    monkeypatch.setattr(sess, "http_post", _spy)
    now = int(time.time())
    valid = pyjwt.encode({"sub": "alice", "exp": now + 3600, "iat": now}, "any",
                         algorithm="HS256")
    at = AppTest.from_file(PROBE)
    at.session_state[sess.KEY_TOKEN] = valid
    at.run()
    assert called == [], "有效 token 不应发起续期请求"
