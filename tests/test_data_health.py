# -*- coding: utf-8 -*-
"""决策「全数据源健康」注册表 + 统一新鲜度判定测试（自找缺口 S9）。

锁死契约：
- DATA_SOURCES 覆盖全部决策相关源（牧羊人/P1事件/连板晋级率/事件池/市场温度/快照）。
- assess_all_sources 复用 assess_freshness：任一源陈旧 → 整体 stale；mtime 兜底源
  不参与「假新鲜」掩盖。
- 抽取器全部惰性强容错：monkeypatch 制造异常时返回 None（status=unknown），不崩看板。

全部离线、确定性；P1 事件因子走本地文件（不触网）。
"""
from __future__ import annotations

import datetime as _dt

import modules.data_health as DH


def _iso(days_ago: int) -> str:
    return (_dt.date.today() - _dt.timedelta(days=days_ago)).isoformat()


# ───────────────────────── 注册表完整性 ─────────────────────────
def test_registry_covers_all_decision_sources():
    keys = {e["key"] for e in DH.DATA_SOURCES}
    assert {"shepherd_sentiment", "p1_event", "ladder",
            "event_pool", "market_temp", "daily_snapshot"} <= keys
    # 每个源都有可解析的 kind
    assert all(e.get("kind") in ("csv_last_date", "json_date_field",
                                 "p1_latest_date", "mtime", "track_last_scored")
               for e in DH.DATA_SOURCES)


# ───────────────────────── 抽取器容错 ─────────────────────────
def test_csv_last_date_col_handles_missing_file(monkeypatch):
    assert DH._csv_last_date_col("/no/such/file.csv", 0) is None


def test_json_date_field_handles_corrupt(monkeypatch):
    assert DH._json_date_field("/no/such/file.json", "date") is None


def test_mtime_date_handles_missing(monkeypatch):
    assert DH._mtime_date("/no/such/file.db") is None


def test_p1_latest_date_fault_tolerant(monkeypatch):
    # P1SignalLoader 抛异常 → 返回 None（不崩）
    import modules.p1_signal as P1
    monkeypatch.setattr(P1, "P1SignalLoader", object)  # object() 不可调用
    assert DH._p1_event_latest_date() is None


# ───────────────────────── 统一判定：最坏源主导 ─────────────────────────
def test_assess_all_sources_worst_source_wins(monkeypatch):
    """仅一个源陈旧 → 整体 stale（避免被新鲜源掩盖）。"""
    fixed = {
        "牧羊人情绪": _iso(1), "P1 事件因子": _iso(1), "连板晋级率": _iso(1),
        "事件池": _iso(1), "市场温度缓存": _iso(1), "今日快照": _iso(1),
    }

    def fake_as_of(entry):
        return fixed.get(entry["name"], _iso(1))

    monkeypatch.setattr(DH, "source_as_of", fake_as_of)
    fr = DH.assess_all_sources()
    assert fr["status"] == "ok"

    fixed["P1 事件因子"] = _iso(21)  # 制造一个陈旧源
    fr = DH.assess_all_sources()
    assert fr["status"] == "stale"
    assert fr["max_lag_days"] == 21
    assert fr["sources"]["P1 事件因子"]["status"] == "stale"


def test_assess_all_sources_unknown_when_all_missing(monkeypatch):
    monkeypatch.setattr(DH, "source_as_of", lambda e: None)
    fr = DH.assess_all_sources()
    assert fr["status"] == "unknown"
    assert fr["max_lag_days"] is None


def test_health_rows_shape(monkeypatch):
    monkeypatch.setattr(DH, "source_as_of", lambda e: _iso(2))
    rows = DH.health_rows()
    assert len(rows) == len(DH.DATA_SOURCES)
    for r in rows:
        assert set(r.keys()) == {"key", "name", "as_of", "lag_days", "status"}
        assert r["lag_days"] == 2
        assert r["status"] == "ok"


# ───────────────────────── CLI 退出码契约 ─────────────────────────
def test_cli_exits_1_on_stale_by_default(monkeypatch, capsys):
    """默认模式下存在 stale 源 → exit 1（供 CI 门禁失败告警）。"""
    import scripts.check_data_health as CLI
    monkeypatch.setattr(DH, "source_as_of", lambda e: _iso(21))  # 全陈旧
    monkeypatch.setattr("sys.argv", ["check_data_health.py"])
    assert CLI._main() == 1
    assert "整体状态：stale" in capsys.readouterr().out


def test_cli_no_fail_overrides_exit_code(monkeypatch, capsys):
    """--no-fail 时即使全陈旧也 exit 0（纯报告模式）。"""
    import scripts.check_data_health as CLI
    monkeypatch.setattr(DH, "source_as_of", lambda e: _iso(21))
    monkeypatch.setattr("sys.argv", ["check_data_health.py", "--no-fail"])
    assert CLI._main() == 0


def test_cli_exits_0_when_all_fresh(monkeypatch, capsys):
    """全部新鲜 → exit 0。"""
    import scripts.check_data_health as CLI
    monkeypatch.setattr(DH, "source_as_of", lambda e: _iso(0))
    monkeypatch.setattr("sys.argv", ["check_data_health.py"])
    assert CLI._main() == 0
    assert "整体状态：ok" in capsys.readouterr().out


# ───────────────────────── 刷新注册表 / 计划 ─────────────────────────
def test_refresh_commands_cover_all_sources():
    """每个源都登记了刷新命令，且 daily_snapshot 一条覆盖 3 源（去重）。"""
    covered = {k for c in DH.REFRESH_COMMANDS.values() for k in c["covers"]}
    assert {e["key"] for e in DH.DATA_SOURCES} <= covered
    assert DH.REFRESH_COMMANDS["daily_snapshot"]["covers"] == [
        "shepherd_sentiment", "ladder", "daily_snapshot"]


def test_build_refresh_plan_dedupes_and_marks_stale(monkeypatch):
    """仅陈旧源进入计划；daily_snapshot 三源都陈旧时只出现一条命令且 stale_sources 含三者。"""
    fixed = {e["key"]: _iso(1) for e in DH.DATA_SOURCES}
    fixed["p1_event"] = _iso(21)  # 制造一个外部源陈旧
    # daily_snapshot 覆盖的 3 源全设陈旧 → 应去重为 1 条命令且 stale_sources 含三者
    for k in ("shepherd_sentiment", "ladder", "daily_snapshot"):
        fixed[k] = _iso(14)
    monkeypatch.setattr(DH, "source_as_of", lambda e: fixed[e["key"]])
    plan = DH.build_refresh_plan(stale_only=True)
    cmd_ids = [p["cmd_id"] for p in plan]
    # shepherd_sentiment 与 daily_snapshot/ladder 同属 daily_snapshot 命令 → 去重为 1 条
    assert cmd_ids.count("daily_snapshot") == 1
    assert "p1_event" in cmd_ids
    ds = next(p for p in plan if p["cmd_id"] == "daily_snapshot")
    assert set(ds["stale_sources"]) == {"牧羊人情绪", "连板晋级率", "今日快照"}


def test_build_refresh_plan_skips_fresh_when_stale_only(monkeypatch):
    """全部新鲜 + stale_only=True → 无计划。"""
    monkeypatch.setattr(DH, "source_as_of", lambda e: _iso(0))
    assert DH.build_refresh_plan(stale_only=True) == []


def test_cli_refresh_prints_plan(monkeypatch, capsys):
    """--refresh 打印去重刷新命令，且不执行（exit 仍 1 因 stale）。"""
    import scripts.check_data_health as CLI
    monkeypatch.setattr(DH, "source_as_of", lambda e: _iso(21))  # 全陈旧
    monkeypatch.setattr("sys.argv", ["check_data_health.py", "--refresh"])
    rc = CLI._main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "刷新计划" in out
    assert "python scripts/daily_snapshot.py" in out
    assert "python scripts/refresh_event_db.py" in out


def test_cli_refresh_exec_reports_honest_failure(monkeypatch, capsys):
    """--exec 在命令失败时如实报「刷新失败」，绝不伪造成功。"""
    import scripts.check_data_health as CLI
    monkeypatch.setattr(DH, "source_as_of", lambda e: _iso(21))  # 全陈旧

    class _FakeRC:
        returncode = 1
        stdout = ""
        stderr = "akshare proxy not up"

    monkeypatch.setattr(CLI.subprocess, "run", lambda *a, **k: _FakeRC())
    monkeypatch.setattr("sys.argv", ["check_data_health.py", "--refresh", "--exec"])
    rc = CLI._main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "刷新失败" in out
    assert "akshare proxy not up" in out  # 真实错误透传
    assert "✅ 命令执行成功" not in out  # 没有伪造成功


# ───────────────────────── 校准证据源（prediction_log）入守卫 ─────────────────────────
def test_calibration_evidence_registered_and_extracted(monkeypatch):
    """prediction_log 作为第 7 个受守卫源，抽取器走 track_last_scored，刷新命令已登记。"""
    keys = {e["key"] for e in DH.DATA_SOURCES}
    assert "calibration_evidence" in keys
    monkeypatch.setattr(DH, "_track_last_scored_date", lambda: "2026-09-03")
    row = next(r for r in DH.health_rows() if r["key"] == "calibration_evidence")
    assert row["as_of"] == "2026-09-03"
    # 刷新命令去重时包含校准证据源
    plan = DH.build_refresh_plan(stale_only=False)
    calib = next((p for p in plan if p["cmd_id"] == "calibration_evidence"), None)
    assert calib is not None, "刷新计划应含校准证据源的刷新命令"
    assert "daily_snapshot.py --score-only" in calib["cmd"]



