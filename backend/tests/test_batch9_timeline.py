"""批次9测试：timeline 持久化 + 端点守卫。

三个层面：
  1. Schema 完整性 — AiTimelineEvent 字段 + 索引存在
  2. 持久化链路 — Flask app context 下 _persist_timeline_event 写入可用
  3. 端点守卫 — GET /api/tasks/<id>/timeline 返回结构化 timeline
"""
from __future__ import annotations

import os
import sys
import time

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def app(tmp_path):
    from backend.app import create_app
    from backend.extensions import db
    from backend.config import Config

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'timeline_test.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        # 确保测试用户存在
        from backend.models import User
        if not db.session.get(User, 1):
            u = User(id=1, username="demo", role="user")
            u.set_password("Demo@123")
            db.session.add(u)
            db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def token(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Demo@123"})
    assert r.status_code == 200, f"login failed: {r.status_code}"
    return r.get_json()["data"]["token"]


# --- 1. Schema 完整性守卫 ---

def test_ai_timeline_event_model_has_expected_fields():
    """AiTimelineEvent 模型应覆盖批次8 dict event 的所有关键字段。"""
    from backend.models import AiTimelineEvent

    cols = {c.name for c in AiTimelineEvent.__table__.columns}
    required = {"id", "task_id", "stage", "event_type", "tool_name",
                "message", "event_json", "idx", "elapsed_s", "status", "ts", "created_at"}
    missing = required - cols
    assert not missing, f"AiTimelineEvent 缺失列: {missing}"


def test_ai_timeline_event_compound_index_exists():
    """批次9 要求 (task_id, ts) 复合索引加速按任务拉完整 timeline。"""
    from backend.models import AiTimelineEvent

    idx_names = [i.name for i in AiTimelineEvent.__table__.indexes]
    assert "ix_timeline_task_id_ts" in idx_names, f"缺少复合索引 ix_timeline_task_id_ts，现有: {idx_names}"


def test_ai_timeline_event_to_dict_returns_expected_keys():
    """to_dict() 应返回前端可直接消费的 dict。"""
    from backend.models import AiTimelineEvent

    row = AiTimelineEvent(
        task_id="t1", stage="research", event_type="tool_end",
        tool_name="get_price", message="⚡ get_price → ok · 1.2s",
        event_json='{"type":"tool_end","tool":"get_price","elapsed_s":1.2,"status":"ok"}',
        idx=1, elapsed_s=1.2, status="ok", ts=1000.0,
    )
    d = row.to_dict()
    assert d["task_id"] == "t1"
    assert d["event_type"] == "tool_end"
    assert d["status"] == "ok"
    assert d["idx"] == 1
    assert isinstance(d["event"], dict)
    assert d["event"]["tool"] == "get_price"


def test_ai_timeline_event_dumps_json_safe_on_malformed():
    """dumps_json 遇到不可序列化对象应返回 None（绝不中断持久化）。"""
    from backend.models import AiTimelineEvent

    assert AiTimelineEvent.dumps_json({"bad": lambda x: x}) is None
    assert AiTimelineEvent.dumps_json(None) is None
    s = AiTimelineEvent.dumps_json({"a": 1, "b": "ok"})
    assert s is not None and '"a": 1' in s


# --- 2. 持久化链路守卫 ---

def test_persist_timeline_event_writes_to_db(app):
    """Flask app context 下，_persist_timeline_event 应写入 AiTimelineEvent 表。"""
    from backend.models import AiTimelineEvent, db
    from backend.tasks.worker import _persist_timeline_event

    task_id = f"test_persist_{int(time.time() * 1000)}"
    batch8_event = {
        "type": "tool_end", "tool": "get_market_sentiment",
        "idx": 1, "total": 3, "elapsed_s": 39.2,
        "status": "ok", "summary": "temperature 24.7",
        "_fmt": "⚡ [1/3] get_market_sentiment → ok · 39.2s: temperature 24.7",
    }

    with app.app_context():
        db.create_all()
        _persist_timeline_event(task_id, "research", batch8_event)

    with app.app_context():
        rows = db.session.execute(
            db.select(AiTimelineEvent).where(AiTimelineEvent.task_id == task_id)
        ).scalars().all()

    assert len(rows) == 1
    r = rows[0]
    assert r.event_type == "tool_end"
    assert r.tool_name == "get_market_sentiment"
    assert r.status == "ok"
    assert r.idx == 1
    assert r.elapsed_s == pytest.approx(39.2, abs=0.1)
    assert "temperature 24.7" in r.message
    assert r.event_json is not None


# --- 3. 端点守卫 ---

def test_get_timeline_endpoint_returns_source_and_events(client, token):
    """批次9 GET /api/tasks/<id>/timeline 端点应返回 source + events 数组。"""
    from backend.tasks.progress_bus import register, report, clear

    tid = f"test_ep_{int(time.time())}"
    register(tid, lambda stage, msg: None)  # 只注册，不关心 reporter

    # 模拟批次8 dict event 上报到 progress_bus
    report(tid, "research", {
        "type": "tool_start", "tool": "get_price", "idx": 1,
        "_fmt": "▶ [1/2] 调 get_price…",
    })
    report(tid, "research", {
        "type": "tool_end", "tool": "get_price", "idx": 1,
        "elapsed_s": 2.3, "status": "ok",
        "_fmt": "⚡ [1/2] get_price → ok · 2.3s",
    })

    resp = client.get(f"/api/tasks/{tid}/timeline", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    inner = data["data"]
    assert inner.get("source") in ("memory", "db")
    assert isinstance(inner.get("events"), list)
    assert len(inner["events"]) >= 2

    clear(tid)


def test_get_timeline_unknown_task_returns_empty(client, token):
    """未知 task_id 应返回空 events 数组（200），而非 404。"""
    resp = client.get(
        "/api/tasks/nonexistent_xyz/timeline",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["data"]["events"] == []
    assert data["data"]["source"] in ("memory", "db")
