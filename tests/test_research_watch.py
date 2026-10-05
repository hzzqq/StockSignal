"""
tests/test_research_watch.py
----------------------------
H1+ 方向 B「研究智能体定时自驱盯盘」契约守卫（T-213）。

覆盖 spec `docs/H1plus-溯源底座与自驱盯盘-spec.md` 的 AC：
- **AC-B1 只读红线**：组装问题不含操作指令；默认研究委托 H1 `research_agent.run_research`
  （自带只读红线），本模块不另起写链。
- **AC-B2 有界**：全局配额 + 冷却去重 → 同一窗口多告警至多研究 1 次。
- **AC-B3 诚实降级**：研究 status 原样透传（unavailable 不粉饰为 ok）。
- **AC-B4 测试隔离**：pytest / 禁用环境变量下不启动调度线程。
- **AC-B5 可追溯**：落库 `research_runs` 含触发原因 + citations，查询端点可读。
- **AC-B6 时段与去重**：复用 alert 引擎交易时段判定；已研究过的告警不再重复取用。

所有用例纯离线（注入 fake research_fn / fake persist_fn），不触网、不调用真实 LLM。
"""
from __future__ import annotations

import inspect
import os
import sys
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

import backend.research_watch as rw  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import MarketAlert, ResearchRun, User  # noqa: E402


# ─────────────────────────── 夹具 ───────────────────────────
@pytest.fixture(autouse=True)
def _reset_gate():
    """隔离进程内配额/冷却状态，避免用例间相互污染。"""
    rw._last_global_ts = 0.0
    rw._last_trigger_ts.clear()
    yield
    rw._last_global_ts = 0.0
    rw._last_trigger_ts.clear()


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'research.db'}"
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
    try:
        from backend.utils.ratelimit import reset_rate_limit as _r
        _r()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def client(app):
    return app.test_client()


def _token(client, username="demo"):
    r = client.post("/api/auth/login", json={"username": username, "password": "Pass@123"})
    assert r.status_code == 200, f"login failed: {r.status_code}"
    return r.get_json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_research(status="ok", citations=None, limitations=None):
    def _fn(question, **kwargs):
        return {
            "status": status,
            "answer": f"研究答复({status})",
            "citations": citations if citations is not None else [{"id": "S1", "title": "t"}],
            "limitations": limitations if limitations is not None else [],
            "steps": [],
        }
    return _fn


# ─────────────────────── AC-B1 只读红线 ───────────────────────
def test_build_question_is_readonly():
    q = rw.build_question({
        "metric_key": "adr", "metric_name": "涨跌比率(ADR)",
        "severity": "danger", "message": "个股普跌", "value": 0.35,
    })
    assert "涨跌比率(ADR)" in q
    assert "0.35" in q
    # 显式声明不提供操作建议
    assert "不给出任何交易操作建议" in q
    # 不含任何下单/仓位动作动词
    for w in ("买入", "卖出", "下单", "清仓", "建仓", "加仓", "减仓", "委托"):
        assert w not in q, f"只读红线被破坏：问题含操作动词「{w}」"


def test_research_fn_receives_only_readonly_kwargs():
    seen = {}

    def _spy(question, **kwargs):
        seen["question"] = question
        seen["kwargs"] = kwargs
        return {"status": "ok", "answer": "", "citations": [], "limitations": [], "steps": []}

    rw.run_watch_once(
        alert={"metric_key": "adr", "metric_name": "ADR", "severity": "warning", "id": 1},
        research_fn=_spy, persist_fn=None,
    )
    # 只透传有界参数，绝不注入写操作工具
    assert set(seen["kwargs"]) <= {"max_steps", "budget_s"}
    assert "不给出任何交易操作建议" in seen["question"]


def test_run_watch_once_delegates_to_h1_agent_by_default():
    """默认 research_fn 必须是 H1 research_agent.run_research（自带只读红线 + 有界 + 溯源）。"""
    src = inspect.getsource(rw.run_watch_once)
    assert "modules.research_agent" in src and "run_research" in src


def test_module_has_no_write_action_chain():
    src = inspect.getsource(rw)
    for bad in ("place_order", "submit_order", 'action="buy"', 'action="sell"', "conditional_orders"):
        assert bad not in src, f"只读红线被破坏：模块含写操作标记「{bad}」"


# ─────────────────────── AC-B3 诚实降级 ───────────────────────
@pytest.mark.parametrize("status", ["ok", "partial", "unavailable"])
def test_status_passthrough(status):
    rec = rw.run_watch_once(
        alert={"metric_key": "vix", "metric_name": "VIX恐慌指数", "id": 2},
        research_fn=_fake_research(status=status), persist_fn=None,
    )
    # 原样透传，绝不粉饰
    assert rec["status"] == status
    assert rec["citations"] == [{"id": "S1", "title": "t"}]


def test_missing_status_defaults_unavailable():
    rec = rw.run_watch_once(
        alert={"metric_key": "vix", "metric_name": "VIX恐慌指数"},
        research_fn=lambda q, **k: {}, persist_fn=None,
    )
    assert rec["status"] == "unavailable"


def test_persist_failure_does_not_fake_success():
    """落库失败须留痕，但研究记录仍如实反映 status（不谎报、不吞改）。"""
    def _boom(_record):
        raise RuntimeError("db down")

    rec = rw.run_watch_once(
        alert={"metric_key": "adr", "metric_name": "ADR", "id": 3},
        research_fn=_fake_research(status="unavailable"), persist_fn=_boom,
    )
    assert rec["status"] == "unavailable"


# ────────────────── AC-B2 / AC-B6 有界 + 去重 ──────────────────
def test_gate_global_quota_blocks_within_interval():
    now = 1_000_000.0
    ok, why = rw.gate_allows(now, "adr", last_global_ts=now - 60, last_trigger_ts={})
    assert not ok
    assert "配额" in why


def test_gate_global_quota_allows_after_interval():
    now = 1_000_000.0
    ok, _ = rw.gate_allows(now, "adr",
                           last_global_ts=now - rw.MIN_INTERVAL_SECONDS - 1,
                           last_trigger_ts={})
    assert ok


def test_gate_trigger_cooldown_blocks_same_source_only():
    now = 2_000_000.0
    lt = {"adr": now - 100}
    ok_same, why = rw.gate_allows(now, "adr", last_global_ts=0.0, last_trigger_ts=lt)
    assert not ok_same and "adr" in why
    ok_other, _ = rw.gate_allows(now, "vix", last_global_ts=0.0, last_trigger_ts=lt)
    assert ok_other


def test_gate_trigger_cooldown_recovers():
    now = 2_000_000.0
    lt = {"adr": now - rw.PER_TRIGGER_COOLDOWN_SECONDS - 1}
    ok, _ = rw.gate_allows(now, "adr", last_global_ts=0.0, last_trigger_ts=lt)
    assert ok


def test_multi_alert_same_window_at_most_one_run():
    """AC-B2：一批告警在同一配额窗口 → 至多研究 1 次。"""
    n = {"c": 0}

    def _fn(q, **k):
        n["c"] += 1
        return {"status": "ok", "answer": "", "citations": [], "limitations": [], "steps": []}

    now = 3_000_000.0
    for mk in ("adr", "vix", "adr"):
        ok, _why = rw.gate_allows(now, mk)
        if ok:
            rw.run_watch_once(alert={"metric_key": mk, "metric_name": mk, "id": 9},
                              research_fn=_fn, persist_fn=None)
            rw._mark_ran(now, mk)
    assert n["c"] == 1, f"同一窗口至多跑 1 次，实际 {n['c']}"
    assert rw._last_global_ts == now


def test_scheduler_uses_trading_window_guard():
    """AC-B6：调度循环复用 alert 引擎的交易时段判定。"""
    src = inspect.getsource(rw.start_research_watch_scheduler)
    assert "_in_trading_window" in src


# ─────────────────────── AC-B5 可追溯 ───────────────────────
def test_persist_run_and_query_endpoint(app, client):
    with app.app_context():
        rw.persist_run({
            "trigger": {"metric_key": "adr", "metric_name": "涨跌比率(ADR)",
                        "severity": "danger", "alert_id": 7},
            "question": "q", "status": "ok", "answer": "综合结论",
            "citations": [{"id": "S1", "title": "涨跌比率"}],
            "limitations": ["部分源缺失"],
        })
        assert ResearchRun.query.count() == 1

    tok = _token(client)
    r = client.get("/api/research-runs", headers=_auth(tok))
    obj = r.get_json(force=True)
    assert obj["status"] == "ok"
    assert obj["data"]["total"] == 1
    item = obj["data"]["items"][0]
    assert item["trigger_metric_key"] == "adr"
    assert item["status"] == "ok"
    assert item["citations"][0]["id"] == "S1"
    assert item["limitations"] == ["部分源缺失"]
    assert item["created_at"]


def test_endpoint_status_filter(app, client):
    with app.app_context():
        db.session.add(ResearchRun(trigger_metric_key="adr", question="q1", status="ok"))
        db.session.add(ResearchRun(trigger_metric_key="vix", question="q2", status="unavailable"))
        db.session.commit()
    tok = _token(client)
    d = client.get("/api/research-runs?status=unavailable", headers=_auth(tok)).get_json(force=True)["data"]
    assert d["total"] == 1
    assert d["items"][0]["trigger_metric_key"] == "vix"


def test_endpoint_requires_auth(client):
    r = client.get("/api/research-runs")
    assert r.status_code in (401, 403)


def test_latest_unprocessed_alert_excludes_researched(app):
    with app.app_context():
        db.session.add(MarketAlert(metric_key="adr", metric_name="ADR",
                                   severity="danger", message="m", value=2.0))
        db.session.commit()
        a1 = rw.latest_unprocessed_alert(app)
        assert a1 is not None and a1.metric_key == "adr"
        # 落一条引用该告警的研究记录 → 之后不再取用（AC-B6 去重）
        rw.persist_run({
            "trigger": {"metric_key": "adr", "metric_name": "ADR",
                        "severity": "danger", "alert_id": a1.id},
            "question": "q", "status": "ok", "answer": "", "citations": [], "limitations": [],
        })
        assert rw.latest_unprocessed_alert(app) is None


# ─────────────────────── AC-B4 测试隔离 ───────────────────────
def test_scheduler_skipped_under_pytest(app):
    """pytest 环境下（PYTEST_CURRENT_TEST / TESTING）不得启动调度线程。"""
    rw._SCHEDULER_STARTED = False
    before = {t.name for t in threading.enumerate()}
    rw.start_research_watch_scheduler(app)
    after = {t.name for t in threading.enumerate()}
    assert "research-watch-scheduler" not in (after - before)
    assert rw._SCHEDULER_STARTED is False


def test_scheduler_skipped_when_env_disabled(app, monkeypatch):
    rw._SCHEDULER_STARTED = False
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("STOCKSIGNAL_ENABLE_RESEARCH_WATCH", "0")
    app.config["TESTING"] = False
    before = {t.name for t in threading.enumerate()}
    rw.start_research_watch_scheduler(app)
    after = {t.name for t in threading.enumerate()}
    assert "research-watch-scheduler" not in (after - before)
    assert rw._SCHEDULER_STARTED is False


# ─────────────────── T-216 桌面通知 + 手动触发端点 ───────────────────
def test_notify_run_disabled_by_env(monkeypatch):
    """STOCKSIGNAL_RESEARCH_NOTIFY=0 → 不触发桌面通知（防测试真弹窗）。"""
    monkeypatch.setenv("STOCKSIGNAL_RESEARCH_NOTIFY", "0")
    import backend.desktop_notify as dn
    called = []
    monkeypatch.setattr(dn, "notify", lambda t, m: called.append((t, m)))
    rw.notify_run({"metric_name": "ADR"}, {"status": "ok"})
    assert called == []


def test_notify_run_calls_desktop_notify(monkeypatch):
    """默认开 → 经 backend.desktop_notify.notify 弹出（异步），失败只留痕。"""
    monkeypatch.delenv("STOCKSIGNAL_RESEARCH_NOTIFY", raising=False)
    import backend.desktop_notify as dn
    called = []
    monkeypatch.setattr(dn, "notify", lambda t, m: called.append((t, m)))
    rw.notify_run({"metric_name": "VIX恐慌指数"}, {"status": "unavailable"})
    assert len(called) == 1
    t, m = called[0]
    assert "VIX恐慌指数" in m and "unavailable" in m


def test_notify_run_failure_does_not_raise(monkeypatch):
    monkeypatch.delenv("STOCKSIGNAL_RESEARCH_NOTIFY", raising=False)
    import backend.desktop_notify as dn

    def _boom(t, m):
        raise RuntimeError("no user32")

    monkeypatch.setattr(dn, "notify", _boom)
    rw.notify_run({"metric_key": "adr"}, {"status": "ok"})  # 不应抛


def test_scheduler_notifies_on_completion():
    """调度循环研究完成后必须调 notify_run（防通知链路被静默摘除）。"""
    src = inspect.getsource(rw.start_research_watch_scheduler)
    assert "notify_run(a, rec)" in src


def test_manual_run_requires_admin(app, client):
    r = client.post("/api/research-runs/run")
    assert r.status_code in (401, 403)
    tok = _token(client, "demo")
    r2 = client.post("/api/research-runs/run", headers=_auth(tok))
    assert r2.status_code == 403


def test_manual_run_honest_when_no_alert(app, client, monkeypatch):
    monkeypatch.setenv("STOCKSIGNAL_RESEARCH_NOTIFY", "0")
    admin_tok = _token(client, "admin")
    r = client.post("/api/research-runs/run", headers=_auth(admin_tok))
    obj = r.get_json(force=True)
    assert obj["status"] == "ok"
    assert obj["data"]["ran"] is False
    assert "无未处理告警" in obj["data"]["reason"]


def test_manual_run_executes_and_persists(app, client, monkeypatch):
    """有未处理告警 → 同步跑一轮：落库 + status 原样透传 + 标记已跑。"""
    monkeypatch.setenv("STOCKSIGNAL_RESEARCH_NOTIFY", "0")
    monkeypatch.setattr(
        "modules.research_agent.run_research",
        lambda q, **k: {"status": "partial", "answer": "a", "citations": [{"id": "S1"}],
                        "limitations": ["限"], "steps": []})
    with app.app_context():
        db.session.add(MarketAlert(metric_key="pcr", metric_name="PCR(认沽/认购比)",
                                   severity="warning", message="避险", value=1.1))
        db.session.commit()
    admin_tok = _token(client, "admin")
    r = client.post("/api/research-runs/run", headers=_auth(admin_tok))
    obj = r.get_json(force=True)
    assert obj["status"] == "ok" and obj["data"]["ran"] is True
    rec = obj["data"]["record"]
    assert rec["status"] == "partial" and rec["citations"][0]["id"] == "S1"
    # 落库可查 + 该告警已被消费（重复触发 → 诚实 ran=False）
    with app.app_context():
        assert ResearchRun.query.count() == 1
        assert rw.latest_unprocessed_alert(app) is None
    r2 = client.post("/api/research-runs/run", headers=_auth(admin_tok))
    assert r2.get_json(force=True)["data"]["ran"] is False
