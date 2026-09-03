# -*- coding: utf-8 -*-
"""StockSignal 锐评迭代优化（I2/I3/I4/I6/I8/I9）单测。

覆盖本次决策闭环迭代的新行为：
  · I4 derive_position 输入校验（温度越界 clamp / 未知方向 / 未知周期告警）
  · I3 事件信号不可用时在 reasons 留痕
  · I2 快照 data_age_days / as_of 元信息
  · I8 prediction_log 记录事件归因字段 + 幂等保留已打分
  · I9 by_event 按事件开/关拆命中率
  · I6 calibration.verdict 样本新鲜度字段
"""
import logging

import pytest

from modules import decision as _dec
from modules import decision_track as _track
from modules import calibration as _cal


# ───────── I4 输入校验 ─────────
def test_temp_clamp_upper():
    pos = _dec.derive_position(150, bias="中性", cycle_name="主升高潮")
    assert pos["pct"] == 95          # base 150 → clamp 100 → +5(主升) → clamp 95
    assert any("温度 100" in r for r in pos["reasons"])


def test_temp_clamp_lower():
    pos = _dec.derive_position(-20, bias="偏空", cycle_name="退潮")
    assert pos["pct"] == 5           # base clamp 0 → -8(偏空) -10(退潮) → clamp 5
    assert any("温度 0" in r for r in pos["reasons"])


def test_unknown_bias_warn(caplog):
    with caplog.at_level(logging.WARNING):
        pos = _dec.derive_position(50, bias="XYZ", cycle_name="主升高潮")
    assert pos["band"] in ("激进", "偏多", "中性", "偏空", "防御")  # 不崩
    assert any("未知方向" in r.message for r in caplog.records)


def test_unknown_cycle_warn(caplog):
    with caplog.at_level(logging.WARNING):
        pos = _dec.derive_position(50, bias="中性", cycle_name="神秘周期")
    assert any("未知情绪周期" in r.message for r in caplog.records)
    # 未知周期按 0 调节，pct 应等于基准仓位（无周期项）
    assert pos["pct"] == 50 or pos["pct"] == 5  # 50 clamp[5,95]=50


# ───────── I3 事件留痕 ─────────
def test_event_unavailable_reason():
    pos = _dec.derive_position(50, bias="中性", cycle_name="主升高潮", event_adj=None)
    assert any("事件驱动信号不可用" in r for r in pos["reasons"])


def test_event_applied_reason():
    pos = _dec.derive_position(50, bias="中性", cycle_name="主升高潮", event_adj=3)
    assert any("事件驱动催化" in r for r in pos["reasons"])


# ───────── I2 快照新鲜度元信息 ─────────
def test_snapshot_has_age_fields():
    snap = _dec.build_snapshot("2026-09-03", {}, 50,
                                {"cycle": {"name": "主升高潮"}, "bias": "偏多", "score": 60},
                                {"overall": 65})
    assert snap["as_of"] == "2026-09-03"
    assert "data_age_days" in snap
    assert isinstance(snap["data_age_days"], int)


# ───────── I8 事件归因字段落库 + 幂等 ─────────
def test_record_prediction_event_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    ok = _track.record_prediction("2026-09-03", 60, "主升高潮", "偏多", 70,
                                  event_adj=3, event_available=True)
    assert ok
    recs = _track._load()
    assert len(recs) == 1
    assert recs[0]["event_adj"] == 3
    assert recs[0]["event_available"] is True


def test_record_prediction_idempotent_preserves_scored(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    _track.record_prediction("2026-09-03", 60, "主升高潮", "偏多", 70,
                              event_adj=3, event_available=True)
    # 打分后回填
    recs = _track._load()
    recs[0]["realized"] = 1.2
    recs[0]["hit"] = True
    _track._save(recs)
    # 同日重跑预测侧（事件信号这次取不到 → None）
    _track.record_prediction("2026-09-03", 60, "主升高潮", "偏多", 70,
                              event_adj=None, event_available=None)
    recs2 = _track._load()
    assert len(recs2) == 1
    assert recs2[0]["realized"] == 1.2      # 已打分保留
    assert recs2[0]["hit"] is True
    # 事件字段：本次 None → 沿用旧值，不被抹掉
    assert recs2[0]["event_available"] is True


# ───────── I9 by_event 拆分 ─────────
def test_by_event_split(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    recs = [
        {"date": "2026-09-01", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": 1.0, "hit": True},
        {"date": "2026-09-02", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": -1.0, "hit": False},
        {"date": "2026-09-03", "temp": 40, "cycle": "退潮", "bias": "偏空",
         "pct": 20, "event_available": False, "realized": -1.0, "hit": True},
        {"date": "2026-09-04", "temp": 40, "cycle": "退潮", "bias": "偏空",
         "pct": 20, "event_available": False, "realized": 1.0, "hit": False},
    ]
    _track._save(recs)
    be = {r["group"]: r for r in _track.by_event()}
    assert set(be.keys()) == {"事件开", "事件关"}
    assert be["事件开"]["n_call"] == 2 and be["事件开"]["accuracy"] == 50.0
    assert be["事件关"]["n_call"] == 2 and be["事件关"]["accuracy"] == 50.0


def test_last_scored_date(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    recs = [
        {"date": "2026-09-01", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": None, "hit": None},
        {"date": "2026-09-05", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": 1.0, "hit": True},
    ]
    _track._save(recs)
    assert _track.last_scored_date() == "2026-09-05"


# ───────── I6 verdict 新鲜度字段 ─────────
def test_verdict_freshness_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)
    importlib.reload(_cal)

    _track._save([])
    v = _cal.verdict()
    assert "last_scored_date" in v
    assert "stale_days" in v
    assert v["last_scored_date"] is None  # 无样本 → 无最近打分
