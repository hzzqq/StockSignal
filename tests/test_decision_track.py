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


# ───────────────────── 分情绪周期命中率（战术细分） ─────────────────────
def _seed_cycle_samples(monkeypatch):
    """种一批带情绪周期的样本：进攻期 2 中 1，防守期 1 中 1，修复期不表态。"""
    closes = {
        "2026-08-26": 3000.0, "2026-08-27": 3060.0,   # +2.0% 涨
        "2026-08-28": 3000.0,                         # -1.97% 跌
        "2026-08-31": 3050.0,                         # +1.67% 涨
    }
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: closes)
    _track.record_prediction("2026-08-26", 72, "主升高潮", "偏多", 80)   # 次日涨 → 命中
    _track.record_prediction("2026-08-27", 68, "修复确认", "偏多", 70)   # 次日跌 → 未命中
    _track.record_prediction("2026-08-28", 30, "退潮", "偏空", 25)       # 次日涨 → 未命中
    _track.record_prediction("2026-08-30", 45, "冰点", "中性", 40)       # 不表态 → 不计入分母
    _track.score_predictions()


def test_by_cycle_groups_and_accuracy(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    _seed_cycle_samples(monkeypatch)
    rows = _track.by_cycle()
    by = {r["cycle"]: r for r in rows}

    # 六阶段 → 四大战术分组映射正确
    assert by["主升高潮"]["group"] == "进攻期"
    assert by["修复确认"]["group"] == "进攻期"
    assert by["退潮"]["group"] == "防守期"
    assert by["冰点"]["group"] == "修复期"

    # 进攻期 2 次表态、命中 1 次 → 50%
    assert by["主升高潮"]["n_call"] == 1 and by["主升高潮"]["hits"] == 1
    assert by["修复确认"]["n_call"] == 1 and by["修复确认"]["hits"] == 0
    # 中性不表态：不计入分母
    assert by["冰点"]["n_call"] == 0 and by["冰点"]["accuracy"] is None

    # 顺序稳定：分组热度序 → 表态数降序（进攻期应排在防守期之前）
    assert [r["group"] for r in rows][0] == "进攻期"


def test_by_group_aggregates_phases(tmp_path, monkeypatch):
    """四大分组把六阶段归并，解决单阶段样本稀疏。"""
    _reset(monkeypatch, tmp_path)
    _seed_cycle_samples(monkeypatch)
    gs = {g["group"]: g for g in _track.by_group()}
    # 进攻期 = 主升高潮(1中1) + 修复确认(1中0) = 2 表态 1 命中 → 50%
    assert gs["进攻期"]["n_call"] == 2 and gs["进攻期"]["hits"] == 1
    assert gs["进攻期"]["accuracy"] == 50.0
    # 防守期 = 退潮(1 表态 0 命中) → 0%
    assert gs["防守期"]["accuracy"] == 0.0
    # 修复期只有中性样本 → 无表态，不出命中率
    assert gs["修复期"]["n_call"] == 0 and gs["修复期"]["accuracy"] is None
    # 顺序按热度：进攻期 → 分化期 → 修复期 → 防守期
    names = [g["group"] for g in _track.by_group()]
    assert names == sorted(names, key=lambda g: ["进攻期", "分化期", "修复期", "防守期"].index(g))


def test_by_group_min_samples_filters_noise(tmp_path, monkeypatch):
    """样本不足的分组默认可过滤，避免 1 条样本显示 0%/100% 误导。"""
    _reset(monkeypatch, tmp_path)
    _seed_cycle_samples(monkeypatch)
    # 进攻期 2 次表态达标，防守期(1)/修复期(0) 样本不足被过滤
    kept = _track.by_group(min_samples=2)
    assert [g["group"] for g in kept] == ["进攻期"]
    assert kept[0]["n_call"] == 2 and kept[0]["accuracy"] == 50.0


# ───────────────────── 脚本 --score-only 轻量打分模式 ─────────────────────
def _load_snapshot_script():
    """scripts/ 无 __init__.py，按文件路径加载（与主脚本入口等价）。"""
    import importlib.util
    from pathlib import Path
    root = Path(_track.ROOT)
    spec = importlib.util.spec_from_file_location(
        "_ds_score_only", root / "scripts" / "daily_snapshot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_score_only_mode_does_not_fetch_market(tmp_path, monkeypatch):
    """--score-only 只打分：绝不触碰牧羊人/梯队抓取（抓取函数被调即视为失败）。"""
    _reset(monkeypatch, tmp_path)
    ds = _load_snapshot_script()

    def _boom(*a, **k):
        raise AssertionError("--score-only 不应触发行情抓取")

    monkeypatch.setattr(ds, "get_shepherd_indicators", _boom)
    monkeypatch.setattr(ds, "get_zt_ladder", _boom)
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: {"2026-08-26": 3000.0,
                                                                   "2026-08-27": 3060.0})
    _track.record_prediction("2026-08-26", 72, "主升高潮", "偏多", 80)
    monkeypatch.setattr("sys.argv", ["daily_snapshot.py", "--score-only", "--quiet"])

    assert ds.main() == 0, "打分模式应正常退出（退出码 0）"
    assert _track.summary()["n_call"] == 1
    assert _track.summary()["accuracy"] == 100.0


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
