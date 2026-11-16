# -*- coding: utf-8 -*-
"""AC1/AC2：v2 决策闭环停摆告警只读端点契约守卫。

真值源唯一在 modules.decision.assess_decision_loop_health()；端点只透传、
不重写分级、不补零、不把缺失洗成成功。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import modules.decision as decision  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402

ENDPOINT = "/api/v2/read/decision-loop-health"
FIELDS = {
    "status", "rank", "generated_at", "as_of",
    "gen_lag_hours", "data_lag_days", "message",
}
STATUSES = {"ok", "warn", "stale", "dead", "unknown"}


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path_factory.mktemp('db') / 'a.db'}"

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="rwuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
        tok = issue_token(u)
    return application.test_client(), tok


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_requires_jwt(ctx):
    client, _ = ctx
    assert client.get(ENDPOINT).status_code in (401, 403), "只读端点必须鉴权"


def test_returns_assessment_contract(ctx):
    """AC1：信封 ok + data 为 assess() 原样的 7 字段结构。"""
    client, tok = ctx
    r = client.get(ENDPOINT, headers=_auth(tok))
    assert r.status_code == 200, f"实得 {r.status_code}"
    env = r.get_json(force=True)
    assert env["status"] == "ok", "业务状态在 data 里，信封不得谎报 error"
    data = env["data"]
    assert isinstance(data, dict) and set(data) == FIELDS, f"字段不符：{sorted(data)}"
    assert data["status"] in STATUSES
    assert isinstance(data["rank"], int) and 0 <= data["rank"] <= 3
    assert isinstance(data["message"], str) and data["message"]


def test_missing_snapshot_is_dead_not_fake_ok(ctx, monkeypatch, tmp_path):
    """AC2：快照缺失 → dead + null 字段 + 明确提示，绝不补 0 / 不假绿。"""
    monkeypatch.setattr(decision, "SNAPSHOT_PATH", str(tmp_path / "nope.json"))
    client, tok = ctx
    r = client.get(ENDPOINT, headers=_auth(tok))
    assert r.status_code == 200
    env = r.get_json(force=True)
    assert env["status"] == "ok", "业务状态 dead 不等于接口故障，不得伪装成 error 或 ok 数据"
    d = env["data"]
    assert d["status"] == "dead" and d["rank"] == 3
    assert d["generated_at"] is None and d["gen_lag_hours"] is None
    assert "每日调度" in d["message"]


def test_endpoint_passes_through_assessment(ctx, monkeypatch):
    """AC1：端点不重写分级逻辑——assess() 返回什么就透出什么。"""
    sentinel = {
        "status": "stale", "rank": 2,
        "generated_at": "2026-11-01T08:00:00", "as_of": "2026-10-31",
        "gen_lag_hours": 30.0, "data_lag_days": 16,
        "message": "⚠️ 原始告警文案（不得被端点改写）",
    }
    monkeypatch.setattr(decision, "assess_decision_loop_health", lambda: sentinel)
    client, tok = ctx
    d = client.get(ENDPOINT, headers=_auth(tok)).get_json(force=True)["data"]
    assert d == sentinel, "端点重写/美化了真值源输出"
