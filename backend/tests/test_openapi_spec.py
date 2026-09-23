"""
backend/tests/test_openapi_spec.py
----------------------------------
T-159：OpenAPI 3.0 规范骨架守卫。

【为什么要有这个守卫】
  T-149 企业级评估实证：backend 此前无任何 API 文档（openapi/swagger 零匹配），
  75 REST 端点的契约只存在于代码与散落的 docstring 中，对接方（小程序/第三方/
  新成员）没有单一可读契约面。本守卫防两类漂移：
    1. spec 与真实路由脱节：url_map 里的 /api/* 端点必须全部出现在 spec 中
       （新增端点忘更新 spec → 红）；
    2. spec 结构失效：openapi 版本/信封 schema/鉴权 scheme 缺失 → 红。

  spec 由 build_spec(app) 从 app.url_map 动态生成，路径天然与路由一致；
  守卫的价值在于钉死「生成器本身不被掏空 + 关键端点存在」。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest                                # noqa: E402

from backend.app import create_app           # noqa: E402
from backend.config import Config            # noqa: E402
from backend.openapi import _openapi_path    # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        # 注意：不能用 sqlite:///:memory:——SQLALCHEMY_ENGINE_OPTIONS 的
        # pool_size/max_overflow 与 StaticPool 不兼容（TypeError）
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path_factory.mktemp('db') / 'a.db'}"

    return create_app(_C)


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


def _spec(client):
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def test_spec_served_and_valid(client):
    spec = _spec(client)
    assert spec.get("openapi", "").startswith("3.")
    assert spec.get("info", {}).get("title"), "info.title 必填"
    assert isinstance(spec.get("paths"), dict) and spec["paths"], "paths 不得为空"


def test_spec_covers_all_api_routes(client, app):
    """spec 与 url_map 一致：每个 /api/* 路由（含方法）必须登记在 spec 中。"""
    spec = _spec(client)
    paths = spec["paths"]
    missing = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        if rule.rule in ("/api/openapi.json", "/api/docs"):
            continue  # 文档自举端点
        for m in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            node = paths.get(_openapi_path(rule.rule))
            if node is None or m.lower() not in node:
                missing.append(f"{m} {rule.rule}")
    assert not missing, f"spec 缺失端点（新增路由未进文档）: {missing}"


def test_auth_endpoints_in_spec(client):
    """auth 全部端点（含 T-158 新增 /api/auth/refresh）必须可被对接方发现。

    OpenAPI paths 以完整路径为键（/api/auth/login），非前缀嵌套。
    """
    spec = _spec(client)
    paths = spec["paths"]
    for sub, method in (
        ("/api/auth/login", "post"),
        ("/api/auth/register", "post"),
        ("/api/auth/refresh", "post"),
        ("/api/auth/me", "get"),
        ("/api/auth/logout", "post"),
        ("/api/auth/logins", "get"),
        ("/api/auth/settings", "post"),
        ("/api/auth/avatar", "post"),
        ("/api/auth/token-info", "get"),
    ):
        assert method in paths.get(sub, {}), f"{method.upper()} {sub} 不在 spec 中"


def test_envelope_schema_present(client):
    """统一响应信封必须是可引用的 schema（对接方按信封解析，而非裸字段）。"""
    spec = _spec(client)
    schemas = spec.get("components", {}).get("schemas", {})
    env = schemas.get("EnvelopeResponse")
    assert env, "EnvelopeResponse schema 缺失"
    props = env.get("properties", {})
    for k in ("status", "code", "message", "data"):
        assert k in props, f"信封缺字段 {k}"


def test_bearer_scheme_declared(client):
    spec = _spec(client)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert "BearerAuth" in schemes, "Bearer 鉴权 scheme 必须声明"


def test_docs_page_served(client):
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("Content-Type", "")
    body = resp.get_data(as_text=True)
    assert "openapi.json" in body, "docs 页必须引用本服务的 spec"
