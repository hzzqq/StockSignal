# -*- coding: utf-8 -*-
"""
tests/test_calibration.py — 仓位刻度反向校准的规则守卫（离线、确定性）

为何存在：
    calibration.py 会用回测数据「反推」decision.py 的 CYCLE_ADJ 常数。这个能力
    一旦失控（自动改规则 / 小样本拟合 / 调节量无界）就会把噪音当信号写进系统，
    比当初拍脑袋的常数更危险。所以必须锁死三条设计铁律：
        T1 只出建议不自动改规则：as_patch() 只返回 dict，绝不写 decision.py；
        T2 调节量有界：sug_delta 被 clamp 在 ±MAX_DELTA，样本再极端也不越界；
        T3 小样本不表态：样本 <strong_samples 或调节量在噪音阈值内 → actionable=False。
    另锁计算口径：中性不计入 n_call、avg_realized 驱动 sug_delta 的符号与幅度。

运行：pytest tests/test_calibration.py -q
"""

from __future__ import annotations

import modules.calibration as _cal
import modules.decision_track as _track


# ───────────────────────── 构造离線样本 ─────────────────────────
def _rec(date: str, cycle: str, bias: str, pct: int, realized: float | None):
    """造一条预测记录（hit 按方向一致性算出，与 decision_track 口径一致）。"""
    hit = None
    if realized is not None:
        d = {"偏多": 1, "偏空": -1, "中性": 0}.get(bias, 0)
        a = 1 if realized > 0 else (-1 if realized < 0 else 0)
        hit = None if d == 0 else (d == a)
    return {"date": date, "temp": 50, "cycle": cycle, "bias": bias,
            "pct": pct, "realized": realized, "hit": hit}


def _seed(monkeypatch, recs):
    """把 decision_track 的数据源换成固定记录，全程离线。"""
    monkeypatch.setattr(_track, "_load", lambda: list(recs))
    monkeypatch.setattr(_track, "_save", lambda r: None)


def _n(n: int, cycle: str, bias: str, pct: int, realized: float, start: int = 1):
    """造 n 条同参数样本（日期递增，保证落盘顺序稳定）。"""
    return [_rec(f"2026-01-{i:02d}", cycle, bias, pct, realized)
            for i in range(start, start + n)]


# ───────────────────────── T3 小样本不表态 ─────────────────────────
def test_below_min_samples_hidden(tmp_path, monkeypatch):
    """样本 <min_samples(8) 连观察行都不展示：1~2 条样本的行只会误导，不如不给。"""
    _seed(monkeypatch, _n(5, "退潮", "偏空", 20, -3.0))
    assert _cal.suggestions() == [], "样本 <8 条的分组应被直接过滤"


def test_small_sample_not_actionable(tmp_path, monkeypatch):
    """样本在观察区间（≥8 但 <20）时出建议行，但明确标记不可采纳。"""
    _seed(monkeypatch, _n(12, "退潮", "偏空", 20, -3.0))
    sug = _cal.suggestions()
    assert sug, "样本 ≥8 条应出观察行"
    row = [s for s in sug if s["group"] == "防守期"][0]
    assert row["n_call"] == 12
    assert row["sug_delta"] < 0, "次日平均跌，调节量应为负"
    assert row["actionable"] is False, "样本 <20 条，不应标记为可采纳"
    assert "样本仅" in row["verdict"]


def test_noise_delta_not_actionable(tmp_path, monkeypatch):
    """样本够但调节量在噪音阈值内（|delta|<2）→ 不值得动手改规则。"""
    # realized=-0.4% → delta = round(2 * -0.4) = -1 → 属噪音
    _seed(monkeypatch, _n(25, "退潮", "偏空", 45, -0.4))
    row = [s for s in _cal.suggestions() if s["group"] == "防守期"][0]
    assert row["sug_delta"] == -1
    assert row["actionable"] is False, "调节量属噪音，不应建议改"
    assert "无需调整" in row["verdict"]


# ───────────────────────── T2 调节量有界 ─────────────────────────
def test_delta_clamped_to_max(tmp_path, monkeypatch):
    """极端样本也不越界：单次校准最多 ±MAX_DELTA 点，防过拟合。"""
    _seed(monkeypatch, _n(30, "退潮", "偏空", 10, -20.0))  # 次日平均暴跌 20%
    row = [s for s in _cal.suggestions() if s["group"] == "防守期"][0]
    assert row["sug_delta"] == -_cal.MAX_DELTA, "应被 clamp 在下限"
    assert row["actionable"] is True, "样本足 + 偏差大 → 可采纳"

    _seed(monkeypatch, _n(30, "主升高潮", "偏多", 90, 20.0))  # 次日平均暴涨 20%
    row = [s for s in _cal.suggestions() if s["group"] == "进攻期"][0]
    assert row["sug_delta"] == _cal.MAX_DELTA, "应被 clamp 在上限"


# ───────────────────────── 计算口径 ─────────────────────────
def test_delta_sign_and_magnitude(tmp_path, monkeypatch):
    """调节量 = 2 × 次日平均涨跌：符号跟随实际方向，幅度按 GAIN 换算。"""
    _seed(monkeypatch, _n(25, "退潮", "偏空", 30, -1.5))  # 平均跌 1.5% → -3 点
    row = [s for s in _cal.suggestions() if s["group"] == "防守期"][0]
    assert row["avg_realized"] == -1.5
    assert row["sug_delta"] == -3
    assert row["cur_adj"] is not None, "防守期应能取到当前 CYCLE_ADJ"
    assert row["sug_adj"] == round(row["cur_adj"] + row["sug_delta"], 1)


def test_neutral_not_counted_in_n_call(tmp_path, monkeypatch):
    """中性预测不表态，不计入 n_call 分母（与 summary/by_group 口径一致）。"""
    recs = _n(20, "退潮", "偏空", 30, -2.0) + _n(10, "退潮", "中性", 50, -2.0, start=100)
    _seed(monkeypatch, recs)
    row = [s for s in _cal.suggestions() if s["group"] == "防守期"][0]
    assert row["n_call"] == 20, "中性不表态，不该进分母"
    assert row["n"] == 30, "总记录数仍应统计中性"


def test_edge_is_position_weighted(tmp_path, monkeypatch):
    """暴露收益 = 平均建议仓位/100 × 次日平均实际涨跌，衡量「敢给的仓位值不值」。"""
    _seed(monkeypatch, _n(25, "主升高潮", "偏多", 80, 2.0))
    row = [s for s in _cal.suggestions() if s["group"] == "进攻期"][0]
    assert row["avg_pct"] == 80.0
    assert row["edge"] == round(80 / 100 * 2.0, 3) == 1.6


# ───────────────────────── T1 只出建议，不自动改规则 ─────────────────────────
def test_as_patch_only_contains_actionable(tmp_path, monkeypatch):
    """as_patch 只摊回可采纳的分组，且只改这些分组覆盖的阶段。"""
    from modules import decision as _dec
    # 防守期：25 条、平均跌 2% → delta=-4 → 可采纳
    # 进攻期：仅 3 条、平均涨 5% → 样本不足 → 不采纳
    recs = (_n(25, "退潮", "偏空", 30, -2.0)
            + _n(3, "主升高潮", "偏多", 80, 5.0, start=200))
    _seed(monkeypatch, recs)
    patch = _cal.as_patch()
    assert "退潮" in patch, "可采纳的防守期应摊回退潮阶段"
    assert "主升高潮" not in patch, "样本不足的分组不应出现在补丁里"
    assert patch["退潮"] == int(_dec.CYCLE_ADJ["退潮"]) - 4


def test_as_patch_never_writes_decision(tmp_path, monkeypatch):
    """铁律：as_patch 绝不修改 decision.CYCLE_ADJ（只返回 dict，落地由人决定）。"""
    from modules import decision as _dec
    before = dict(_dec.CYCLE_ADJ)
    _seed(monkeypatch, _n(25, "退潮", "偏空", 30, -2.0))
    _cal.as_patch()
    assert dict(_dec.CYCLE_ADJ) == before, "调用 as_patch 不得改动 CYCLE_ADJ"


# ───────────────────────── verdict 总览 ─────────────────────────
def test_verdict_ready_threshold(tmp_path, monkeypatch):
    """verdict 按 strong_samples 判定是否可校准，并给出还差多少条。"""
    _seed(monkeypatch, _n(7, "退潮", "偏空", 30, -1.0))
    v = _cal.verdict(strong_samples=20)
    assert v["ready"] is False
    assert v["gap"] == 13
    assert "还需 13 条" in v["msg"]

    _seed(monkeypatch, _n(20, "退潮", "偏空", 30, -1.0))
    v = _cal.verdict(strong_samples=20)
    assert v["ready"] is True
    assert v["gap"] == 0


def test_empty_history_is_safe(tmp_path, monkeypatch):
    """无样本时全链路返回空/零，不抛（页面首日不炸是底线）。"""
    _seed(monkeypatch, [])
    v = _cal.verdict()
    assert v["n_call"] == 0 and v["ready"] is False
    assert _cal.suggestions() == []
    assert _cal.as_patch() == {}
