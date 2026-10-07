"""POST /api/tasks/ 提交契约回归（防止 `ok` 被局部变量遮蔽导致恒 500）。

背景（真实事故）：backend/api/task_routes.py::create_task 曾写
``ok, payload_or_err = _validate_task_payload(...)``，局部变量 `ok` 遮蔽了模块顶部
``from ..utils.response import ok`` 的响应助手，使末尾 ``return ok(data=...)`` 抛
``TypeError: 'bool' object is not callable`` → 所有后台任务（ai_consult/analysis/
compare/research...）提交即 HTTP 500，前端永远拿不到 task_id（星辰 AI「不回复」根因）。

本测试用 Flask test_client 覆盖：合法提交 200 + 返回 task_id；非法类型 400。
不依赖外网（question 走 ai_engine 的快速通道，不触发数据抓取）。
"""
from __future__ import annotations

import pytest

from backend.app import create_app
from backend.extensions import db
from backend.models import User


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATE_LIMIT_ENABLED"] = False
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


def test_create_task_returns_200_and_task_id(client):
    """合法提交必须 200 且带 task_id（回归：曾因 `ok` 遮蔽恒 500）。"""
    token = _login(client)
    r = client.post(
        "/api/tasks/",
        json={"type": "ai_consult", "payload": {"question": "你好"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"POST /api/tasks/ 应 200，实际 {r.status_code}: {r.text}"
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["data"]["task_id"], "响应缺少 task_id"


def test_create_task_rejects_unknown_type(client):
    """非法任务类型仍应 400（fail 分支不受影响）。"""
    token = _login(client)
    r = client.post(
        "/api/tasks/",
        json={"type": "not_a_type", "payload": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.get_json()["status"] == "error"


def test_create_task_rejects_non_object_payload(client):
    """payload 非对象应 400（校验分支返回 fail）。"""
    token = _login(client)
    r = client.post(
        "/api/tasks/",
        json={"type": "ai_consult", "payload": "oops"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.get_json()["status"] == "error"


def test_create_task_requires_auth(client):
    """无 token 提交应被鉴权拦截（不被 500 掩盖）。"""
    r = client.post("/api/tasks/", json={"type": "ai_consult", "payload": {"question": "你好"}})
    assert r.status_code in (401, 403)
