# -*- coding: utf-8 -*-
"""数据源停更检测（Direction #2）回归测试。

锁死的核心契约：
    一个源可能"今天 lag 才 5 天(还 warn)，但 as_of 已连续多日冻结"——这种"正在坏掉"
    的状态必须被 detect_stall 提前捕获（stalled），不等它滚到 stale(≥8天)才报警。
    且：无观测历史/异常时不得误报 stalled（避免"狼来了"）。

全部离线、确定性：用临时库注入合成观测历史，不读真实 11MB 信号文件。
"""
import datetime as _dt
import os
import sqlite3

import modules.data_health as dh


def _seed(tmp_path, rows):
    """在临时库注入合成观测历史。rows: [(source_key, observed_at, as_of, status, lag_days)]"""
    dh._DATA_DIR = str(tmp_path)
    p = dh._health_db_path()
    if os.path.exists(p):
        os.remove(p)
    dh._ensure_health_table()
    with sqlite3.connect(p) as c:
        for r in rows:
            c.execute(
                "INSERT INTO data_source_health"
                "(source_key, observed_at, as_of, status, lag_days) VALUES (?,?,?,?,?)", r)


def _days_ago(n):
    return (_dt.date.today() - _dt.timedelta(days=n)).strftime("%Y-%m-%d")


def test_detect_stall_flags_frozen_source():
    """as_of 冻结 ≥STALL_DAYS 天且未推进到今日 → stalled=True（提前于 stale 报警）。"""
    import tempfile
    d = tempfile.mkdtemp()
    # 最后两次观测 as_of 都是 2026-09-01，最后推进观测在 ~10 天前 → 冻结≥5天
    _seed(d, [
        ("p1_event", f"{_days_ago(10)} 09:00:00", "2026-09-01", "stale", 8),
        ("p1_event", f"{_days_ago(3)} 09:00:00", "2026-09-01", "stale", 14),
    ])
    st = dh.detect_stall("p1_event")
    assert st["p1_event"]["stalled"] is True, "冻结源应判停更"
    assert st["p1_event"]["frozen_days"] is not None and st["p1_event"]["frozen_days"] >= dh.STALL_DAYS


def test_detect_stall_not_false_alarm_when_fresh():
    """as_of 已推进到今日 → 即便只有 1 次观测也不应 stalled。"""
    import tempfile
    d = tempfile.mkdtemp()
    _seed(d, [("p1_event", f"{_days_ago(0)} 09:00:00", _days_ago(0), "ok", 0)])
    st = dh.detect_stall("p1_event")
    assert st["p1_event"]["stalled"] is False


def test_detect_stall_no_history_is_not_stalled():
    """没有任何观测历史 → stalled=False（不误报）。"""
    import tempfile
    d = tempfile.mkdtemp()
    _seed(d, [])  # 空表
    st = dh.detect_stall("p1_event")
    assert st["p1_event"]["stalled"] is False


def test_detect_stall_frozen_but_recent_advance_not_stalled():
    """as_of 冻结了，但"最后推进日"就在最近（源刚停更不足阈值）→ 不误报。"""
    import tempfile
    d = tempfile.mkdtemp()
    # 最后推进观测在 2 天前、as_of=当天-2，之后没新数据，但冻结<STALL_DAYS
    _seed(d, [
        ("p1_event", f"{_days_ago(2)} 09:00:00", _days_ago(2), "ok", 2),
        ("p1_event", f"{_days_ago(1)} 09:00:00", _days_ago(2), "ok", 2),
    ])
    st = dh.detect_stall("p1_event")
    assert st["p1_event"]["stalled"] is False, "刚停更不足阈值不应报停更"


def test_record_health_observation_writes_and_idempotent(monkeypatch):
    """record_health_observation 把当前快照落盘；重复调用=再追加一行（不伪造成功）。"""
    import tempfile
    d = tempfile.mkdtemp()
    dh._DATA_DIR = d
    # 用固定小集合替代真实 health_rows（避免读 11MB 信号文件 / 真实 CSV）
    monkeypatch.setattr(dh, "health_rows", lambda: [
        {"key": "p1_event", "name": "P1 事件因子", "as_of": "2026-09-01",
         "lag_days": 14, "status": "stale"},
    ])
    n1 = dh.record_health_observation()
    n2 = dh.record_health_observation()
    assert n1 == 1 and n2 == 1, "每次应写入 1 行"
    p = dh._health_db_path()
    with sqlite3.connect(p) as c:
        cnt = c.execute("SELECT count(*) FROM data_source_health").fetchone()[0]
    assert cnt == 2, "两次调用应共写入 2 行"


def test_health_rows_enriched_carries_stalled(monkeypatch):
    """health_rows_enriched 在 health_rows 基础上合并 stalled 标记（供 SLA 看板）。"""
    import tempfile
    d = tempfile.mkdtemp()
    dh._DATA_DIR = d
    _seed(d, [
        ("p1_event", f"{_days_ago(10)} 09:00:00", "2026-09-01", "stale", 8),
        ("p1_event", f"{_days_ago(3)} 09:00:00", "2026-09-01", "stale", 14),
    ])
    monkeypatch.setattr(dh, "health_rows", lambda: [
        {"key": "p1_event", "name": "P1 事件因子", "as_of": "2026-09-01",
         "lag_days": 14, "status": "stale"},
    ])
    rows = dh.health_rows_enriched()
    p1 = next(r for r in rows if r["key"] == "p1_event")
    assert p1["stalled"] is True
    assert p1["frozen_days"] is not None


def test_build_refresh_plan_includes_stalled(monkeypatch):
    """刷新计划应纳入 stalled 源（即便 lag 还没到 stale），提前触发刷新。"""
    import tempfile
    d = tempfile.mkdtemp()
    dh._DATA_DIR = d
    _seed(d, [
        ("p1_event", f"{_days_ago(10)} 09:00:00", "2026-09-01", "warn", 5),
        ("p1_event", f"{_days_ago(3)} 09:00:00", "2026-09-01", "warn", 5),
    ])
    # health_rows_enriched 走真实 health_rows；用固定值避免读真实文件
    monkeypatch.setattr(dh, "health_rows", lambda: [
        {"key": "p1_event", "name": "P1 事件因子", "as_of": "2026-09-01",
         "lag_days": 5, "status": "warn"},
    ])
    plan = dh.build_refresh_plan(stale_only=True)
    covers = [s for p in plan for s in p["covers"]]
    assert "P1 事件因子" in covers, "停更源应进入刷新计划"
