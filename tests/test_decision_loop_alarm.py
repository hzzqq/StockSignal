"""决策闭环主动报警守卫（方向 #②，根治 09-10/09-15 静默停摆）。

锁定不变量：
- assess_decision_loop_health 返回结构化分级：ok/warn/stale/dead/unknown
- 快照 >48h 未更新 -> dead（调度死）；缺失文件 -> dead
- 交易日/非交易日按交易日历判定：周末与节假日前移不误报 stale
- 新鲜快照 -> ok
- render_decision_loop_alarm 按 status 正确映射到 红/橙/绿 盒子
全部离线（monkeypatch 本地快照 + time），不触网。
"""

import datetime as _dtmod
import json
import time as _time

import pytest

import modules.decision as D
import modules.decision_view as dv


def _patch(monkeypatch, tmp_path, snap, mtime_epoch, now_epoch):
    # 把 SNAPSHOT_PATH 指向临时真实文件，确保 os.path.exists 通过
    sp = tmp_path / "daily_snapshot.json"
    sp.write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr(D, "SNAPSHOT_PATH", str(sp))
    monkeypatch.setattr(D, "load_snapshot", lambda *a, **k: snap)
    monkeypatch.setattr(D.os.path, "getmtime", lambda p: mtime_epoch)
    monkeypatch.setattr(_time, "time", lambda: now_epoch)

    # T-128：assess_decision_loop_health 在快照带 generated_at 时改用 datetime.now()
    # 计算 gen_lag（modules/decision.py），time.time 补丁盖不住该旁路 → 冻结 datetime。
    class _FrozenDatetime(_dtmod.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dtmod.datetime.fromtimestamp(now_epoch, tz)

    monkeypatch.setattr(_dtmod, "datetime", _FrozenDatetime)


def test_health_ok_for_fresh_snapshot(monkeypatch, tmp_path):
    snap = {"generated_at": "2026-09-16T09:00:00", "as_of": "2026-09-15"}
    now = _time.mktime(_time.strptime("2026-09-16 12:00:00", "%Y-%m-%d %H:%M:%S"))
    _patch(monkeypatch, tmp_path, snap, now - 3 * 3600, now)
    h = D.assess_decision_loop_health()
    assert h["status"] == "ok", h
    assert h["rank"] == 0
    assert "正常" in h["message"]


def test_health_ok_on_weekend_when_last_trading_day_snapshot_exists(monkeypatch, tmp_path):
    """2026-11-21 周六假警报回归：周五 15:31 已落盘，周末无新收盘，不得判 stale。"""
    snap = {"generated_at": "2026-11-20T15:31:34", "as_of": "2026-11-20"}
    now = _time.mktime(_time.strptime("2026-11-21 21:00:00", "%Y-%m-%d %H:%M:%S"))
    _patch(monkeypatch, tmp_path, snap, now - 29 * 3600, now)
    h = D.assess_decision_loop_health()
    assert h["status"] == "ok", h
    assert h["rank"] == 0
    assert h["gen_lag_hours"] >= 26  # 自然小时确实超阈值，但交易日历口径优先
    assert '非交易日' in h['message'] or '正常' in h['message']


def test_health_stale_when_trading_session_missed_even_if_hours_are_short(monkeypatch, tmp_path):
    """周一 18:30 仍停在周五数据日：即使距上次生成仅 10h，也已错过一个交易日。"""
    snap = {"generated_at": "2026-11-23T08:00:00", "as_of": "2026-11-20"}
    now = _time.mktime(_time.strptime("2026-11-23 18:30:00", "%Y-%m-%d %H:%M:%S"))
    _patch(monkeypatch, tmp_path, snap, now - 10 * 3600, now)
    h = D.assess_decision_loop_health()
    assert h["status"] == "stale", h
    assert h["rank"] == 2
    assert "错过 1 个交易日" in h["message"]


def test_health_dead_when_generated_at_old(monkeypatch, tmp_path):
    snap = {"generated_at": "2026-09-10T15:00:00", "as_of": "2026-09-09"}
    now = _time.mktime(_time.strptime("2026-09-16 12:00:00", "%Y-%m-%d %H:%M:%S"))
    _patch(monkeypatch, tmp_path, snap, now - 3 * 86400, now)  # mtime 3 天前
    h = D.assess_decision_loop_health()
    assert h["status"] == "dead", h
    assert h["rank"] == 3
    assert "停摆" in h["message"]


def test_health_missing_file_is_dead(monkeypatch, tmp_path):
    monkeypatch.setattr(D, "SNAPSHOT_PATH", str(tmp_path / "nope.json"))
    h = D.assess_decision_loop_health()
    assert h["status"] == "dead"
    assert h["rank"] == 3


def test_render_alarm_maps_status_to_box(monkeypatch):
    calls = []

    def _err(*a, **k):
        calls.append(("err",) + a)

    def _warn(*a, **k):
        calls.append(("warn",) + a)

    def _ok(*a, **k):
        calls.append(("ok",) + a)

    monkeypatch.setattr(dv, "xc_error_box", _err)
    monkeypatch.setattr(dv, "xc_warn_box", _warn)
    monkeypatch.setattr(dv, "xc_success_box", _ok)

    monkeypatch.setattr(D, "assess_decision_loop_health", lambda: {"status": "dead", "message": "x"})
    dv.render_decision_loop_alarm()
    assert calls[0][0] == "err", calls

    calls.clear()
    monkeypatch.setattr(D, "assess_decision_loop_health", lambda: {"status": "stale", "message": "y"})
    dv.render_decision_loop_alarm()
    assert calls[0][0] == "warn", calls

    calls.clear()
    monkeypatch.setattr(D, "assess_decision_loop_health", lambda: {"status": "warn", "message": "w"})
    dv.render_decision_loop_alarm()
    assert calls[0][0] == "warn", calls

    calls.clear()
    monkeypatch.setattr(D, "assess_decision_loop_health", lambda: {"status": "ok", "message": "z"})
    dv.render_decision_loop_alarm()
    assert calls[0][0] == "ok", calls
