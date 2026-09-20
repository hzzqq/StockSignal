# -*- coding: utf-8 -*-
"""backend/tests/test_auth_hardening.py — T-144 评估报告三实锤缺陷的修复守卫。

1. 登录审计：/api/auth/logins 曾恒空（登录成功从未写 OperationLog action='login'）；
2. CORS 默认收紧：默认 origins='*' → 必须默认收敛到本机前后端来源（env 可覆盖）；
3. SECRET_KEY 弱默认：兜底 'dev-only-change-me-in-production' → 未设 env 时必须
   首启生成随机密钥并持久化复用（每机唯一、重启稳定、可伪造风险消除）。
"""
from __future__ import annotations

import importlib
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "backend"))
_PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

import pytest  # noqa: E402

from backend.app import create_app   # noqa: E402
from backend.config import Config    # noqa: E402
from backend.extensions import db    # noqa: E402
from backend.models import User      # noqa: E402


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'audit.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        for uname, role in (("admin", "admin"), ("demo", "user")):
            if User.query.filter_by(username=uname).first() is None:
                u = User(username=uname, role=role)
                u.set_password("Pass@123")
                db.session.add(u)
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username="demo"):
    r = client.post("/api/auth/login", json={"username": username, "password": "Pass@123"})
    assert r.status_code == 200, r.text[:200]
    return r.get_json()["data"]["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_writes_audit_and_logins_endpoint_returns_it(app, client):
    """缺陷①：登录成功必须落 OperationLog(action='login')，/api/auth/logins 不得恒空。"""
    token = _login(client, "demo")
    r = client.get("/api/auth/logins?limit=10", headers=_hdr(token))
    assert r.status_code == 200, r.text[:200]
    rows = r.get_json(force=True).get("data") or []
    assert rows, "登录后 /api/auth/logins 仍为空（登录审计未落库）"
    assert rows[0]["action"] == "login"
    assert rows[0]["username"] == "demo"


def test_cors_default_not_wildcard(monkeypatch):
    """缺陷②：默认 CORS_ORIGINS 不得为 '*'，须默认收敛到本机前后端来源（env 仍可覆盖）。"""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    import backend.config as cfg_mod
    cfg = importlib.reload(cfg_mod).Config
    origins = str(cfg.CORS_ORIGINS)
    assert "*" not in origins, f"CORS 默认仍含通配符: {origins!r}"
    assert "localhost:8899" in origins and "localhost:5050" in origins or "8501" in origins, (
        f"CORS 默认应包含本机前端来源: {origins!r}"
    )
    importlib.reload(cfg_mod)  # 还原模块状态，避免污染其它测试


def test_secret_key_not_weak_default_when_unset(monkeypatch, tmp_path):
    """缺陷③：未设 STOCKSIGNAL_SECRET 时不得回退公开弱默认——应首启生成随机密钥并持久化。"""
    monkeypatch.delenv("STOCKSIGNAL_SECRET", raising=False)
    import backend.config as cfg_mod
    cfg_mod = importlib.reload(cfg_mod)  # 刷新到当前源码（会话内可能存在旧加载）
    key_file = tmp_path / "secret_key"
    monkeypatch.setattr(cfg_mod, "SECRET_KEY_FILE", key_file)
    k1 = cfg_mod._resolve_secret()   # 直接调用解析函数（env 已清空）
    assert k1 != "dev-only-change-me-in-production", "SECRET_KEY 仍是公开弱默认"
    assert len(str(k1)) >= 32, "随机密钥长度不足"
    assert key_file.exists(), "密钥未持久化到文件"
    k2 = cfg_mod._resolve_secret()   # 二次调用：读持久化文件复用，重启不失效
    assert k2 == k1, "二次解析密钥漂移（未持久化复用）"
