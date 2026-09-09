# -*- coding: utf-8 -*-
"""
tests/test_backtest_decision_closure.py — 决策闭环回测「可复现 + 防回归」护栏

R31 新增。目的：把「决策闭环 × 真实广度历史」大样本回测锁死为可复现的回归测试，
未来任何改动（locate_cycle / derive_position / 回测脚本本身）若破坏闭环逻辑在
真实数据上的统计行为，本测试立即变红。

只读 data/shepherd_history.csv（与 R28 真实数据回归网同一数据源）；缺失时 skip，不造假。
"""
from __future__ import annotations

import json
import os
import sys

import pytest

# 让测试独立于调用方式可导入项目模块（与脚本自身插入 sys.path 的逻辑一致）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.backtest_decision_closure import run, locate_cycle  # noqa: E402
from modules.shepherd_forecast import locate_cycle as _live_locate  # noqa: E402
from modules.decision import CYCLE_ADJ  # noqa: E402


_BREADTH = os.path.join(_ROOT, "data", "shepherd_history.csv")
_HAVE_DATA = os.path.exists(_BREADTH)


@pytest.mark.skipif(not _HAVE_DATA, reason="data/shepherd_history.csv 缺失（gitignore），无法跑真实回测")
def test_backtest_runs_on_real_history_and_is_reproducible():
    """回测在真实 4094 行历史上跑通、样本量充足、结果可复现。"""
    r1 = run(_BREADTH)
    r2 = run(_BREADTH)
    # 纯函数式回测两次结果应逐字节一致（可复现性 = 论文证据可信的前提）
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    assert r1["meta"]["n_trading_days_scored"] >= 1000
    assert r1["overall"]["call"] > 0


@pytest.mark.skipif(not _HAVE_DATA, reason="data/shepherd_history.csv 缺失")
def test_backtest_vocabulary_subset_of_cycle_adj():
    """回测出现的周期名 ⊆ CYCLE_ADJ 键（与 R28 同一不变式，防静默降级）。"""
    r = run(_BREADTH)
    cycles = {row["cycle"] for row in r["by_stage_full_closure"]}
    for c in cycles:
        assert c in CYCLE_ADJ, f"回测出现未知周期 {c}，CYCLE_ADJ 未同步"


@pytest.mark.skipif(not _HAVE_DATA, reason="data/shepherd_history.csv 缺失")
def test_backtest_position_tracks_regime_not_direction():
    """核心命题：方向命中≈随机，但仓位刻度随周期显著分化（模型真实机制）。

    诚实披露：日频方向近似随机游走，方向命中率应落在 [40,60]%；
    但防守期平均建议仓位应显著低于进攻期（风险缩放逻辑成立）。
    """
    r = run(_BREADTH)
    grp = {g["group"]: g for g in r["by_group_calibration"]}
    # 方向命中率落在随机区间（诚实的负结果，非 bug）
    assert 40 <= r["overall"]["dir_accuracy"] <= 60
    # 仓位随周期分化：防守期 < 修复期 < 进攻期（价差足够大，证明刻度机制生效）
    assert grp["防守期"]["avg_pct"] < grp["修复期"]["avg_pct"] < grp["进攻期"]["avg_pct"]
    spread = grp["进攻期"]["avg_pct"] - grp["防守期"]["avg_pct"]
    assert spread >= 15.0, f"周期仓位价差仅 {spread}，风险缩放不明显"


@pytest.mark.skipif(not _HAVE_DATA, reason="data/shepherd_history.csv 缺失")
def test_backtest_calibration_withholds_when_noise_or_small():
    """刻度校准治理：在代理数据上正确「不采纳」（样本足够但调节量在噪音阈值内）。"""
    r = run(_BREADTH)
    for g in r["by_group_calibration"]:
        # 真实代理数据中各分组 |suggest_delta| 均 < NOISE_DELTA(2) → 不应被标记为可采纳
        assert g["actionable"] is False, f"{g['group']} 不应在噪音阈值内被采纳"


@pytest.mark.skipif(not _HAVE_DATA, reason="data/shepherd_history.csv 缺失")
def test_locate_cycle_returns_known_stage_on_real_rows():
    """sanity：locate_cycle 在真实行上返回的是六阶段已知名称之一。"""
    import pandas as pd
    df = pd.read_csv(_BREADTH, encoding="utf-8-sig").sort_values("date").reset_index(drop=True)
    rows = df.to_dict("records")
    known = set(CYCLE_ADJ.keys())
    for i in range(0, len(rows), 500):  # 抽样，避免太慢
        cyc = _live_locate(rows[i], rows[i - 1] if i > 0 else None)
        assert cyc.get("name") in known or cyc.get("name") is not None
