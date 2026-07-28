"""后端 API 冒烟测试（Flask test_client，无需起服务、不依赖外网）。

覆盖：健康检查、认证信封、未授权拦截、带 token 获取用户信息（不含
password_hash）、普通列表路由、管理员路由的角色鉴权。作为 P2 回归护栏，
防止路由/鉴权被后续改动打回。
"""
from __future__ import annotations

import pytest
from backend.app import create_app
from backend.extensions import db
from backend.models import User
from werkzeug.security import generate_password_hash


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        u = User.query.filter_by(username="demo").first()
        if u is None:
            u = User(username="demo", role="user")
            u.set_password("Demo@123")
            db.session.add(u)
        else:
            u.set_password("Demo@123")
            u.role = "user"
            u.is_active = True
        db.session.commit()
    return app.test_client()


def _login(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Demo@123"})
    assert r.status_code == 200, r.text
    return r.get_json()["data"]["token"]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_auth_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code in (401, 403)


def test_auth_me_with_token(client):
    token = _login(client)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert "password_hash" not in data, "响应泄露 password_hash"
    assert data["role"] == "user"


def test_forum_list(client):
    token = _login(client)
    r = client.get("/api/forum/posts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"


def test_admin_requires_admin_role(client):
    token = _login(client)  # demo 是 user，不是 admin
    r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (401, 403), "非 admin 角色不应访问管理员路由"
