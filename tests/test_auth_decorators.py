"""
tests/test_auth_decorators.py
==============================
JWT / 角色校验装饰器（backend.auth.decorators）测试。

用 Flask test_request_context 提供 request，monkeypatch decode_token 与 User，
覆盖：Bearer 提取的各类非法输入、jwt_required 正常/失效 token/停用用户、
admin_required 越权与放行。
"""
import flask
import pytest
from jwt import PyJWTError

import backend.auth.decorators as dec
from backend.utils.errors import AuthError, ForbiddenError


class FakeUser:
    def __init__(self, username="u", role="user", is_active=True):
        self.username = username
        self.role = role
        self.is_active = is_active


class FakeQuery:
    def __init__(self, user):
        self._user = user

    def filter_by(self, **kw):
        return self

    def first(self):
        return self._user


@pytest.fixture
def app():
    a = flask.Flask(__name__)
    a.config["SECRET_KEY"] = "test-secret"
    return a


# ── _extract_bearer_token ────────────────────────────────
def test_extract_missing_header(app):
    with app.test_request_context():
        with pytest.raises(AuthError):
            dec._extract_bearer_token()


def test_extract_empty_bearer(app):
    with app.test_request_context(headers={"Authorization": "Bearer "}):
        with pytest.raises(AuthError):
            dec._extract_bearer_token()


def test_extract_wrong_scheme(app):
    with app.test_request_context(headers={"Authorization": "Basic abc"}):
        with pytest.raises(AuthError):
            dec._extract_bearer_token()


def test_extract_valid_trims_whitespace(app):
    with app.test_request_context(headers={"Authorization": "Bearer  tok123 "}):
        assert dec._extract_bearer_token() == "tok123"


# ── jwt_required ─────────────────────────────────────────
def test_jwt_required_valid(app, monkeypatch):
    monkeypatch.setattr(dec, "decode_token", lambda t: {"sub": "u"})
    monkeypatch.setattr(dec, "User", FakeUser)
    FakeUser.query = FakeQuery(FakeUser(username="u", role="user", is_active=True))
    captured = {}

    @dec.jwt_required
    def view():
        captured["user"] = flask.g.current_user
        return "ok"

    with app.test_request_context(headers={"Authorization": "Bearer x"}):
        assert view() == "ok"
        assert captured["user"].username == "u"


def test_jwt_required_invalid_token(app, monkeypatch):
    def boom(t):
        raise PyJWTError("bad")

    monkeypatch.setattr(dec, "decode_token", boom)

    @dec.jwt_required
    def view():
        return "ok"

    with app.test_request_context(headers={"Authorization": "Bearer x"}):
        with pytest.raises(AuthError):
            view()


def test_jwt_required_inactive_user(app, monkeypatch):
    monkeypatch.setattr(dec, "decode_token", lambda t: {"sub": "u"})
    monkeypatch.setattr(dec, "User", FakeUser)
    FakeUser.query = FakeQuery(FakeUser(username="u", is_active=False))

    @dec.jwt_required
    def view():
        return "ok"

    with app.test_request_context(headers={"Authorization": "Bearer x"}):
        with pytest.raises(AuthError):
            view()


# ── admin_required ───────────────────────────────────────
def test_admin_required_forbidden_for_normal_user(app, monkeypatch):
    monkeypatch.setattr(dec, "decode_token", lambda t: {"sub": "u"})
    monkeypatch.setattr(dec, "User", FakeUser)
    FakeUser.query = FakeQuery(FakeUser(username="u", role="user"))

    @dec.admin_required
    def view():
        return "admin"

    with app.test_request_context(headers={"Authorization": "Bearer x"}):
        with pytest.raises(ForbiddenError):
            view()


def test_admin_required_ok(app, monkeypatch):
    monkeypatch.setattr(dec, "decode_token", lambda t: {"sub": "u"})
    monkeypatch.setattr(dec, "User", FakeUser)
    FakeUser.query = FakeQuery(FakeUser(username="u", role="admin"))

    @dec.admin_required
    def view():
        return "admin"

    with app.test_request_context(headers={"Authorization": "Bearer x"}):
        assert view() == "admin"
