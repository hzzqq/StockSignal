# -*- coding: utf-8 -*-
"""
tests/test_recommend_risk_penalty.py
====================================
T-330 R6 连续风险扣分守卫（benchmark 采纳清单 R6：五路「只奖不罚」结构性补位）。

契约（spec 冻结 2026-10-26）：

continuous_risk_penalty(df) 纯函数（连续价量风险惩罚，0~14 分）：
- 振幅分量 amp5 = 近 5 日 mean((high-low)/prev_close)，
  penalty_amp = clamp((amp5 - 0.05) × 120, 0, 8)（5% 起罚，+1pp 罚 1.2，封顶 8）；
- 回撤分量 dd20 = 1 - close[-1] / max(close[-20:])，
  penalty_dd = clamp((dd20 - 0.20) × 60, 0, 6)（20% 起罚，+10pp 罚 6，封顶 6）；
  注：买入条件要求 close>MA20，故深回撤候选=「站上 MA20 但近 20 日剧烈下摆」的
  高波动股；处于 20 日新高的右侧强势股 dd20=0 不受罚；
- 换手率：数据链无字段 → components.turnover 恒 unavailable（reasons 如实标注，
  绝不默认 0、绝不假装扫过）；
- high/low 缺列 / 样本不足（<6 行振幅、<21 行回撤）→ 该分量 unavailable
  不计分母（不谎报 0 风险）。

apply_unlock_penalty(rows, scan_map)（解禁临近扣分，复用 R1 闸门已取数据）：
- 仅 risk_scan.status=="scanned" 行取 scan_map[code].components.unlock；
- unlock.value = 未来 90 日最大解禁占流通市值 %，level ∈ {medium, high} →
  penalty = clamp(value × 0.4, 0, 8)（10%→4 分，20%→8 分封顶），
  composite 相应扣减（floor 0），reasons 追加 [风险] 条目，risk_penalty.unlock 透明记录；
- unknown / low / 组件或数值缺失 → 不罚（不编造）；
- 返回按 composite 降序重排的列表（gate 成员资格不变，只改顺位）。

主流程接线（generate_daily_recommendation）：
- 阶段 3 rows 循环调用 continuous_risk_penalty，penalty>0 时扣 composite 并入 reasons，
  risk_penalty 元数据透明落 row（0 分也存，防「悄悄不罚」）；
- R1 闸门后调用 apply_unlock_penalty。

mutation：振幅项失效 / 回撤项失效 / 解禁罚误伤 low 级 / 缺列谎报 0 风险 → 对应用例变红。
"""
import inspect

import numpy as np
import pandas as pd
import pytest

from modules import recommend_engine as re_eng


# ─────────────── 连续价量风险惩罚（纯函数） ───────────────
def _base_df(n=30, high_pad=0.005, low_pad=0.005, close_tail=None):
    """构造 n 行日线的辅助：默认紧振幅（±0.5%）+ 平价（回撤 0）。"""
    close = [100.0] * n if close_tail is None else close_tail
    return pd.DataFrame({
        "close": close,
        "volume": [1_000_000.0] * n,
        "high": [c * (1 + high_pad) for c in close],
        "low": [c * (1 - low_pad) for c in close],
    })


def test_amplitude_penalty_monotonic_and_capped():
    """振幅过热：amp5 越大罚越多，封顶 8；低振幅不罚。"""
    calm = re_eng.continuous_risk_penalty(_base_df(high_pad=0.005, low_pad=0.005))
    mid = re_eng.continuous_risk_penalty(_base_df(high_pad=0.04, low_pad=0.04))
    wild = re_eng.continuous_risk_penalty(_base_df(high_pad=0.10, low_pad=0.10))
    # 平价（close 恒 100）→ dd20 = 0，罚分全部来自振幅分量
    assert calm["components"]["amplitude"]["penalty"] == pytest.approx(0.0, abs=1e-9)
    assert mid["components"]["amplitude"]["penalty"] == pytest.approx((0.08 - 0.05) * 120, abs=0.01)
    assert wild["components"]["amplitude"]["penalty"] == pytest.approx(8.0, abs=0.01)
    assert calm["penalty"] < mid["penalty"] < wild["penalty"]
    assert wild["penalty"] <= 8.0 + 1e-9, "平价下总罚分不得超过振幅封顶 8"


def test_drawdown_penalty_tiers_and_zero_at_high():
    """20 日深回撤起罚 20%、封顶 6；20 日新高（右侧强势）不受罚。"""
    dd0 = re_eng.continuous_risk_penalty(_base_df())  # 平价 → dd=0
    assert dd0["components"]["drawdown"]["penalty"] == pytest.approx(0.0, abs=1e-9)
    # 20 日内从 100 跌到 82（dd=0.18，未达起罚线）→ 0
    tail = [100.0] * 25 + [100.0 * (1 - 0.18)] * 5
    d18 = re_eng.continuous_risk_penalty(_base_df(close_tail=tail))
    assert d18["components"]["drawdown"]["penalty"] == pytest.approx(0.0, abs=1e-9)
    # dd=0.30 → (0.30-0.20)*60 = 6（触顶）
    tail30 = [100.0] * 25 + [70.0] * 5
    d30 = re_eng.continuous_risk_penalty(_base_df(close_tail=tail30))
    assert d30["components"]["drawdown"]["penalty"] == pytest.approx(6.0, abs=0.01)
    # dd=0.25 → 3
    tail25 = [100.0] * 25 + [75.0] * 5
    d25 = re_eng.continuous_risk_penalty(_base_df(close_tail=tail25))
    assert d25["components"]["drawdown"]["penalty"] == pytest.approx(3.0, abs=0.01)


def test_turnover_always_unavailable_with_honest_note():
    """换手率：数据链无字段 → 恒 unavailable，reasons 如实标注（不默认 0）。"""
    r = re_eng.continuous_risk_penalty(_base_df())
    assert r["components"]["turnover"]["status"] == "unavailable"
    assert "换手率" in "".join(r["reasons"])


def test_missing_columns_or_short_history_unavailable_not_zero():
    """缺 high/low 列或样本不足 → 该分量 unavailable（不谎报 0 风险）。"""
    df_nohl = _base_df().drop(columns=["high", "low"])
    r = re_eng.continuous_risk_penalty(df_nohl)
    assert r["components"]["amplitude"]["status"] == "unavailable"
    assert r["components"]["drawdown"]["status"] == "ok"  # close 仍在，回撤可算
    # 5 行：振幅与回撤都不可得 → 总罚 0，但 reasons 须如实交代
    r5 = re_eng.continuous_risk_penalty(_base_df(n=5))
    assert r5["penalty"] == pytest.approx(0.0, abs=1e-9)
    assert r5["components"]["amplitude"]["status"] == "unavailable"
    assert r5["components"]["drawdown"]["status"] == "unavailable"
    assert "不可得" in "".join(r5["reasons"])


# ─────────────── 解禁临近扣分（apply_unlock_penalty） ───────────────
def _row(code, composite, scanned=True):
    return {"code": code, "name": f"股{code}", "composite": composite,
            "reasons": [], "risk_scan": {"status": "scanned" if scanned else "not_scanned"}}


def _scan(unlock_level, unlock_value):
    return {"components": {"unlock": {"level": unlock_level, "value": unlock_value,
                                      "note": "x", "detail": []}},
            "report": {"overall_level": "low"}}


def test_unlock_penalty_applied_and_rows_resorted():
    """medium/high 解禁 → 按市值占比扣分，且 rows 按 composite 重排。"""
    rows = [_row("600001", 90.0),   # unlock medium 12% → 罚 4.8 → 85.2
            _row("600002", 80.0),   # unlock low → 不罚 → 80.0
            _row("600003", 86.0)]   # unlock medium 30% → 罚 8（封顶）→ 78.0
    scan_map = {"600001": _scan("medium", 12.0),
                "600002": _scan("low", 2.0),
                "600003": _scan("high", 30.0)}
    out = re_eng.apply_unlock_penalty(rows, scan_map)
    by = {r["code"]: r for r in out}
    assert by["600001"]["composite"] == pytest.approx(85.2, abs=0.05)
    assert by["600002"]["composite"] == pytest.approx(80.0, abs=1e-9)
    assert by["600003"]["composite"] == pytest.approx(78.0, abs=0.05)
    # 重排：85.2 > 80.0 > 78.0
    assert [r["code"] for r in out] == ["600001", "600002", "600003"]
    # 透明记录 + reasons
    assert by["600003"]["risk_penalty"]["unlock"]["penalty"] == pytest.approx(8.0, abs=0.01)
    joined = " ".join(by["600003"]["reasons"])
    assert "解禁" in joined and "[风险]" in joined


def test_unlock_unknown_or_low_or_missing_no_penalty():
    """unknown/low/组件缺失/not_scanned → 不罚不编造，composite 不变。"""
    rows = [_row("600001", 90.0),            # unknown
            _row("600002", 88.0),            # low
            _row("600003", 86.0),            # scan_map 无 unlock 组件
            _row("600004", 84.0, scanned=False)]  # not_scanned
    scan_map = {"600001": _scan("unknown", None),
                "600002": _scan("low", 2.0),
                "600003": {"components": {}, "report": {}}}
    out = re_eng.apply_unlock_penalty(rows, scan_map)
    assert [r["composite"] for r in out] == [90.0, 88.0, 86.0, 84.0]
    for r in out:
        assert "unlock" not in (r.get("risk_penalty") or {}), "未罚行不得伪造 unlock 罚分记录"


# ─────────────── 主流程接线（源码契约） ───────────────
def test_wiring_in_source():
    src = inspect.getsource(re_eng)
    assert "continuous_risk_penalty(df" in src, "阶段 3 rows 循环未接连续风险惩罚"
    assert "apply_unlock_penalty(rows, scan_map)" in src, "闸门后未接解禁扣分"
    assert '"risk_penalty"' in src, "风险惩罚元数据未透明落 row"
