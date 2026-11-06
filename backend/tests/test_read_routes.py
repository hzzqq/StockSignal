# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_read_routes.py — W1 只读端点回归守卫。

验证：
  1. 每个新端点无 token -> 401（鉴权闸门）；
  2. 有合法 token 且背后数据文件存在 -> 200 + 信封 {status:ok, code:ok, ...}；
  3. 背后文件缺失 -> 200 + status=error（优雅降级，绝不 500）；
  4. 非法 date/user 参数 -> 400 validation_error（防穿越）；
  5. /api/openapi.json 覆盖 /api/v2/read/* 路径。

为避免触碰真实 data/，测试把 read_routes 模块的目录常量 monkeypatch 到临时树。
"""
from __future__ import annotations

import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402


# 实际请求用的具体路径（含参数/具体日期）
ENDPOINTS = [
    "/api/v2/read/daily-snapshot",
    "/api/v2/read/daily-recommendation",
    "/api/v2/read/user-dashboard",
    "/api/v2/read/alert-rules",
    "/api/v2/read/alert-log",
    "/api/v2/read/virtual-users-sim",
    "/api/v2/read/p1-signals",
    "/api/v2/read/snapshot-dates",
    "/api/v2/read/snapshot/2026-08-31",
    "/api/v2/read/paper-trades?user=demo",
    "/api/v2/read/review-notes?date=2026-08-31",
    "/api/v2/read/webapps",
]

# OpenAPI spec 中的路径（<date> 在 spec 里被渲染成 {date}）
SPEC_PATHS = [
    "/api/v2/read/daily-snapshot",
    "/api/v2/read/daily-recommendation",
    "/api/v2/read/user-dashboard",
    "/api/v2/read/alert-rules",
    "/api/v2/read/alert-log",
    "/api/v2/read/virtual-users-sim",
    "/api/v2/read/p1-signals",
    "/api/v2/read/snapshot-dates",
    "/api/v2/read/snapshot/{date}",
    "/api/v2/read/paper-trades",
    "/api/v2/read/review-notes",
    "/api/v2/read/webapps",
]


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'a.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="rwuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def client(app, tmp_path_factory):
    # 构造隔离的临时数据树并 monkeypatch 模块目录常量
    root = tmp_path_factory.mktemp("readroot")
    data = root / "data"
    reports = root / "reports"
    webapps = root / "webapps"
    for d in (data, reports, webapps):
        d.mkdir(parents=True, exist_ok=True)

    (data / "daily_snapshot.json").write_text(json.dumps({"date": "2026-08-31", "temperature": 42}),
                                              encoding="utf-8")
    (data / "daily_recommendation.json").write_text(json.dumps({"picks": [{"code": "600519"}]}),
                                                   encoding="utf-8")
    (data / "user_dashboard.json").write_text(json.dumps({"layout": "grid"}), encoding="utf-8")
    (data / "alert_rules.json").write_text(json.dumps({"rules": []}), encoding="utf-8")
    (data / "alerts.log").write_text("[2026-08-31] rule fired\n", encoding="utf-8")
    (reports / "virtual_users_sim.json").write_text(json.dumps({"meta": {"n_users": 100}}),
                                                   encoding="utf-8")

    p1 = data / "p1_signals"
    p1.mkdir(exist_ok=True)
    (p1 / "signal_ev.json").write_text(json.dumps({"model": "ev", "top": [{"code": "600519"}]}),
                                       encoding="utf-8")

    snaps = data / "snapshots"
    snaps.mkdir(exist_ok=True)
    (snaps / "2026-08-31.json").write_text(json.dumps({"date": "2026-08-31"}), encoding="utf-8")

    (data / "paper_demo.json").write_text(json.dumps({"cash": 100000}), encoding="utf-8")
    (data / "review_notes_2026-08-31.md").write_text("# 复盘\n今日缩量。\n", encoding="utf-8")

    wa = webapps / "foo"
    wa.mkdir(parents=True, exist_ok=True)
    (wa / "meta.json").write_text(
        json.dumps({"title": "Demo WebApp", "entry": "index.html", "added": "2026-08-31"}),
        encoding="utf-8",
    )

    rr._DATA_DIR = data.resolve()
    rr._REPORTS_DIR = reports.resolve()
    rr._WEBAPPS_DIR = webapps.resolve()
    rr._FILE_WHITELIST = {
        "daily_snapshot": data / "daily_snapshot.json",
        "daily_recommendation": data / "daily_recommendation.json",
        "user_dashboard": data / "user_dashboard.json",
        "alert_rules": data / "alert_rules.json",
        "alert_log": data / "alerts.log",
        "virtual_users_sim": reports / "virtual_users_sim.json",
    }
    return app.test_client()


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        u = User.query.filter_by(username="rwuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_auth_gate_requires_token(client):
    """所有新端点无 token 必须 401。"""
    for ep in ENDPOINTS:
        resp = client.get(ep)
        assert resp.status_code == 401, f"无 token 应 401: {ep} -> {resp.status_code}"


def test_existing_files_return_ok_envelope(client, token):
    """背后文件存在 -> 200 + status=ok 信封。"""
    # 固定文件类
    for ep, key in (
        ("/api/v2/read/daily-snapshot", "daily_snapshot.json"),
        ("/api/v2/read/daily-recommendation", "daily_recommendation.json"),
        ("/api/v2/read/user-dashboard", "user_dashboard.json"),
        ("/api/v2/read/alert-rules", "alert_rules.json"),
        ("/api/v2/read/alert-log", "alerts.log"),
        ("/api/v2/read/virtual-users-sim", "virtual_users_sim.json"),
    ):
        obj = client.get(ep, headers=_auth(token)).get_json()
        assert obj["status"] == "ok" and obj["code"] == "ok", f"{ep}: {obj}"

    # 目录/参数化类
    obj = client.get("/api/v2/read/p1-signals", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and "signal_ev.json" in obj["data"], obj

    obj = client.get("/api/v2/read/snapshot-dates", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and "2026-08-31" in obj["data"], obj

    obj = client.get("/api/v2/read/snapshot/2026-08-31", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"]["date"] == "2026-08-31", obj

    obj = client.get("/api/v2/read/paper-trades?user=demo", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"]["cash"] == 100000, obj

    obj = client.get("/api/v2/read/review-notes?date=2026-08-31",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and "复盘" in obj["data"]["content"], obj

    obj = client.get("/api/v2/read/webapps", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"][0]["title"] == "Demo WebApp", obj


def test_missing_files_graceful_error(client, token):
    """文件缺失 -> 200 + status=error（优雅，不 500）。"""
    for ep in (
        "/api/v2/read/snapshot/2099-01-01",
        "/api/v2/read/paper-trades?user=nobody",
        "/api/v2/read/review-notes?date=2099-01-01",
    ):
        resp = client.get(ep, headers=_auth(token))
        assert resp.status_code == 200, f"{ep} 缺失应 200 而非 {resp.status_code}: {resp.text[:120]}"
        obj = resp.get_json()
        assert obj["status"] == "error" and obj["code"] == "not_found", f"{ep}: {obj}"


def test_invalid_params_validation_error(client, token):
    """非法 date/user -> 400 validation_error（防穿越）。"""
    for ep in (
        "/api/v2/read/snapshot/2026-13-99",
        "/api/v2/read/paper-trades?user=bad%2Fuser",  # 含 '/'
        "/api/v2/read/review-notes?date=not-a-date",
    ):
        resp = client.get(ep, headers=_auth(token))
        assert resp.status_code == 400, f"{ep} 应 400: {resp.status_code} {resp.text[:120]}"
        obj = resp.get_json()
        assert obj["code"] == "validation_error", f"{ep}: {obj}"


def test_openapi_covers_read_routes(client):
    """spec 必须覆盖全部 /api/v2/read/* 路径且标注 BearerAuth。"""
    spec = client.get("/api/openapi.json").get_json()
    paths = spec["paths"]
    for base in SPEC_PATHS:
        node = paths.get(base)
        assert node is not None, f"spec 缺失路径: {base}"
        assert "get" in node, f"{base} 缺 get"
        assert node["get"].get("security") == [{"BearerAuth": []}], f"{base} 未标注鉴权"
