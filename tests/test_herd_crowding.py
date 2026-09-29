# -*- coding: utf-8 -*-
"""tests/test_herd_crowding.py — 羊群拥挤度指标守卫（T-182 因子 B）。

覆盖：纯函数计算正确性 / 方向侧语义（greed·fear）/ 无前视历史分位 /
诚实降级（缺失返 unavailable 绝不默认 0）/ 阈值常量契约。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from modules.herd_crowding import (
    MILD_CROWD,
    STRONG_CROWD,
    compute_crowding,
    crowding_from_history,
)


# ───────────── 纯函数 compute_crowding ─────────────

def test_neutral_inputs_low_score():
    """中性市场（红盘比近 50、无极端家数、无连势）→ 低拥挤分。"""
    out = compute_crowding(red_ratio=52.0, limit_up_pct=0.5, limit_down_pct=0.5,
                           streak_days=1)
    assert out["status"] == "ok"
    assert out["score"] < 50.0, out


def test_extreme_greed_high_score_and_side():
    """极端红挤：红盘比 90 + 涨停分位 0.95 + 连续 5 天红 → 高分且 side=greed。"""
    out = compute_crowding(red_ratio=90.0, limit_up_pct=0.95, limit_down_pct=0.01,
                           streak_days=5)
    assert out["status"] == "ok"
    assert out["side"] == "greed"
    assert out["score"] >= STRONG_CROWD, out


def test_extreme_fear_side():
    """极端绿挤：红盘比 10 + 跌停分位 0.95 + 连续 5 天绿 → side=fear 且高分。

    heat 取「方向端」分位：fear 端用 limit_down_pct（跌停潮=恐慌参与极端）。
    """
    out = compute_crowding(red_ratio=10.0, limit_up_pct=0.01, limit_down_pct=0.95,
                           streak_days=5)
    assert out["status"] == "ok"
    assert out["side"] == "fear"
    assert out["score"] >= STRONG_CROWD, out


def test_score_monotonic_in_streak():
    """连势越长分越高（单调性）。"""
    scores = [
        compute_crowding(red_ratio=80.0, limit_up_pct=0.8, limit_down_pct=0.1,
                         streak_days=d)["score"]
        for d in (0, 2, 5)
    ]
    assert scores[0] < scores[1] < scores[2], scores


def test_streak_capped():
    """连势封顶 5 天：6 天与 5 天同分（防止无限连势虚高）。"""
    a = compute_crowding(red_ratio=80.0, limit_up_pct=0.8, limit_down_pct=0.1,
                         streak_days=5)
    b = compute_crowding(red_ratio=80.0, limit_up_pct=0.8, limit_down_pct=0.1,
                         streak_days=9)
    assert a["score"] == b["score"]


def test_missing_input_unavailable_never_zero():
    """诚实降级：核心输入缺失 → status=unavailable + score=None，绝不默认 0。"""
    for kwargs in (
        dict(red_ratio=None, limit_up_pct=0.5, limit_down_pct=0.5, streak_days=1),
        dict(red_ratio=60.0, limit_up_pct=None, limit_down_pct=0.5, streak_days=1),
        dict(red_ratio=60.0, limit_up_pct=0.5, limit_down_pct=0.5, streak_days=None),
        dict(red_ratio=float("nan"), limit_up_pct=0.5, limit_down_pct=0.5, streak_days=1),
    ):
        out = compute_crowding(**kwargs)
        assert out["status"] == "unavailable", kwargs
        assert out["score"] is None, kwargs


def test_red_ratio_exactly_50_side_none():
    """红盘比恰为 50 → 无方向一致性，side=None（多空对轰不属羊群）。"""
    out = compute_crowding(red_ratio=50.0, limit_up_pct=0.9, limit_down_pct=0.9,
                           streak_days=5)
    assert out["side"] is None
    assert out["score"] < MILD_CROWD, out


def test_threshold_contract():
    """阈值契约：strong > mild，且 decision 端引用同一常量（单一真理源）。"""
    assert STRONG_CROWD > MILD_CROWD
    from modules import decision
    assert decision.MILD_CROWD == MILD_CROWD
    assert decision.STRONG_CROWD == STRONG_CROWD


# ───────────── crowding_from_history（无前视历史入口） ─────────────

def _mk_history(n: int = 30) -> pd.DataFrame:
    """构造可控广度历史：前段中性、末 5 天连续强红+涨停放量。"""
    rng = np.random.default_rng(42)
    rr = rng.normal(50, 5, n).clip(30, 70)
    lu = rng.integers(20, 60, n).astype(float)
    ld = rng.integers(0, 10, n).astype(float)
    # 末 5 天：连续强红、涨停爆量
    rr[-5:] = [85, 88, 90, 92, 94]
    lu[-5:] = [120, 150, 180, 200, 220]
    df = pd.DataFrame({
        "red_ratio": rr, "limit_up": lu, "limit_down": ld,
        "median_chg": rng.normal(0, 1.5, n),
    })
    return df


def test_from_history_no_lookahead():
    """涨停分位只用截至前一日的历史：对当日行，分位 < 用含当日计算的分位。"""
    df = _mk_history(30)
    idx = 29  # 最后一天（涨停 220，历史前 29 天最大 60 → 分位应为 1.0 以下但由前 29 天算）
    out = crowding_from_history(df, idx)
    assert out["status"] == "ok"
    # 无前视：今日 220 不参与自身分位 → 分位由前 29 天（max≈60 附近）得出 = 1.0
    assert out["parts"]["heat"] == pytest.approx(1.0)
    # streak：末 5 天全 >50 → 含当日连续 5 天
    assert out["parts"]["streak_days"] == 5


def test_from_history_missing_row_unavailable():
    """当日行关键列缺失 → unavailable（诚实降级），绝不编造。"""
    df = _mk_history(10)
    df.loc[9, "red_ratio"] = np.nan
    out = crowding_from_history(df, 9)
    assert out["status"] == "unavailable"
    assert out["score"] is None


def test_from_history_first_day():
    """首日：历史为空 → 分位缺数据 → unavailable（不臆造）。"""
    df = _mk_history(10)
    out = crowding_from_history(df, 0)
    assert out["status"] == "unavailable"
