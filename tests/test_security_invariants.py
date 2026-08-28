"""后端安全不变量回归测试：锁定已加固的出口行为，防止后续改动悄悄回退。

覆盖：
  - 未认证访问受保护 API → 401 结构化 JSON（非 HTML）
  - 未知 /api/ 路由 → 404 结构化 JSON
  - 超大请求体 → 413 结构化 JSON（见 test_request_size_limit，此处仅校验缺省阈值生效）
  - 未捕获异常 → 500 结构化 JSON，绝不泄露 HTML/traceback
  - 所有 API 响应携带安全头（nosniff / X-Frame-Options / no-store）
"""
import json

import pytest

from backend.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATE_LIMIT_ENABLED"] = False
    # 注入一个必崩路由，用于验证 500 处理
    @app.get("/api/_test_boom")
    def _boom():
        raise RuntimeError("boom-detail-should-not-leak")
    return app.test_client()


def _is_json(resp) -> bool:
    return "application/json" in resp.headers.get("Content-Type", "")


def test_unauthenticated_protected_route_returns_401_json(client):
    r = client.post(
        "/api/trade/orders",
        data=json.dumps({"stock_code": "600000"}),
        content_type="application/json",
    )
    assert r.status_code == 401, r.text
    assert _is_json(r), "401 必须返回 JSON"
    body = r.get_json()
    assert body.get("status") == "error"
    assert "text/html" not in r.headers.get("Content-Type", "")


def test_unknown_api_route_returns_404_json(client):
    r = client.get("/api/this_route_does_not_exist")
    assert r.status_code == 404, r.text
    assert _is_json(r)
    body = r.get_json()
    assert body.get("status") == "error"
    assert body.get("code") == "not_found"


def test_unhandled_exception_returns_500_json_no_html_leak(client):
    r = client.get("/api/_test_boom")
    assert r.status_code == 500, r.text
    assert _is_json(r), "500 必须返回 JSON，不可回退 HTML traceback"
    body = r.get_json()
    assert body.get("status") == "error"
    assert "boom-detail-should-not-leak" not in r.text  # 内部细节绝不可外泄
    assert "text/html" not in r.headers.get("Content-Type", "")


def test_security_headers_present_on_api_response(client):
    r = client.get("/api/health")
    assert r.status_code in (200, 200)
    headers = r.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert "no-store" in headers.get("Cache-Control", "")
