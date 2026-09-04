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
                                 "p1_latest_date", "mtime") for e in DH.DATA_SOURCES)


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

