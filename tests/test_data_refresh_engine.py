"""
tests/test_data_refresh_engine.py
---------------------------------
T-324 方向A②「数据源每日自动刷新调度器」契约守卫。

覆盖 AC：
- **AC1 测试隔离**：pytest / TESTING / ``STOCKSIGNAL_ENABLE_DATA_REFRESH=0`` 三闸门不启动
  调度线程；``_SCHEDULER_STARTED`` 防重入。
- **AC2 超时杀进程树**：子进程超 20 分钟 → ``taskkill /T /F``（kill_fn 注入验证）。
- **AC3 产出校验以 CSV 末行为准**：退出码仅参考（非零+推进→ok；超时杀+推进→ok；
  正常退出无推进→no_new_data；失败→failed）。绝不粉饰。
- **AC4 P1 停更告警**：lag ≥ ``modules.decision.FRESH_STALE_DAYS``（单一真理源）→
  MarketAlert 落库，消息含「需 sj 空间（P1-QuantFactor）重训导出」诚实提示；24h 去重。
- **AC5 状态文件**：原子写 + 当日成功后不重复触发；失败当日有限重试（上限 3 次）。
- **AC6 失败留痕**：失败必须 logger.error，不静默；状态如实记 failed。

所有用例离线（注入 fake popen / csv 末行序列 / health_rows），不触网、不真跑刷新脚本。
"""
from __future__ import annotations

import inspect
import json
import logging
import subprocess
import os
import sys
import threading
from datetime import date, datetime, time as dtime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

import backend.data_refresh_engine as dre  # noqa: E402


# ─────────────────────────── 工具 ───────────────────────────
class _DummyApp:
    """最小 app 桩：调度器只需 config 与 logger。"""

    def __init__(self, testing: bool = True):
        self.config = {"TESTING": testing}
        self.logger = logging.getLogger("dummy.data_refresh")


def _weekday_evening() -> datetime:
    """最近的未来工作日 18:00（时钟相对，不硬编码日期）。"""
    d = date.today()
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime.combine(d, dtime(18, 0))


def _weekday_morning() -> datetime:
    return datetime.combine(_weekday_evening().date(), dtime(10, 0))


def _weekend_evening() -> datetime:
    d = date.today()
    while d.weekday() < 5:
        d += timedelta(days=1)
    return datetime.combine(d, dtime(18, 0))


class _FakeProc:
    """Popen 桩：wait 可按预设返回码；kill 前抛 TimeoutExpired 模拟超时。"""

    def __init__(self, rc: int = 0, hang_until_killed: bool = False):
        self.pid = 424242
        self._rc = rc
        self._hang = hang_until_killed
        self._killed = False
        self.wait_timeouts: list = []

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if self._hang and not self._killed:
            raise subprocess.TimeoutExpired(cmd="refresh", timeout=timeout)
        return self._rc


@pytest.fixture(autouse=True)
def _reset_gate():
    dre._SCHEDULER_STARTED = False
    yield
    dre._SCHEDULER_STARTED = False


@pytest.fixture
def app(tmp_path):
    """真 Flask app（独立 sqlite 库，不碰老板常驻库）。"""
    from backend.app import create_app
    from backend.config import Config
    from backend.extensions import db
    from backend.models import User

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'data_refresh.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        if User.query.filter_by(username="admin").first() is None:
            u = User(username="admin", role="admin")
            u.set_password("Pass@123")
            db.session.add(u)
        db.session.commit()
    yield application


# ─────────────────────── AC3 产出校验（纯函数） ───────────────────────
@pytest.mark.parametrize("rc,advanced,killed,expected", [
    (1, True, False, "ok"),            # 退出码仅参考：非零但末行推进 → ok
    (None, True, True, "ok"),          # 超时强杀但产出已落盘 → ok
    (0, False, False, "no_new_data"),  # 正常退出无新行（节假日/数据源未发布）
    (1, False, False, "failed"),       # 取数失败 → 当日有限重试
    (None, False, True, "failed"),     # 超时且无产出
    (0, True, False, "ok"),            # 正常成功
])
def test_classify_result_advancement_is_authority(rc, advanced, killed, expected):
    assert dre.classify_result(rc, advanced, killed) == expected


def test_classify_result_docstring_honesty():
    """口径说明必须钉在源码里（防实现漂移后语义失传）。"""
    src = inspect.getsource(dre.classify_result)
    assert "末行推进" in src and "退出码仅参考" in src


# ─────────────────────── AC5 触发判定 + 状态文件 ───────────────────────
def test_should_trigger_before_window():
    ok, why = dre.should_trigger({}, _weekday_morning())
    assert not ok and "17:35" in why


def test_should_trigger_weekend():
    ok, why = dre.should_trigger({}, _weekend_evening())
    assert not ok and "17:35" in why


def test_should_trigger_first_time_evening():
    ok, why = dre.should_trigger({}, _weekday_evening())
    assert ok and why == "ok"


def test_should_trigger_skips_when_done_today():
    now = _weekday_evening()
    state = {"last_run_date": now.strftime("%Y-%m-%d"), "last_result": "ok"}
    ok, why = dre.should_trigger(state, now)
    assert not ok and "当日已完成" in why
    state["last_result"] = "no_new_data"
    ok2, why2 = dre.should_trigger(state, now)
    assert not ok2 and "当日已完成" in why2


def test_should_trigger_retry_then_cap():
    """失败 → 允许当日重试；达上限后停手（防反复撞网）。"""
    now = _weekday_evening()
    run_date = now.strftime("%Y-%m-%d")
    st1 = {"last_run_date": run_date, "last_result": "failed", "attempts_today": 1}
    assert dre.should_trigger(st1, now)[0] is True
    st_cap = {"last_run_date": run_date, "last_result": "failed",
              "attempts_today": dre.MAX_ATTEMPTS_PER_DAY}
    ok, why = dre.should_trigger(st_cap, now)
    assert not ok and "上限" in why


def test_should_trigger_yesterday_state_does_not_block():
    now = _weekday_evening()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    state = {"last_run_date": yesterday, "last_result": "ok",
             "attempts_today": dre.MAX_ATTEMPTS_PER_DAY}
    ok, why = dre.should_trigger(state, now)
    assert ok and why == "ok"


def test_state_roundtrip_atomic(tmp_path):
    p = str(tmp_path / "state.json")
    dre.save_state({"last_run_date": "2026-01-01", "last_result": "ok"}, p)
    assert dre.load_state(p)["last_result"] == "ok"
    # 空文件 / 坏 JSON → 空状态（诚实降级，不崩）
    assert dre.load_state(str(tmp_path / "missing.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert dre.load_state(str(bad)) == {}


def test_state_holds_no_unreplaced_placeholders(tmp_path):
    """状态文件必须真实可解码（防并发写坏整文件的前科）。"""
    p = tmp_path / "state.json"
    dre.save_state({"last_run_date": date.today().strftime("%Y-%m-%d"),
                    "last_result": "no_new_data"}, str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["last_result"] == "no_new_data"


# ─────────────────────── AC2 超时杀进程树 ───────────────────────
def test_timeout_kills_process_tree(tmp_path):
    proc = _FakeProc(rc=1, hang_until_killed=True)
    kills: list[int] = []

    def _kill(pid):
        kills.append(pid)
        proc._killed = True

    rc, killed = dre._spawn_and_wait(
        ["python", "-c", "pass"], popen_fn=lambda cmd, logf: proc,
        kill_fn=_kill, timeout=5)
    assert killed is True
    assert kills == [424242]
    assert rc == 1
    # 首次 wait 用的就是调用方超时；强杀后还有一次收尸 wait
    assert proc.wait_timeouts[0] == 5


def test_normal_completion_no_kill(tmp_path):
    proc = _FakeProc(rc=0)
    kills: list[int] = []
    rc, killed = dre._spawn_and_wait(
        ["python", "-c", "pass"], popen_fn=lambda cmd, logf: proc,
        kill_fn=lambda pid: kills.append(pid), timeout=5)
    assert rc == 0 and killed is False and kills == []


def test_refresh_cmd_shape(tmp_path, monkeypatch):
    """子进程命令必须指向增量刷新脚本（-m 模块入口 + --since + --workers）。"""
    d0 = date.today() - timedelta(days=3)
    seq = [d0, d0]
    monkeypatch.setattr(dre, "csv_last_date", lambda path=None: seq.pop(0))
    monkeypatch.setattr(dre, "alert_p1_stale", lambda app: False)
    seen = {}

    def _popen(cmd, logf):
        seen["cmd"] = list(cmd)
        return _FakeProc(rc=1)

    rec = dre.run_refresh_once(None, state_path=str(tmp_path / "s.json"),
                               popen_fn=_popen, kill_fn=lambda pid: None)
    cmd = seen["cmd"]
    assert cmd[:3] == [sys.executable, "-m", "scripts.refresh_shepherd_history_recent"]
    i = cmd.index("--since")
    expect = (d0 - timedelta(days=dre.SINCE_BACKWARD_DAYS)).strftime("%Y-%m-%d")
    assert cmd[i + 1] == expect
    assert cmd[cmd.index("--workers") + 1] == str(dre.WORKERS)
    # exit=1 且末行未推进 → failed（诚实）
    assert rec["result"] == "failed"


# ─────────────────────── AC3/AC5/AC6 run_refresh_once 集成 ───────────────────────
def test_advancement_beats_nonzero_exit(tmp_path, monkeypatch):
    """退出码仅参考：exit=1 但 CSV 末行推进 → ok（产出已落盘）。"""
    d0 = date.today() - timedelta(days=1)
    d1 = date.today()
    seq = [d0, d1]
    monkeypatch.setattr(dre, "csv_last_date", lambda path=None: seq.pop(0))
    monkeypatch.setattr(dre, "alert_p1_stale", lambda app: False)
    rec = dre.run_refresh_once(None, state_path=str(tmp_path / "s.json"),
                               popen_fn=lambda cmd, logf: _FakeProc(rc=1),
                               kill_fn=lambda pid: None)
    assert rec["result"] == "ok"
    st = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert st["last_result"] == "ok"
    assert st["last_csv_date"] == str(d0)


def test_no_new_data_counts_as_done(tmp_path, monkeypatch):
    """正常退出无推进 → no_new_data（当日完成，防节假日重试风暴）。"""
    d = date.today()
    seq = [d, d]
    monkeypatch.setattr(dre, "csv_last_date", lambda path=None: seq.pop(0))
    monkeypatch.setattr(dre, "alert_p1_stale", lambda app: False)
    rec = dre.run_refresh_once(None, state_path=str(tmp_path / "s.json"),
                               popen_fn=lambda cmd, logf: _FakeProc(rc=0),
                               kill_fn=lambda pid: None)
    assert rec["result"] == "no_new_data"
    # 生产上 run 只发生在工作日晚间 → 「当日已完成」用同一工作日晚间判定
    wd = _weekday_evening()
    st = {"last_run_date": wd.strftime("%Y-%m-%d"), "last_result": "no_new_data"}
    ok, why = dre.should_trigger(st, wd)
    assert not ok and "当日已完成" in why


def test_unreadable_csv_refuses_blind_run(tmp_path, monkeypatch, caplog):
    """AC6：基线读不到 → 拒绝盲跑（不猜 since）+ logger.error 留痕。"""
    monkeypatch.setattr(dre, "csv_last_date", lambda path=None: None)
    monkeypatch.setattr(dre, "alert_p1_stale", lambda app: False)
    with caplog.at_level(logging.ERROR, logger="backend.data_refresh_engine"):
        rec = dre.run_refresh_once(None, state_path=str(tmp_path / "s.json"))
    assert rec["result"] == "failed"
    assert "拒绝盲跑" in rec["detail"]
    assert any("刷新失败" in r.getMessage() for r in caplog.records)
    st = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert st["last_result"] == "failed"
    assert st["attempts_today"] == 1


def test_failed_run_logged_not_silenced(tmp_path, monkeypatch, caplog):
    """AC6：子进程失败必须 logger.error（不静默、不粉饰）。"""
    d = date.today()
    seq = [d, d]
    monkeypatch.setattr(dre, "csv_last_date", lambda path=None: seq.pop(0))
    monkeypatch.setattr(dre, "alert_p1_stale", lambda app: False)
    with caplog.at_level(logging.ERROR, logger="backend.data_refresh_engine"):
        rec = dre.run_refresh_once(None, state_path=str(tmp_path / "s.json"),
                                   popen_fn=lambda cmd, logf: _FakeProc(rc=1),
                                   kill_fn=lambda pid: None)
    assert rec["result"] == "failed"
    assert any("刷新失败" in r.getMessage() for r in caplog.records)


def test_attempts_increment_and_reset_by_date(tmp_path, monkeypatch):
    """attempts_today 同日累计；跨日重置由 should_trigger 的昨日态用例覆盖。"""
    d = date.today()
    seq = [d, d, d, d]  # 每次 run 消耗 before/after 两个读点
    monkeypatch.setattr(dre, "csv_last_date", lambda path=None: seq.pop(0))
    monkeypatch.setattr(dre, "alert_p1_stale", lambda app: False)
    sp = str(tmp_path / "s.json")
    rec1 = dre.run_refresh_once(None, state_path=sp,
                                popen_fn=lambda cmd, logf: _FakeProc(rc=1),
                                kill_fn=lambda pid: None)
    assert rec1["attempts_today"] == 1
    rec2 = dre.run_refresh_once(None, state_path=sp,
                                popen_fn=lambda cmd, logf: _FakeProc(rc=1),
                                kill_fn=lambda pid: None)
    assert rec2["attempts_today"] == 2
    st = dre.load_state(sp)
    assert st["last_run_date"] == rec2["run_date"]


def test_timeout_killed_no_advancement_is_failed(tmp_path, monkeypatch, caplog):
    """超时强杀且无产出 → failed（不粉饰成 ok）。"""
    d = date.today()
    seq = [d, d]
    monkeypatch.setattr(dre, "csv_last_date", lambda path=None: seq.pop(0))
    monkeypatch.setattr(dre, "alert_p1_stale", lambda app: False)
    rec = dre.run_refresh_once(None, state_path=str(tmp_path / "s.json"),
                               popen_fn=lambda cmd, logf: _FakeProc(rc=1, hang_until_killed=True),
                               kill_fn=lambda pid: None)
    assert rec["result"] == "failed"
    assert "killed=True" in rec["detail"]


# ─────────────────────── AC4 P1 停更告警 ───────────────────────
def _p1_rows(lag, as_of="2026-09-17"):
    return [{"key": "p1_event", "name": "P1 事件因子", "as_of": as_of,
             "lag_days": lag, "status": "stale"}]


def test_p1_alert_fires_with_sj_honest_hint(monkeypatch):
    monkeypatch.setattr("modules.data_health.health_rows",
                        lambda: _p1_rows(38, "2026-09-17"))
    calls = []
    ok = dre.alert_p1_stale(None, exists_fn=lambda: False,
                            add_fn=lambda msg, lag: calls.append((msg, lag)))
    assert ok is True
    msg, lag = calls[0]
    assert lag == 38
    # 诚实提示：跨仓依赖 + 只读红线 + 需重训导出，绝不含糊
    for token in ("P1-QuantFactor", "sj", "重训", "只读", "2026-09-17"):
        assert token in msg, f"告警消息缺少诚实要素「{token}」：{msg}"


def test_p1_alert_threshold_uses_decision_single_source(monkeypatch):
    """阈值必须引用 modules.decision.FRESH_STALE_DAYS（边界：±1 行为翻转）。"""
    from modules.decision import FRESH_STALE_DAYS
    monkeypatch.setattr("modules.data_health.health_rows",
                        lambda: _p1_rows(FRESH_STALE_DAYS - 1))
    calls = []
    assert dre.alert_p1_stale(None, exists_fn=lambda: False,
                              add_fn=lambda m, l: calls.append(1)) is False
    monkeypatch.setattr("modules.data_health.health_rows",
                        lambda: _p1_rows(FRESH_STALE_DAYS))
    assert dre.alert_p1_stale(None, exists_fn=lambda: False,
                              add_fn=lambda m, l: calls.append(1)) is True
    assert len(calls) == 1


def test_p1_alert_no_fire_when_lag_not_int(monkeypatch):
    monkeypatch.setattr("modules.data_health.health_rows",
                        lambda: _p1_rows(None))
    assert dre.alert_p1_stale(None, exists_fn=lambda: False,
                              add_fn=lambda m, l: None) is False


def test_p1_alert_dedup_24h(monkeypatch):
    """24h 内已有同源告警 → 不重复落库。"""
    monkeypatch.setattr("modules.data_health.health_rows", lambda: _p1_rows(38))
    calls = []
    assert dre.alert_p1_stale(None, exists_fn=lambda: True,
                              add_fn=lambda m, l: calls.append(1)) is False
    assert calls == []


def test_p1_alert_default_db_write(app):
    """默认路径：真实落库 MarketAlert（severity=warning，值=lag，阈值=FRESH_STALE_DAYS）。"""
    from modules.decision import FRESH_STALE_DAYS
    from backend.extensions import db
    from backend.models import MarketAlert
    monkey_rows = _p1_rows(38, "2026-09-17")
    import modules.data_health as dh
    orig = dh.health_rows
    dh.health_rows = lambda: monkey_rows
    try:
        with app.app_context():
            assert dre.alert_p1_stale(app) is True
            row = MarketAlert.query.filter_by(metric_key="p1_event").one()
            assert row.severity == "warning"
            assert row.value == 38.0
            assert row.threshold == float(FRESH_STALE_DAYS)
            assert "P1-QuantFactor" in row.message
            # 24h 内第二条不落库（DB 去重生效）
            assert dre.alert_p1_stale(app) is False
            assert MarketAlert.query.filter_by(metric_key="p1_event").count() == 1
    finally:
        dh.health_rows = orig


# ─────────────────────── AC1 测试隔离 + 接线 ───────────────────────
def test_scheduler_skipped_under_pytest():
    before = {t.name for t in threading.enumerate()}
    dre.start_data_refresh_scheduler(_DummyApp(testing=True))
    after = {t.name for t in threading.enumerate()}
    assert "data-refresh-scheduler" not in (after - before)
    assert dre._SCHEDULER_STARTED is False


def test_scheduler_skipped_when_env_disabled(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("STOCKSIGNAL_ENABLE_DATA_REFRESH", "0")
    before = {t.name for t in threading.enumerate()}
    dre.start_data_refresh_scheduler(_DummyApp(testing=False))
    after = {t.name for t in threading.enumerate()}
    assert "data-refresh-scheduler" not in (after - before)
    assert dre._SCHEDULER_STARTED is False


def test_scheduler_idempotent(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    dre._SCHEDULER_STARTED = True
    before = {t.name for t in threading.enumerate()}
    dre.start_data_refresh_scheduler(_DummyApp(testing=False))
    assert "data-refresh-scheduler" not in {t.name for t in threading.enumerate()} - before


def test_scheduler_starts_thread_when_enabled(monkeypatch):
    """三闸门全开 → 守护线程真的被构造并 start（防假绿）。

    用 Thread spy 而非 enumerate 轮询：轮询在重负载全量回归下时序 flaky
    （本用例实测定向绿/全量红），spy 断言无时序依赖且同时钉住 daemon 语义。
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("STOCKSIGNAL_ENABLE_DATA_REFRESH", "1")
    calls = []

    class _SpyThread:
        def __init__(self, *, target=None, daemon=None, name=None, **kw):
            calls.append({"name": name, "daemon": daemon, "started": False})
            self._target = target

        def start(self):
            calls[-1]["started"] = True

    monkeypatch.setattr(dre.threading, "Thread", _SpyThread)
    dre.start_data_refresh_scheduler(_DummyApp(testing=False), initial_delay=3600)
    assert len(calls) == 1
    assert calls[0]["name"] == "data-refresh-scheduler"
    assert calls[0]["daemon"] is True
    assert calls[0]["started"] is True


def test_app_wires_data_refresh_scheduler():
    """接线守卫：backend/app.py 必须挂 start_data_refresh_scheduler（防被静默摘除）。"""
    import backend.app as app_mod
    src = inspect.getsource(app_mod)
    assert "start_data_refresh_scheduler" in src
    assert "STOCKSIGNAL_ENABLE_DATA_REFRESH" not in src  # 闸门在引擎内，勿重复
