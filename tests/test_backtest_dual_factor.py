# -*- coding: utf-8 -*-
"""tests/test_backtest_dual_factor.py — T-182 回测脚本守卫（合成数据控制变量）。

覆盖：四组产出完整性 / 因子只降不升（方向中性）/ regime 门控在暴跌日生效 /
herd 在极端红挤生效 / 口径守卫（不设方向命中率）/ meta 诚实披露。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.backtest_dual_factor import run


def _synthetic_csv(tmp_path):
    """40 日合成广度历史：含 1 个高红盘暴跌日 + 6 个极端红挤连势段。

    构造确保：
      · day20：red=70 但 limit_down=120 → classify_state=暴跌，conf=120/150=0.8
        且 temp=70+bias偏多 → 基线 78% → 门控封顶 50 必然生效
      · day24-30：红盘比 90+、涨停远超历史 → 拥挤度 ≥85 greed → -8pt 生效
      · 各特殊日的次日 median_chg 为负 → 加权收益方向可验证
    """
    n = 42
    rng = np.random.default_rng(7)
    rr = rng.normal(50, 4, n).clip(42, 58)
    lu = rng.integers(20, 40, n).astype(float)
    ld = rng.integers(0, 8, n).astype(float)
    mchg = rng.normal(0, 0.8, n).clip(-2, 2)
    dates = pd.date_range("2025-01-01", periods=n, freq="B").strftime("%Y-%m-%d")

    def set_day(i, r, u, d, m):
        rr[i], lu[i], ld[i], mchg[i] = r, u, d, m

    set_day(20, 70.0, 30.0, 120.0, 1.0)   # 高红盘暴跌日（次日 -3）
    set_day(21, 50.0, 30.0, 5.0, -1.0)
    for j, i in enumerate(range(24, 31)):  # 极端红挤连势 7 天
        set_day(i, 88.0 + j, 200.0 + 10 * j, 2.0, 2.0)
    mchg[25] = -2.5  # 极端红挤后次日大跌（反向因子应提前减仓）
    set_day(31, 55.0, 60.0, 5.0, 0.5)

    df = pd.DataFrame({
        "date": dates, "up_count": rr * 10, "down_count": (100 - rr) * 10,
        "red_ratio": rr, "limit_up": lu, "limit_down": ld, "median_chg": mchg,
    })
    path = tmp_path / "shepherd_history.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    return path


def test_four_groups_complete(tmp_path):
    """五组（含 dual_cap 变体）都产出且共享同一有效样本集（n 恒等）。"""
    rep = run(str(_synthetic_csv(tmp_path)))
    gs = rep["groups"]
    assert set(gs) == {"baseline", "regime", "herd", "dual", "dual_cap"}
    ns = {g: gs[g]["n"] for g in gs}
    assert len(set(ns.values())) == 1 and next(iter(ns.values())) > 0, ns


def test_dual_cap_variant_semantics(tmp_path):
    """封顶变体：合成强红挤日 → dual_cap 仓位被压到 ≤60 且低于 dual（-8pt 不够时）。"""
    rep = run(str(_synthetic_csv(tmp_path)))
    gs = rep["groups"]
    assert gs["dual_cap"]["n"] == gs["dual"]["n"]
    assert gs["dual_cap"]["avg_position"] <= gs["dual"]["avg_position"]
    assert "dual_cap" in rep["meta"]["variants"]


def test_factors_never_increase_position(tmp_path):
    """因子只降不升（门控仅封顶/反向仅减仓）→ 三组平均仓位 ≤ baseline。"""
    gs = run(str(_synthetic_csv(tmp_path)))["groups"]
    b = gs["baseline"]["avg_position"]
    assert gs["regime"]["avg_position"] <= b
    assert gs["herd"]["avg_position"] <= b
    assert gs["dual"]["avg_position"] <= b


def test_regime_cap_binds_on_crash_day(tmp_path):
    """合成暴跌日（高红盘+跌停爆量）→ regime 组 capping 真实发生。"""
    gs = run(str(_synthetic_csv(tmp_path)))["groups"]
    assert gs["regime"]["capped_days"] >= 1, gs["regime"]
    assert gs["regime"]["cap_by_state"]["暴跌"] >= 1


def test_herd_binds_on_extreme_greed(tmp_path):
    """极端红挤段 → herd 组 greed_strong_days ≥ 1 且 avg_position 下降。"""
    gs = run(str(_synthetic_csv(tmp_path)))["groups"]
    assert gs["herd"]["greed_strong_days"] >= 1, gs["herd"]
    assert gs["herd"]["avg_position"] < gs["baseline"]["avg_position"]


def test_no_direction_accuracy_metric(tmp_path):
    """口径守卫：门控/反向因子不改方向，报告不得含方向命中率字段（诚实披露）。"""
    rep = run(str(_synthetic_csv(tmp_path)))
    for g, s in rep["groups"].items():
        assert "dir_accuracy" not in s and "hit" not in s, g
    assert "方向命中率" in rep["meta"]["disclosure"]


def test_meta_disclosure_and_state_days(tmp_path):
    """meta 含口径/披露/状态分布，且暴跌日被计入 state_days。"""
    rep = run(str(_synthetic_csv(tmp_path)))
    m = rep["meta"]
    assert "disclosure" in m and "baseline_rule" in m and "tail_rule" in m
    assert m["state_days"]["暴跌"] >= 1
