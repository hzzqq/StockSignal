"""后端 API 边界加固：变异请求必须携带 JSON，否则返回结构化 422。"""
import json

import pytest

from backend.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATE_LIMIT_ENABLED"] = False
    return app.test_client()


def test_form_encoded_post_rejected_422(client):
    r = client.post(
        "/api/auth/login",
        data="username=demo&password=x",
        content_type="application/x-www-form-urlencoded",
    )
    assert r.status_code == 422, r.text
    assert "application/json" in r.headers.get("Content-Type", "")
    body = r.get_json()
    assert body.get("status") == "error"
    assert body.get("code") == "validation_error"


def test_valid_json_post_allowed(client):
    r = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "demo", "password": "Demo@123"}),
        content_type="application/json",
    )
    # 不被 422 拦截（登录成功与否不影响本次断言）
    assert r.status_code != 422, r.text


def test_get_not_enforced(client):
    # GET 不应被 JSON 强制拦截
    r = client.get("/api/health")
    assert r.status_code in (200, 503)
