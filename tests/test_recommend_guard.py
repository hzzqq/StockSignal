"""tests/test_recommend_guard.py

T-235/236/237：荐股可靠性三件套守卫（全离线）。
- T-235 assess_data_staleness：数据时效纯函数（空/新鲜/滞后/坏日期）
- T-236 assess_recommend_health：调度判活纯函数（空目录/当日/warn/dead + 周末宽容）
- T-237 _maybe_push：微信推送开关（默认关/开启调用/异常不传播）
- 接线文本守卫：36 页 stale 徽标、94 页 health 告警不得脱落
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for p in (str(REPO), str(REPO / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)


# ══════════════ T-235：assess_data_staleness ══════════════
def test_staleness_empty_list_is_stale():
    from modules.recommend_engine import assess_data_staleness

    r = assess_data_staleness([], today="2026-10-11")
    assert r["stale"] is True and r["latest"] is None


def test_staleness_fresh_within_threshold():
    from modules.recommend_engine import assess_data_staleness

    r = assess_data_staleness(["2026-10-09", "2026-10-08"], today="2026-10-11")
    assert r["stale"] is False and r["latest"] == "2026-10-09" and r["lag_days"] == 2


def test_staleness_over_threshold():
    from modules.recommend_engine import assess_data_staleness

    r = assess_data_staleness(["2026-10-01"], today="2026-10-11")
    assert r["stale"] is True and r["lag_days"] == 10 and "过时" in r["note"]


def test_staleness_bad_date_is_stale():
    from modules.recommend_engine import assess_data_staleness

    r = assess_data_staleness(["not-a-date"], today="2026-10-11")
    assert r["stale"] is True


def test_staleness_none_mixed_with_valid():
    from modules.recommend_engine import assess_data_staleness

    r = assess_data_staleness([None, "2026-10-10", None], today="2026-10-11")
    assert r["stale"] is False and r["latest"] == "2026-10-10"


# ══════════════ T-236：assess_recommend_health ══════════════
def _make_archive(tmp_path, dates):
    rec_dir = tmp_path / "recommendations"
    rec_dir.mkdir(parents=True, exist_ok=True)
    for d in dates:
        (rec_dir / f"{d}.json").write_text("{}", encoding="utf-8")
    return str(tmp_path)


def test_health_empty_dir_dead(tmp_path):
    from backend.recommend_scheduler import assess_recommend_health

    r = assess_recommend_health(now=datetime(2026, 10, 9, 16, 0), data_dir=str(tmp_path))
    assert r["status"] == "dead"


def test_health_today_ok(tmp_path):
    from backend.recommend_scheduler import assess_recommend_health

    # 2026-10-08 是周四；同日 16:00 查 → ok
    r = assess_recommend_health(now=datetime(2026, 10, 8, 16, 0),
                                data_dir=_make_archive(tmp_path, ["2026-10-08"]))
    assert r["status"] == "ok" and r["latest"] == "2026-10-08"


def test_health_age1_weekday_after_close_warn(tmp_path):
    from backend.recommend_scheduler import assess_recommend_health

    # 周五 16:00 查，最新停在周四（工作日生成窗口内未生成）→ warn
    r = assess_recommend_health(now=datetime(2026, 10, 9, 16, 0),
                                data_dir=_make_archive(tmp_path, ["2026-10-08"]))
    assert r["status"] == "warn"


def test_health_age1_before_window_ok(tmp_path):
    from backend.recommend_scheduler import assess_recommend_health

    # 周五 10:00 查（未到 15:30 窗口），最新=昨日 → ok
    r = assess_recommend_health(now=datetime(2026, 10, 9, 10, 0),
                                data_dir=_make_archive(tmp_path, ["2026-10-08"]))
    assert r["status"] == "ok"


def test_health_age5_dead(tmp_path):
    from backend.recommend_scheduler import assess_recommend_health

    r = assess_recommend_health(now=datetime(2026, 10, 14, 16, 0),
                                data_dir=_make_archive(tmp_path, ["2026-10-08"]))
    assert r["status"] == "dead" and "停摆" in r["message"]


def test_health_weekend_lenient(tmp_path):
    from backend.recommend_scheduler import assess_recommend_health

    # 周日（2026-10-11）查，最新=周五 10-09（最近应生成工作日）→ 周末宽容 → ok
    r = assess_recommend_health(now=datetime(2026, 10, 11, 12, 0),
                                data_dir=_make_archive(tmp_path, ["2026-10-09"]))
    assert r["status"] == "ok"


def test_health_missed_friday_warn_on_sunday(tmp_path):
    from backend.recommend_scheduler import assess_recommend_health

    # 周日查，最新=周四（周五工作日窗口缺生成）→ warn（只缺最近一轮）
    r = assess_recommend_health(now=datetime(2026, 10, 11, 12, 0),
                                data_dir=_make_archive(tmp_path, ["2026-10-08"]))
    assert r["status"] == "warn"


# ══════════════ T-237：_maybe_push 开关 ══════════════
def _rec():
    return {"status": "ok", "date": "2026-10-11", "picks": [
        {"code": "600519", "name": "贵州茅台", "composite": 88.5,
         "data_staleness": {"stale": False}},
    ], "data_staleness": {"stale": False, "note": "ok"}}


def test_push_disabled_by_default(monkeypatch):
    import backend.recommend_scheduler as rs

    called = {"n": 0}
    monkeypatch.setenv("STOCKSIGNAL_RECOMMEND_PUSH", "0")
    monkeypatch.setattr("modules.push_channel.push_text", lambda text, prefer="auto": called.__setitem__("n", called["n"] + 1) or {"ok": True})
    rs._maybe_push(_rec())
    assert called["n"] == 0, "默认必须关（不擅自打扰）"


def test_push_enabled_calls_push_text(monkeypatch):
    import backend.recommend_scheduler as rs

    seen = {}
    monkeypatch.setenv("STOCKSIGNAL_RECOMMEND_PUSH", "1")
    monkeypatch.setattr("modules.push_channel.push_text",
                        lambda text, prefer="auto": seen.setdefault("text", text) or {"ok": True})
    rs._maybe_push(_rec())
    assert "每日荐股" in (seen.get("text") or "") and "贵州茅台" in (seen.get("text") or "")


def test_push_exception_never_propagates(monkeypatch):
    import backend.recommend_scheduler as rs

    monkeypatch.setenv("STOCKSIGNAL_RECOMMEND_PUSH", "1")

    def _boom(text, prefer="auto"):
        raise RuntimeError("通道炸了")

    monkeypatch.setattr("modules.push_channel.push_text", _boom)
    rs._maybe_push(_rec())  # 不抛即通过


def test_push_stale_warning_in_text(monkeypatch):
    import backend.recommend_scheduler as rs

    seen = {}
    monkeypatch.setenv("STOCKSIGNAL_RECOMMEND_PUSH", "1")
    monkeypatch.setattr("modules.push_channel.push_text",
                        lambda text, prefer="auto": seen.setdefault("text", text) or {"ok": True})
    rec = _rec()
    rec["data_staleness"] = {"stale": True, "note": "行情数据最新 2026-10-01，滞后 10 天"}
    rs._maybe_push(rec)
    assert "数据时效" in (seen.get("text") or "") or "滞后" in (seen.get("text") or "")


# ══════════════ 接线文本守卫（防脱落）══════════════
def test_page36_has_staleness_warning():
    src = (REPO / "pages" / "36_每日荐股.py").read_text(encoding="utf-8")
    assert "data_staleness" in src and "数据时效告警" in src


def test_page94_has_health_alarm():
    src = (REPO / "pages" / "94_消息中心.py").read_text(encoding="utf-8")
    assert "assess_recommend_health" in src and "荐股告警" in src


def test_engine_generate_wires_staleness():
    import inspect

    from modules import recommend_engine as re_mod

    src = inspect.getsource(re_mod.generate_daily_recommendation)
    assert "assess_data_staleness" in src and "data_staleness" in src
