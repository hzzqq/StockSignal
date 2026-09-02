"""决策闭环端到端拼接护栏（离线、确定性）。

为何单独存在（见 test_decision_track 注释的「只验不崩 → 验数据对」原则延伸）：
   单测已覆盖打分 / by_cycle / 校准各自逻辑，但**没有一条验证它们的字段拼接契约**——
   即 record_prediction 落盘的 key 名（date/temp/cycle/bias/pct）必须被
   score_predictions → by_cycle → calibration.verdict 正确消费。

   这类契约若被「重构改名」破坏，单测会因各自 monkeypatch 独立而全绿，
   运行时却静默失效（正是本会话最早的「牧羊人漏解包 → 整条闭环 0 样本」的根因模式）。
   本文件用**真实的** record_prediction + score_predictions + by_cycle + verdict 串起来跑，
   把字段名契约锁死。

运行：pytest tests/test_decision_loop_e2e.py -q
"""
from __future__ import annotations

from datetime import timedelta

import modules.calibration as _cal
import modules.decision_track as _track

# 四个情绪周期（与 modules.decision 的六阶段→四大战术分组口径一致）
_CYCLES = ["主升高潮", "分化", "修复试探", "退潮"]


def _reset(monkeypatch, tmp_path):
    """预测记录重定向到临时目录并清内存单例状态。"""
    monkeypatch.setattr(_track, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_track, "PRED_PATH", str(tmp_path / "prediction_log.json"))
    try:
        (tmp_path / "prediction_log.json").unlink()
    except OSError:
        pass


def _weekdays(start: str, n: int) -> list[str]:
    """生成 n 个连续交易日（跳过周末），返回 YYYY-MM-DD 列表。"""
    d = __import__("datetime").datetime.strptime(start, "%Y-%m-%d")
    out: list[str] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _fake_closes(dates: list[str], biases: list[str]):
    """构造合成收盘序列：偏多→次日 +1%，偏空→次日 -1%，中性→0。

    _next_day_return 取「≤date 的最大日期(base)」为基准、其后第一个交易日为次日，
    即 ret = closes[dates[i+1]] / closes[dates[i]] - 1。
    因此必须**逐日累积**（每个 next 在 base 之上 ×(1+ret)），
    否则把所有 next 都设成 101.0 会让相邻日相等 → 除首日外收益全为 0（已踩过此坑）。
    """
    closes: dict[str, float] = {}
    prev = 100.0
    for i, d in enumerate(dates):
        closes[d] = round(prev, 2)
        if i + 1 < len(dates):
            nxt = dates[i + 1]
            ret = 0.01 if biases[i] == "偏多" else (-0.01 if biases[i] == "偏空" else 0.0)
            prev = prev * (1 + ret)
            closes[nxt] = round(prev, 2)
    return closes


def test_record_to_bycycle_field_contract(tmp_path, monkeypatch):
    """record_prediction 写出的 cycle 字段必须被 by_cycle 原样分组——改名即失败。

    锁死「闭环字段拼接契约」：未来若有人把 record_prediction 的 cycle key 改名，
    本例会直接红（by_cycle 收不到该周期 → 分组缺失）。
    """
    _reset(monkeypatch, tmp_path)
    dates = _weekdays("2026-03-02", 4)  # 周一..周四
    cycles = ["主升高潮", "退潮", "修复试探", "分化"]
    biases = ["偏多", "偏空", "偏多", "偏空"]
    for d, c, b in zip(dates, cycles, biases):
        _track.record_prediction(d, 60.0, c, b, 70)

    closes = _fake_closes(dates, biases)
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: closes)
    res = _track.score_predictions()
    assert res["scored"] == 3  # 最后一天无次日，不评分

    groups = {g["cycle"]: g for g in _track.by_cycle()}
    # 四个周期全部出现（字段名原样透传）
    assert set(groups.keys()) == set(_CYCLES), f"by_cycle 周期缺失: {set(groups)}"
    # 方向命中判定正确：偏多→次日+1% 命中，偏空→次日-1% 命中
    assert groups["主升高潮"]["hits"] == 1 and groups["主升高潮"]["n_call"] == 1
    assert groups["退潮"]["hits"] == 1 and groups["退潮"]["n_call"] == 1
    # 分数确实回填进了 prediction_log（拼接链终点正确）
    recs = _track._load()
    assert all(r["realized"] is not None for r in recs if r["date"] != dates[-1])


def test_calibration_gating_flips_at_scale(tmp_path, monkeypatch):
    """刻度校准门控的「翻转点」必须存在：小样本不就绪、足够大样本 any_actionable=True。

    这是对 calibration.verdict()「ready = 至少一个战术分组达到可采纳阈值（而非全局 n_call≥20）」
    不变量（见 MEMORY.md）的端到端守护——防止门控逻辑被改坏而永远不给出校准建议。
    """
    # ── 小样本（3 条，分散到多周期）：必须 not ready ──
    _reset(monkeypatch, tmp_path)
    small = _weekdays("2026-04-06", 3)
    small_bias = ["偏多", "偏空", "偏多"]
    for d, c, b in zip(small, ["主升高潮", "退潮", "修复试探"], small_bias):
        _track.record_prediction(d, 55.0, c, b, 60)
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: _fake_closes(small, small_bias))
    _track.score_predictions()
    v_small = _cal.verdict()
    assert v_small["ready"] is False and v_small["any_actionable"] is False

    # ── 大样本（22 条集中到一个周期，全部命中）：any_actionable 必须翻转为 True ──
    _reset(monkeypatch, tmp_path)
    big = _weekdays("2026-05-04", 22)
    big_bias = ["偏多"] * len(big)  # 同向：平均次日收益 +1% → sug_delta=2 触发 actionable
    for d, b in zip(big, big_bias):
        _track.record_prediction(d, 65.0, "主升高潮", b, 65)  # 同周期，便于单组达阈值
    monkeypatch.setattr(_track, "_fetch_benchmark_close", lambda: _fake_closes(big, big_bias))
    scored = _track.score_predictions()["scored"]
    assert scored >= 20  # 大样本确有足够可评分
    v_big = _cal.verdict()
    assert v_big["any_actionable"] is True, f"大样本下校准未就绪: {v_big}"
