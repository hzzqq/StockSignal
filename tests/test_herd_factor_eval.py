# -*- coding: utf-8 -*-
"""tests/test_herd_factor_eval.py — 拥挤度因子化验证脚本守卫（T-184 · 自研延伸）。

合成数据覆盖：分桶统计正确性 / Spearman 单调性方向 / 状态分桶 / 诚实口径
（空桶 n=0 字段 None）/ meta 披露完整性。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.herd_factor_eval import run


@pytest.fixture()
def synthetic_csv(tmp_path):
    """120 日合成：前 100 日中性随机、末 20 日红挤渐强 + 次日收益随拥挤度递减。

    构造使「拥挤度越高次日越差」在贪婪端成立 → Spearman rho 应为负。
    """
    rng = np.random.default_rng(9)
    n = 122
    rr = rng.normal(50, 4, n).clip(42, 58)
    lu = rng.integers(20, 40, n).astype(float)
    ld = rng.integers(0, 6, n).astype(float)
    mchg = rng.normal(0, 0.8, n).clip(-2, 2)
    # 末 20 日：连续强红（拥挤度爬升），次日收益线性走弱（-0.05/日 → 累计明显）
    for j, i in enumerate(range(n - 20, n - 1)):
        rr[i] = 70 + j  # 70 → 89 渐强
        lu[i] = 150 + 5 * j
        ld[i] = 2.0
        mchg[i + 1] = 1.0 - 0.15 * j  # 次日收益递减（拥挤度惩罚）
    dates = pd.date_range("2025-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    df = pd.DataFrame({"date": dates, "red_ratio": rr, "limit_up": lu,
                       "limit_down": ld, "median_chg": mchg})
    p = tmp_path / "shepherd_history.csv"
    df.to_csv(p, index=False, encoding="utf-8")
    return str(p)


def test_buckets_and_spearman_negative(synthetic_csv):
    """合成「红挤越强次日越差」→ 贪婪端 Spearman rho<0；分桶 n 汇总一致。"""
    rep = run(synthetic_csv)
    sp = rep["monotonic"]["greed_side_score_vs_next_chg"]
    assert sp is not None and sp["rho"] < 0, sp
    assert sp["n"] >= 10
    ns = [b["n"] for b in rep["by_crowding_bucket"]]
    assert sum(ns) == rep["meta"]["n_scored"]


def test_empty_bucket_honest_none(synthetic_csv):
    """空桶如实 n=0 且字段 None（绝不编造 0 收益）。"""
    rep = run(synthetic_csv)
    for b in rep["by_crowding_bucket"]:
        if b["n"] == 0:
            assert b["avg_next_chg"] is None and b["up_frac"] is None


def test_state_buckets_present(synthetic_csv):
    """五状态分桶齐全，普涨/震荡必有样本。"""
    bs = rep["by_state"] if (rep := run(synthetic_csv)) else None
    assert set(bs) == {"暴跌", "恐慌", "震荡", "结构牛", "普涨"}
    assert bs["普涨"]["n"] > 0 or bs["震荡"]["n"] > 0


def test_meta_disclosure(synthetic_csv):
    """meta 含无前视披露与阈值单一真理源引用。"""
    rep = run(synthetic_csv)
    assert "无前视" in rep["meta"]["disclosure"]
    assert rep["meta"]["thresholds"]["strong"] == 85.0
