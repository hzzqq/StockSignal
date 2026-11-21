"""pattern_scan 异步任务化守卫测试（team-lead 指定四项 + 提交端点）。

覆盖：
 1. 注册存在：task_worker handlers 里有 "pattern_scan"；
 2. handler 内部经 modules.fetch_parallel.fetch_many 并行取数（monkeypatch 断言调用与入参）；
 3. 进度上报：每完成一只经 progress_bus report(stage="scan")，消息含 [i/n] code；
 4. 诚实降级：单股取数失败（fetch_many 返回 None）→ available=false + reason，
    不中断整批、不补零、不伪造形态；
 5. 提交端点 POST /api/v2/pattern-scan/tasks：真 Flask test_client + 临时 SQLite + 真 JWT，
    返回 {task_id, status: "pending"}；校验失败 422；无 token 401；
    通用任务端点 POST /api/tasks/ 也接受 type="pattern_scan"。

夹具：K 线为合成确定性数据（非真实行情），与 test_pattern_scan.py 同款。
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

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402

import modules.fetch_parallel as fp  # noqa: E402
from backend.tasks import worker as w  # noqa: E402
from backend.tasks.progress_bus import register, clear  # noqa: E402


# ── 合成确定性 K 线夹具（非真实行情）：长期平稳 + 末端 V 形，稳定触发 MACD金叉 ──
def _flat_then_v_rows() -> list[dict]:
    vals = [100.0] * 60 + [90, 85, 80, 90, 100, 110, 120, 125]
    return [
        {
            "date": f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}",
            "open": c - 0.5, "high": c + 1.0, "low": c - 1.0, "close": c,
        }
        for i, c in enumerate(vals)
    ]


FLAT_V = _flat_then_v_rows()


# ───────────── 1. 注册存在 ─────────────
def test_pattern_scan_handler_registered():
    assert "pattern_scan" in w.task_worker._handlers, sorted(w.task_worker._handlers)


# ───────────── 2/3. fetch_many 并行取数 + 进度上报 ─────────────
def test_handler_uses_fetch_many_and_reports_progress(monkeypatch):
    calls: list[list[str]] = []

    def fake_fetch_many(tasks, max_workers=None, timeout=None):
        tasks = list(tasks)
        calls.append([key for key, _fn in tasks])
        # 取数被隔离：直接返回合成 K 线，不触发真实网络
        return {key: FLAT_V for key, _fn in tasks}

    monkeypatch.setattr(fp, "fetch_many", fake_fetch_many)

    events: list[tuple[str, str]] = []
    register("t-progress", lambda stage, msg: events.append((stage, str(msg))))
    try:
        out = w._handle_pattern_scan({
            "codes": ["600519", "000001"],
            "window_days": 120,
            "__task_id__": "t-progress",
        })
    finally:
        clear("t-progress")

    # 结果与同步端点 data 同构
    assert out["n_scanned"] == 2, out
    assert out["available"] is True, out
    assert [r["code"] for r in out["results"]] == ["600519", "000001"], out
    for r in out["results"]:
        assert r["available"] is True, r
        assert any(p["name"] == "MACD金叉" for p in r["patterns"]), r

    # fetch_many 被调用一次，任务按 codes 逐股下发
    assert calls == [["600519", "000001"]], calls

    # 进度上报：每完成一只一条 stage="scan"，消息含序号与代码
    scan_events = [e for e in events if e[0] == "scan"]
    assert len(scan_events) == 2, events
    assert "[1/2] 600519" in scan_events[0][1], scan_events
    assert "[2/2] 000001" in scan_events[1][1], scan_events


# ───────────── 4. 诚实降级 ─────────────
def test_handler_honest_degradation_on_fetch_failure(monkeypatch):
    # 取数失败 → fetch_many 预填 None 语义：单股 available=false + reason，不中断整批
    monkeypatch.setattr(
        fp, "fetch_many",
        lambda tasks, max_workers=None, timeout=None: {key: None for key, _fn in tasks},
    )
    out = w._handle_pattern_scan({"codes": ["600519", "000001"]})
    assert out["n_scanned"] == 2, out
    assert out["available"] is False, out
    for r in out["results"]:
        assert r["available"] is False, r
        assert r["patterns"] == [], r
        assert r["reason"], r
        assert r["n_bars"] == 0, r


def test_handler_mixed_outcome_does_not_abort(monkeypatch):
    # 一只失败一只成功：整批照常完成，失败股诚实降级
    def fake_fetch_many(tasks, max_workers=None, timeout=None):
        out = {}
        for key, fn in tasks:
            out[key] = RuntimeError() if key == "000001" else fn()
        out["000001"] = None  # 失败 → None
        return out

    monkeypatch.setattr(fp, "fetch_many", fake_fetch_many)
    out = w._handle_pattern_scan({"codes": ["600519", "000001"]})
    by_code = {r["code"]: r for r in out["results"]}
    assert by_code["600519"]["available"] is True, by_code
    assert by_code["000001"]["available"] is False, by_code
    assert by_code["000001"]["reason"], by_code
    assert out["available"] is True, out


def test_handler_invalid_payload_raises(monkeypatch):
    monkeypatch.setattr(fp, "fetch_many", lambda tasks, **kw: {})
    with pytest.raises(ValueError):
        w._handle_pattern_scan({"codes": []})
    with pytest.raises(ValueError):
        w._handle_pattern_scan({"codes": "600519"})


# ───────────── 5. 提交端点（真 Flask test_client + 临时 SQLite + JWT）─────────────
@pytest.fixture
def app(tmp_path, monkeypatch):
    db_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file.as_posix()}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    from backend.api.pattern_routes import bp as pattern_bp

    if "pattern" not in application.blueprints:
        application.register_blueprint(pattern_bp)

    with application.app_context():
        db.create_all()
        if User.query.filter_by(username="demo").first() is None:
            u = User(username="demo", role="user")
            u.set_password("Pass@123")
            db.session.add(u)
            db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Pass@123"})
    assert r.status_code == 200, f"登录失败: {r.status_code} {r.text[:300]}"
    token = r.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _patch_submit(monkeypatch, captured: dict):
    from backend.tasks.worker import task_worker

    def fake_submit(task_type, payload):
        captured["type"] = task_type
        captured["payload"] = payload
        return "fake-task-id"

    monkeypatch.setattr(task_worker, "submit", fake_submit)


def test_submit_task_endpoint_returns_task_id(client, auth, monkeypatch):
    captured: dict = {}
    _patch_submit(monkeypatch, captured)
    r = client.post(
        "/api/v2/pattern-scan/tasks",
        json={"codes": ["600519", "000001"], "window_days": 60},
        headers=auth,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["task_id"] == "fake-task-id" and d["status"] == "pending", d
    assert captured["type"] == "pattern_scan", captured
    assert captured["payload"] == {"codes": ["600519", "000001"], "window_days": 60}, captured


@pytest.mark.parametrize("body", [
    {"codes": []},
    {"codes": ["ABCDEF"]},
    {"codes": ["600519"] * 51},
    {"codes": "600519"},
    {"codes": ["600519"], "window_days": 0},
    {"codes": ["600519"], "window_days": "abc"},
    ["not-a-dict"],
])
def test_submit_task_invalid_body_422(client, auth, monkeypatch, body):
    captured: dict = {}
    _patch_submit(monkeypatch, captured)
    r = client.post("/api/v2/pattern-scan/tasks", json=body, headers=auth)
    assert r.status_code == 422, f"期望 422，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert j["status"] == "error" and j["code"] == "validation_error", j
    assert "type" not in captured, captured  # 校验失败不得进入 submit


def test_submit_task_no_token_401(client):
    r = client.post("/api/v2/pattern-scan/tasks", json={"codes": ["600519"]})
    assert r.status_code == 401, f"期望 401，实得 {r.status_code}: {r.text[:300]}"
    assert r.get_json()["status"] == "error", r.get_json()


def test_generic_task_endpoint_accepts_pattern_scan(client, auth, monkeypatch):
    captured: dict = {}
    _patch_submit(monkeypatch, captured)
    r = client.post(
        "/api/tasks/",
        json={"type": "pattern_scan", "payload": {"codes": ["600519"]}},
        headers=auth,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["task_id"] == "fake-task-id" and d["status"] == "pending", d
    assert captured["type"] == "pattern_scan", captured
