# -*- coding: utf-8 -*-
"""
tests/test_decision_track.py — 「预测 vs 实际」回测层的数据正确性守卫（离线、确定性）

为何存在（对应「把冒烟从只验不崩升级为验数据对」的建议）：
    回测模块 decision_track 是新能力，必须锁死它的数据逻辑——
    · record_prediction 落盘与按日期幂等覆盖；
    · score_predictions 用「次日基准涨跌」正确判定方向命中、且不因网络失败而崩；
    · summary / chart_data 汇总口径正确。
    全部用固定 JSONL + monkeypatch 基准序列，零网络、可重复。

运行：pytest tests/test_decision_track.py -q
"""

from __future__ import annotations

import importlib

import modules.decision_track as _track


def _reset(monkeypatch, tmp_path):
    """把预测记录重定向到临时目录，并清空内存中的单例状态。"""
    monkeypatch.setattr(_track, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_track, "PRED_PATH", str(tmp_path / "prediction_log.json"))
    # 清掉可能已存在的文件
    try:
        (tmp_path / "prediction_log.json").unlink()
    except OSError:
        pass


def test_record_and_summary_empty(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    assert _track.summary()["n"] == 0
    assert _track.chart_data() is None


def test_record_prediction_and_idempotent(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    assert _track.record_prediction("2026-08-28", 55, "修复确认", "偏多", 70) is True
    # 同日期覆盖（不新增行）
    assert _track.record_prediction("2026-08-28", 55, "修复确认", "偏多", 65) is True
    assert _track.record_prediction("2026-08-29", 40, "退潮", "偏空", 30) is True

    s = _track.summary()
    assert s["n"] == 2, "同日期应幂等覆盖，不应新增"
    recs = _track._load()
    by_date = {r["date"]: r for r in recs}
    assert by_date["2026-08-28"]["pct"] == 65, "同日期覆盖后 pct 应更新"


def test_score_predictions_offline(tmp_path, monkeypatch):
    """固定基准序列，验证方向命中判定与汇总口径正确。"""
    _reset(monkeypatch, tmp_path)
    # 基准：08-28→08-29 +2.0%(涨) ；08-29→08-30 -1.0%(跌) ；08-30 无次日
    closes = {
        "2026-08-28": 3000.0,
        "2026-08-29": 3060.0,
        "2026-08-30": 3030.0,
    }
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: closes)

    _track.record_prediction("2026-08-28", 55, "修复确认", "偏多", 70)  # 次日涨 → 命中
    _track.record_prediction("2026-08-29", 40, "退潮", "偏空", 30)       # 次日跌 → 命中
    _track.record_prediction("2026-08-30", 50, "冰点", "中性", 50)       # 不表态 → 不计入命中率

    res = _track.score_predictions()
    assert res["scored"] == 2, "08-30 无次日，不应被计分"
    s = _track.summary()
    assert s["n_call"] == 2, "中性预测不计入命中率分母"
    assert s["hits"] == 2
    assert s["accuracy"] == 100.0, "两笔偏多/偏空均命中，应为 100%"

    recs = _track._load()
    by_date = {r["date"]: r for r in recs}
    assert by_date["2026-08-28"]["realized"] == 2.0
    assert by_date["2026-08-28"]["hit"] is True
    assert by_date["2026-08-29"]["realized"] == -0.98
    assert by_date["2026-08-29"]["hit"] is True
    assert by_date["2026-08-30"]["realized"] is None, "无次日的样本不应被回填"


def test_score_predictions_no_network_graceful(tmp_path, monkeypatch):
    """基准取不到（如断网）时优雅降级：不计分、不抛。"""
    _reset(monkeypatch, tmp_path)
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: None)
    _track.record_prediction("2026-08-28", 55, "修复确认", "偏多", 70)
    res = _track.score_predictions()
    assert res["scored"] == 0
    assert _track.summary()["accuracy"] is None


def test_chart_data_shape(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    closes = {
        "2026-08-28": 3000.0,
        "2026-08-29": 3060.0,
        "2026-08-30": 3030.0,
    }
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: closes)
    _track.record_prediction("2026-08-28", 55, "修复确认", "偏多", 70)
    _track.record_prediction("2026-08-29", 40, "退潮", "偏空", 30)
    _track.score_predictions()

    cd = _track.chart_data()
    assert cd is not None
    assert cd["dates"] == ["2026-08-28", "2026-08-29"]
    assert cd["predicted"] == [70, 30]
    assert cd["realized"] == [2.0, -0.98]
    assert cd["cumulative_hit"] == [100.0, 100.0]
