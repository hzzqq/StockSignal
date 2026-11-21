"""
backend/tests/test_chat_rename.py
--------------------------------
星辰 AI 会话「只改标题」PATCH 端点契约测试（独立临时库，绝不污染现有库）：

  - 正常改名：响应 data 含 ok/id/title，GET 回读标题同步；
  - 空白/缺失标题回退「新对话」；超 40 字截断；
  - **关键反证**：messages 字段字节级不变（先读原始文本，PATCH 后再读，断言完全相等）；
  - 越权 cid / 不存在 cid 一律 404，中文错误文案；未鉴权 401/403。

运行：
    python -m pytest backend/tests/test_chat_rename.py -q
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
from backend.models import User, ChatConversation  # noqa: E402


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def app(tmp_path):
    # 每个用例独立临时库（tmp_path 唯一），与 test_chat_conversations.py 同一隔离范式；
    # 与占用 5050 的服务不争锁，绝不写业务库。
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


def _new_conv(client, tok, title="原会话"):
    r = client.post("/api/chat/conversations", json={"title": title}, headers=_H(tok))
    assert r.status_code == 200, r.text[:200]
    return r.get_json()["data"]["id"]


def _raw_messages(app, cid):
    """从 DB 读取 messages 原始文本（字节级对照用，绕过 API 序列化）。"""
    with app.app_context():
        rec = ChatConversation.query.get(cid)
        assert rec is not None
        return rec.messages


# ---------------------------------------------------------------- 用例
def test_rename_ok(client, app):
    """正常改名：响应 data={ok,id,title}，GET 回读标题同步。"""
    tok = _token(client, "alice")
    cid = _new_conv(client, tok, "旧标题")
    r = client.patch(
        f"/api/chat/conversations/{cid}", json={"title": "  星辰 AI 问答  "}, headers=_H(tok)
    )
    assert r.status_code == 200, r.text[:200]
    assert r.get_json()["data"] == {"ok": True, "id": cid, "title": "星辰 AI 问答"}
    # GET 回读标题确实更新（trim 后）
    got = client.get(f"/api/chat/conversations/{cid}", headers=_H(tok)).get_json()["data"]
    assert got["title"] == "星辰 AI 问答"


def test_title_blank_and_missing_fallback(client):
    """空白 / 缺失标题 → 回退「新对话」。"""
    tok = _token(client, "alice")
    cid = _new_conv(client, tok, "原会话")
    # 空白字符串
    r = client.patch(f"/api/chat/conversations/{cid}", json={"title": "   "}, headers=_H(tok))
    assert r.status_code == 200
    assert r.get_json()["data"]["title"] == "新对话"
    # 完全缺失 title（空 body）
    r = client.patch(f"/api/chat/conversations/{cid}", json={}, headers=_H(tok))
    assert r.status_code == 200
    assert r.get_json()["data"]["title"] == "新对话"
    # 无 body
    r = client.patch(f"/api/chat/conversations/{cid}", headers=_H(tok))
    assert r.status_code == 200
    assert r.get_json()["data"]["title"] == "新对话"


def test_title_truncate_40(client):
    """超 40 字 → 截断到 40（复用 _norm_title / _TITLE_MAX）。"""
    tok = _token(client, "alice")
    cid = _new_conv(client, tok)
    r = client.patch(
        f"/api/chat/conversations/{cid}", json={"title": "长" * 100}, headers=_H(tok)
    )
    assert r.status_code == 200
    title = r.get_json()["data"]["title"]
    assert len(title) == 40
    assert title == "长" * 40


def test_messages_byte_identical(client, app):
    """关键反证：PATCH 前后 messages 原始文本字节级完全相等，绝不改写历史消息。"""
    tok = _token(client, "alice")
    cid = _new_conv(client, tok, "原会话")
    # 先写入一条含中文/emoji/时间戳/特殊字符的消息，制造可辨识的原始字节
    msgs = [
        {"role": "user", "content": "茅台值得买吗？", "ts": "2026-10-24T00:00:00"},
        {"role": "assistant", "content": "让我查一下最新数据  \\n  \"引号\" 🎯", "nested": {"k": [1, 2, 3]}},
    ]
    assert client.post(
        f"/api/chat/conversations/{cid}", json={"messages": msgs}, headers=_H(tok)
    ).status_code == 200

    before = _raw_messages(app, cid)
    assert before and json.loads(before) == msgs  # 前置确认确有内容

    # 改名（甚至带一个误导性的 messages 字段，后端必须忽略它）
    r = client.patch(
        f"/api/chat/conversations/{cid}",
        json={"title": "新标题", "messages": [{"role": "user", "content": "恶意覆盖"}]},
        headers=_H(tok),
    )
    assert r.status_code == 200

    after = _raw_messages(app, cid)
    assert after == before, "PATCH 竟然改写了 messages 原始字节"
    # 双重确认：API 回读仍是原消息，未被「恶意覆盖」字段污染
    got = client.get(f"/api/chat/conversations/{cid}", headers=_H(tok)).get_json()["data"]
    assert got["messages"] == msgs


def test_ownership_and_missing(client):
    """越权 / 不存在 cid → 404；中文错误文案；未鉴权 401/403。"""
    ta, tb = _token(client, "alice"), _token(client, "bob")
    cid = _new_conv(client, ta, "alice 的会话")
    # 越权：bob 改 alice 的会话
    r = client.patch(f"/api/chat/conversations/{cid}", json={"title": "抢"}, headers=_H(tb))
    assert r.status_code == 404
    assert r.get_json()["message"] == "会话不存在"
    # 不存在 cid
    r = client.patch("/api/chat/conversations/999999", json={"title": "x"}, headers=_H(ta))
    assert r.status_code == 404
    assert r.get_json()["message"] == "会话不存在"
    # 越权/不存在都不得改动原会话
    got = client.get(f"/api/chat/conversations/{cid}", headers=_H(ta)).get_json()["data"]
    assert got["title"] == "alice 的会话"
    # 未鉴权
    assert client.patch(f"/api/chat/conversations/{cid}", json={"title": "x"}).status_code in (401, 403)
