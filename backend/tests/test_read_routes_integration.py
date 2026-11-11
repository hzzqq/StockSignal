"""
backend/tests/test_read_routes_integration.py
-------------------------------------------------
真实后端集成冒烟（补上此前 deferred 的「真数据链路」目检）：

  用真实 Flask app + 真实 JWT 打 read_routes 中「离线可达」端点（读本地真数据，
  不依赖联网），断言：
    1. 统一信封：HTTP 200 + JSON 含 status/code/message/data 四字段；
    2. 对象端点 data 为 dict、列表端点 data 为 list（或缺失时 data=None 仍合法信封）；
    3. 鉴权门：未带 token → 401 且 code=missing_token；
    4. 非法参数：breadth-analytics?window=999 → 400；six-dim?code=BAD → 400。

  为何必要：前端 MSW 夹具只能证明「前端↔夹具」自洽，不能证明真后端真能正确
  吐信封。本测试直接打真后端，是契约漂移守卫（tests/test_read_contract_drift.py）
  的离线对键之外的第二道防线——保证「真后端在真数据/真鉴权/真异常参数下不 500、
  信封合法」。network 类端点（market-sentiment/momentum-breadth/limit-up-review/
  earnings-calendar 等）在 sandbox 无网时会优雅降级为 200 ok，不在此处强校验内容。

设计约束：独立临时 SQLite + _TestConfig 隔离，绝不污染 backend/data/app.db；
不依赖联网，确定性可重复。
"""
from __future__ import annotations

import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.models import User  # noqa: E402


# 离线可达端点（读本地真数据，不联网）。value 为期望 data 类型：
# "dict" = 对象端点；"list" = 列表端点。
OFFLINE_ENDPOINTS = {
    "/api/v2/read/daily-snapshot": "dict",
    "/api/v2/read/daily-recommendation": "dict",
    "/api/v2/read/event-pool": "dict",
    "/api/v2/read/prediction-log": "list",
    "/api/v2/read/p1-sync-status": "dict",
    "/api/v2/read/data-refresh-state": "dict",
    "/api/v2/read/backtest-runs": "dict",
    "/api/v2/read/ladder-detail": "list",
    "/api/v2/read/breadth-history": "list",
    "/api/v2/read/webapps": "list",
    "/api/v2/read/snapshot-dates": "list",
    "/api/v2/read/breadth-analytics?window=250": "dict",
    "/api/v2/read/six-dim?code=600519": "dict",
}


@pytest.fixture
def app():
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 't.db')}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

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


def _token(client, username="demo", password="Pass@123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


def _assert_envelope(j, expect_data_type=None):
    assert isinstance(j, dict), f"响应非 JSON dict: {j}"
    for k in ("status", "code", "message", "data"):
        assert k in j, f"信封缺字段 {k}: {j}"
    d = j["data"]
    if expect_data_type == "dict":
        assert d is None or isinstance(d, dict), f"期望 dict/None，实得 {type(d)}: {j}"
    elif expect_data_type == "list":
        assert d is None or isinstance(d, list), f"期望 list/None，实得 {type(d)}: {j}"


def test_offline_endpoints_serve_valid_envelope(client):
    tok = _token(client)
    hdr = {"Authorization": f"Bearer {tok}"}
    for ep, dt in OFFLINE_ENDPOINTS.items():
        r = client.get(ep, headers=hdr)
        assert r.status_code == 200, f"{ep} 非 200：{r.status_code} {r.text[:200]}"
        _assert_envelope(r.get_json(), dt)


def test_auth_gate_requires_token(client):
    r = client.get("/api/v2/read/daily-snapshot")
    assert r.status_code == 401, r.text[:200]
    assert r.get_json().get("code") == "missing_token", r.text[:200]


def test_invalid_param_rejected_not_500(client):
    tok = _token(client)
    hdr = {"Authorization": f"Bearer {tok}"}
    # window 白名单外 → 400（非 500）
    r1 = client.get("/api/v2/read/breadth-analytics?window=999", headers=hdr)
    assert r1.status_code == 400, f"window 非法应 400，实得 {r1.status_code} {r1.text[:200]}"
    # code 非法格式 → 400（非 500）
    r2 = client.get("/api/v2/read/six-dim?code=BAD", headers=hdr)
    assert r2.status_code == 400, f"code 非法应 400，实得 {r2.status_code} {r2.text[:200]}"
