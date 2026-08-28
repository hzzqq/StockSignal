"""后端可用性加固：请求体大小上限（防超大 payload 造成内存/DoS）。

验证：超过 MAX_CONTENT_LENGTH 的请求应返回结构化 413 JSON，
绝不回退到 Flask 默认 HTML 错误页。
"""
import json

import pytest

from backend.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATE_LIMIT_ENABLED"] = False
    # 测试用极小阈值，便于构造超限请求
    app.config["MAX_CONTENT_LENGTH"] = 50
    return app.test_client()


def test_oversize_payload_returns_413_json(client):
    # 正文远大于 50 字节阈值
    big = {"username": "demo", "password": "x" * 200}
    r = client.post(
        "/api/auth/login",
        data=json.dumps(big),
        content_type="application/json",
    )
    assert r.status_code == 413, r.text
    body = r.get_json()
    assert body is not None, "413 必须返回 JSON，而非 HTML 错误页"
    assert body.get("status") == "error"
    assert body.get("code") == "request_entity_too_large"
    assert "text/html" not in r.headers.get("Content-Type", "")


def test_normal_payload_ok(client):
    # 正常大小请求不应被误伤
    small = {"username": "demo", "password": "Demo@123"}
    r = client.post(
        "/api/auth/login",
        data=json.dumps(small),
        content_type="application/json",
    )
    # 无论登录是否成功，都不应因体积限制被 413 拦截
    assert r.status_code != 413, r.text
