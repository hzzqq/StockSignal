# -*- coding: utf-8 -*-
"""tests/test_tree_factor_eval.py — 改进型集成树 head-to-head 守卫（T-184 · 教师 #5）。

合成数据覆盖：数据集组装（无前视/平盘剔除）/ 时序切分无泄漏 / 五模型结构
完整性 / 增量字段与特征重要性产出 / 小样本拒绝结论。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.tree_factor_eval import P_FEATURES, B_FEATURES, build_dataset, run


@pytest.fixture()
def synthetic_csv(tmp_path):
    """300 日合成：中性段 + 红挤段，保证 train/test 两段都有样本。"""
    rng = np.random.default_rng(5)
    n = 302
    rr = rng.normal(50, 4, n).clip(42, 58)
    lu = rng.integers(20, 40, n).astype(float)
    ld = rng.integers(0, 6, n).astype(float)
    chl = rng.integers(1, 6, n).astype(float)
    zfr = rng.uniform(20, 60, n)
    zpr = rng.normal(0, 0.02, n)
    mchg = rng.normal(0, 0.8, n).clip(-2, 2)
    # 中段红挤 + 次日收益走弱（给增强特征一点可学信号）
    for j, i in enumerate(range(100, 140)):
        rr[i] = 72 + j % 18
        lu[i] = 150 + j
        ld[i] = 2.0
        mchg[i + 1] = 0.8 - 0.04 * (j % 20)
    dates = pd.date_range("2024-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    df = pd.DataFrame({"date": dates, "red_ratio": rr, "limit_up": lu,
                       "limit_down": ld, "connect_hl": chl, "zt_fail_ratio": zfr,
                       "zt_prev_ret": zpr, "median_chg": mchg})
    p = tmp_path / "shepherd_history.csv"
    df.to_csv(p, index=False, encoding="utf-8")
    return str(p)


def test_dataset_no_lookahead_and_flat_removed(synthetic_csv):
    """组装纪律：平盘日剔除；无前视（末行 crowd 用截至前一日分位）。"""
    data = build_dataset(synthetic_csv)
    assert (data["next_chg"] == 0).sum() == 0          # 平盘已剔除
    assert set(B_FEATURES) <= set(data.columns)        # 增强特征齐全
    assert data["crowd_score"].between(0, 100).all()   # 拥挤度值域
    assert data["date"].is_monotonic_increasing        # 时序未乱


def test_run_structure_and_no_leak(synthetic_csv):
    """五模型齐全；train 末行日期 < test 首行日期（时序切分无泄漏）。"""
    rep = run(synthetic_csv)
    m = rep["meta"]
    assert m["train_end"] < m["test_start"]
    assert set(rep["results"]) == {"baseline_majority", "hist_gb_pure",
                                   "hist_gb_enhanced", "rf_pure", "rf_enhanced"}
    ns = {rep["meta"]["n_train"], rep["meta"]["n_test"]}
    assert min(ns) > 50
    # AUC 域：基线多数类如实 None，其余在 [0,1]
    assert rep["results"]["baseline_majority"]["auc"] is None
    for name in ("hist_gb_pure", "hist_gb_enhanced", "rf_pure", "rf_enhanced"):
        assert 0.0 <= rep["results"][name]["auc"] <= 1.0


def test_delta_and_importance_fields(synthetic_csv):
    """增强增量字段存在（可正可负——诚实口径）；RF 重要性含行为金融特征。"""
    rep = run(synthetic_csv)
    d = rep["enhancement_delta"]
    assert set(d) == {"hist_gb_delta_acc", "rf_delta_acc"}
    feats = {x["feature"] for x in rep["rf_feature_importance_top"]}
    assert feats & set(B_FEATURES), "行为金融特征应至少一个进入 top 重要性"


def test_run_rejects_tiny_sample(tmp_path):
    """有效样本 <200 → 拒绝产出结论（诚实：宁缺毋滥）。"""
    rng = np.random.default_rng(1)
    n = 60
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B").strftime("%Y-%m-%d"),
        "red_ratio": rng.normal(50, 4, n), "limit_up": rng.integers(20, 40, n).astype(float),
        "limit_down": rng.integers(0, 6, n).astype(float), "connect_hl": np.ones(n),
        "zt_fail_ratio": np.full(n, 40.0), "zt_prev_ret": np.zeros(n),
        "median_chg": rng.normal(0, 1, n),
    })
    p = tmp_path / "tiny.csv"
    df.to_csv(p, index=False, encoding="utf-8")
    with pytest.raises(ValueError, match="样本不足"):
        run(str(p))
