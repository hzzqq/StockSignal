"""
backend/tests/test_chat_conversations.py
----------------------------------------
T-311 星辰 AI 多会话 API 契约测试（独立临时库，绝不污染现有库）：

  - 建表 → 列表/新建/读写/删除 roundtrip（含 count 元数据）；
  - 越权隔离：他人会话一律 404（不泄漏存在性）、列表只含自己的、未鉴权 401/403；
  - 参数防御：messages 非数组 400、标题空回退/超长钳制；
  - 旧端点 /api/chat/history 向后兼容不被破坏；
  - 迁移幂等：首次建表导入旧单记录为「历史对话」，重跑不重复导入、
    用户删光会话后重跑不复活（导入只绑定「本次新建了表」）。

运行：
    python -m pytest backend/tests/test_chat_conversations.py -q
"""
from __future__ import annotations

import json
import os
import sys

# 把项目根（StockSignal）加入 sys.path，保证 `import backend...` 可行
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.models import User, ChatHistory, ChatConversation  # noqa: E402
from backend.scripts.migrate_add_chat_conversations import (  # noqa: E402
    migrate as migrate_convs,
)


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def app(tmp_path):
    # 每个用例独立临时库（tmp_path 唯一），与既有 backend 测试同一隔离范式
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 't.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        for uname in ("alice", "bob"):
            u = User(username=uname, role="user")
            u.set_password("Pass@123")
            db.session.add(u)
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------- 辅助
def _token(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "Pass@123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


def _H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------- 用例
def test_roundtrip(client):
    """新建 → 保存 → 列表 → 读取 → 删除 全链路。"""
    tok = _token(client, "alice")
    r = client.post("/api/chat/conversations", json={"title": "测试会话"}, headers=_H(tok))
    assert r.status_code == 200, r.text[:200]
    data = r.get_json()["data"]
    cid = data["id"]
    assert data["title"] == "测试会话"
    # 保存消息
    msgs = [{"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀", "ts": "2026-10-24T00:00:00"}]
    r = client.post(f"/api/chat/conversations/{cid}", json={"messages": msgs}, headers=_H(tok))
    assert r.status_code == 200 and r.get_json()["data"]["saved"] is True
    # 列表（含 count 元数据）
    r = client.get("/api/chat/conversations", headers=_H(tok))
    convs = r.get_json()["data"]["conversations"]
    assert len(convs) == 1 and convs[0]["id"] == cid and convs[0]["count"] == 2
    assert convs[0]["title"] == "测试会话"
    # 读取
    r = client.get(f"/api/chat/conversations/{cid}", headers=_H(tok))
    assert r.get_json()["data"]["messages"] == msgs
    # 删除 → 读取 404 → 列表空
    assert client.delete(f"/api/chat/conversations/{cid}", headers=_H(tok)).status_code == 200
    assert client.get(f"/api/chat/conversations/{cid}", headers=_H(tok)).status_code == 404
    assert client.get(
        "/api/chat/conversations", headers=_H(tok)
    ).get_json()["data"]["conversations"] == []


def test_ownership_isolation(client):
    """越权隔离：他人会话一律 404 不泄漏存在性；列表只含自己的；未鉴权 401/403。"""
    ta, tb = _token(client, "alice"), _token(client, "bob")
    cid = client.post("/api/chat/conversations", json={}, headers=_H(ta)).get_json()["data"]["id"]
    assert client.get(f"/api/chat/conversations/{cid}", headers=_H(tb)).status_code == 404
    assert client.post(
        f"/api/chat/conversations/{cid}", json={"messages": []}, headers=_H(tb)
    ).status_code == 404
    assert client.delete(f"/api/chat/conversations/{cid}", headers=_H(tb)).status_code == 404
    # bob 看不到 alice 的会话
    assert client.get(
        "/api/chat/conversations", headers=_H(tb)
    ).get_json()["data"]["conversations"] == []
    # 未带 token → 401/403
    assert client.get("/api/chat/conversations").status_code in (401, 403)


def test_bad_params_and_title_norm(client):
    """参数防御：messages 非数组 400；标题空回退默认、超长钳制。"""
    tok = _token(client, "alice")
    cid = client.post(
        "/api/chat/conversations", json={}, headers=_H(tok)
    ).get_json()["data"]["id"]
    assert client.post(
        f"/api/chat/conversations/{cid}", json={"messages": "x"}, headers=_H(tok)
    ).status_code == 400
    r = client.post("/api/chat/conversations", json={"title": "   "}, headers=_H(tok))
    assert r.get_json()["data"]["title"] == "新对话"
    r = client.post("/api/chat/conversations", json={"title": "长" * 100}, headers=_H(tok))
    assert len(r.get_json()["data"]["title"]) == 40


def test_legacy_history_endpoint_still_works(client):
    """旧端点 /api/chat/history 向后兼容：新端点加入后旧读写路径不破坏。"""
    tok = _token(client, "alice")
    r = client.post(
        "/api/chat/history",
        json={"messages": [{"role": "user", "content": "旧路径"}]},
        headers=_H(tok),
    )
    assert r.status_code == 200
    r = client.get("/api/chat/history", headers=_H(tok))
    assert r.get_json()["data"]["messages"][0]["content"] == "旧路径"


def test_migrate_import_and_idempotent(app):
    """旧单记录 → 首次建表迁移导入「历史对话」；重跑幂等、删光后重跑不复活。"""
    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        db.session.add(ChatHistory(
            user_id=alice.id,
            messages=json.dumps([{"role": "user", "content": "旧历史"}]),
        ))
        db.session.commit()
        # 测试 fixture 的 create_all 已建表 → 先 drop 才能验证「首次建表」分支
        ChatConversation.__table__.drop(db.engine)
        assert migrate_convs(app) is True  # 首次：建表 + 导入
        convs = ChatConversation.query.filter_by(user_id=alice.id).all()
        assert len(convs) == 1
        assert convs[0].title == "历史对话"
        assert json.loads(convs[0].messages)[0]["content"] == "旧历史"
        # 幂等：表已存在 → 跳过，不重复导入
        assert migrate_convs(app) is False
        assert ChatConversation.query.count() == 1
        # 用户删光会话后重跑迁移 → 不复活（导入只绑定「本次新建了表」）
        ChatConversation.query.delete()
        db.session.commit()
        assert migrate_convs(app) is False
        assert ChatConversation.query.count() == 0


# ---------------------------------------------------------------- 导出端点
def test_export_json(client):
    """format=json → 返回结构化 envelope，与 GET /conversations/<id> 同形。"""
    tok = _token(client, "alice")
    cid = client.post(
        "/api/chat/conversations",
        json={"title": "导出测试"},
        headers=_H(tok),
    ).get_json()["data"]["id"]
    msgs = [{"role": "user", "content": "问"}, {"role": "assistant", "content": "答"}]
    client.post(f"/api/chat/conversations/{cid}",
                json={"messages": msgs}, headers=_H(tok))

    r = client.get(f"/api/chat/conversations/{cid}/export?format=json",
                   headers=_H(tok))
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["id"] == cid
    assert data["title"] == "导出测试"
    assert data["messages"] == msgs


def test_export_markdown(client):
    """format=markdown → text/markdown 纯文本，Content-Disposition 带会话标题，逐轮对话渲染。"""
    tok = _token(client, "alice")
    cid = client.post(
        "/api/chat/conversations",
        json={"title": "星辰AI测试会话"},
        headers=_H(tok),
    ).get_json()["data"]["id"]
    msgs = [
        {"role": "user", "content": "茅台值得买吗？"},
        {"role": "assistant", "content": "让我查一下最新数据…"},
    ]
    client.post(f"/api/chat/conversations/{cid}",
                json={"messages": msgs}, headers=_H(tok))

    r = client.get(f"/api/chat/conversations/{cid}/export?format=markdown",
                   headers=_H(tok))
    assert r.status_code == 200
    assert r.mimetype.startswith("text/markdown")
    body = r.get_data(as_text=True)
    assert "# 星辰AI测试会话" in body
    assert "🧑 用户" in body
    assert "🤖 星辰AI" in body
    assert "茅台值得买吗" in body
    assert "让我查一下" in body
    # Content-Disposition 带会话标题
    cd = r.headers.get("Content-Disposition", "")
    assert f"conversation_{cid}" in cd
    assert "星辰AI测试会话" in cd or "星辰AI测试会话".replace(" ", "_") in cd


def test_export_format_validation(client):
    """format 非法值 → 400；缺省默认 json。"""
    tok = _token(client, "alice")
    cid = client.post("/api/chat/conversations", json={}, headers=_H(tok)).get_json()["data"]["id"]
    assert client.get(
        f"/api/chat/conversations/{cid}/export?format=xml", headers=_H(tok)
    ).status_code == 400
    # 缺省 → json（200 且 envelope 包装）
    r = client.get(f"/api/chat/conversations/{cid}/export", headers=_H(tok))
    assert r.status_code == 200
    assert "data" in r.get_json()  # json envelope


def test_export_ownership(client):
    """越权隔离：他人会话 export 一律 404，不泄漏存在性。"""
    ta, tb = _token(client, "alice"), _token(client, "bob")
    cid = client.post("/api/chat/conversations", json={}, headers=_H(ta)).get_json()["data"]["id"]
    for fmt in ("json", "markdown"):
        assert client.get(
            f"/api/chat/conversations/{cid}/export?format={fmt}", headers=_H(tb)
        ).status_code == 404


def test_export_empty_conversation(client):
    """空会话 → markdown 如实标注空消息，不编造。"""
    tok = _token(client, "alice")
    cid = client.post(
        "/api/chat/conversations",
        json={"title": "空的"},
        headers=_H(tok),
    ).get_json()["data"]["id"]
    r = client.get(
        f"/api/chat/conversations/{cid}/export?format=markdown", headers=_H(tok)
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "# 空的" in body
    assert "空会话" in body.lower()
