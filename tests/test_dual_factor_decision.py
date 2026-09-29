# -*- coding: utf-8 -*-
"""tests/test_dual_factor_decision.py — derive_position 双因子增强守卫（T-182）。

覆盖：默认行为不变性（None 因子=旧版逐位一致）/ herd 反向调节 / regime
状态门控 / 诚实降级（低置信度·缺置信度不启用）/ reasons 留痕 / 叠加次序。
"""
from __future__ import annotations

import logging

import pytest

from modules.decision import (
    REGIME_CAPS,
    derive_position,
)
from modules.herd_crowding import MILD_CROWD, STRONG_CROWD

# 固定基线入参：temp=90 偏多 → 高仓位，便于验证各类「封顶/减仓」确实生效
_HI = dict(temp=90.0, bias="偏多", cycle_name="主升高潮")  # 90+8+5=103 → clamp 95
_LO = dict(temp=30.0, bias="偏空", cycle_name="退潮")       # 30-8-10=12


# ───────────── 向后兼容：默认因子 None 行为逐位不变 ─────────────

def test_backward_compat_none_factors():
    """不传新参数与显式传 None：输出完全一致（默认行为不变铁律）。"""
    a = derive_position(**_HI)
    b = derive_position(**_HI, herd_score=None, herd_side=None,
                        regime_state=None, regime_confidence=None)
    assert a == b


def test_baseline_high_position():
    """基线锚定：高仓位输入 → 95（验证后续封顶用例的「未封顶前」前提成立）。"""
    out = derive_position(**_HI)
    assert out["pct"] == 95


# ───────────── 因子 B：羊群拥挤反向调节 ─────────────

def test_herd_greed_extreme_minus8():
    """极端红挤（≥STRONG_CROWD）→ 相比基线减 8pt。"""
    base = derive_position(**dict(temp=60.0, bias="中性"))
    out = derive_position(temp=60.0, bias="中性",
                          herd_score=STRONG_CROWD + 5, herd_side="greed")
    assert out["pct"] == base["pct"] - 8
    assert any("羊群" in r for r in out["reasons"])


def test_herd_greed_moderate_minus4():
    """中度红挤（MILD~STRONG 区间）→ 减 4pt。"""
    base = derive_position(temp=60.0, bias="中性")
    out = derive_position(temp=60.0, bias="中性",
                          herd_score=(MILD_CROWD + STRONG_CROWD) / 2,
                          herd_side="greed")
    assert out["pct"] == base["pct"] - 4


def test_herd_below_mild_no_change():
    """拥挤度低于 MILD_CROWD → 不调节。"""
    base = derive_position(temp=60.0, bias="中性")
    out = derive_position(temp=60.0, bias="中性", herd_score=MILD_CROWD - 1,
                          herd_side="greed")
    assert out["pct"] == base["pct"]


def test_herd_fear_never_reduces():
    """绿挤（fear）不减仓——与「冰点+5 超卖试探」既有语义自洽；方向仍由 bias 承担。"""
    base = derive_position(temp=60.0, bias="中性")
    out = derive_position(temp=60.0, bias="中性", herd_score=STRONG_CROWD + 10,
                          herd_side="fear")
    assert out["pct"] == base["pct"]


def test_herd_unknown_side_warns(caplog):
    """未知 side 不静默：warning + 不调节。"""
    with caplog.at_level(logging.WARNING, logger="modules.decision"):
        base = derive_position(temp=60.0, bias="中性")
        out = derive_position(temp=60.0, bias="中性", herd_score=90.0,
                              herd_side="恐慌盘")
    assert out["pct"] == base["pct"]
    assert any("未知羊群方向" in r.message for r in caplog.records)


def test_herd_none_score_untouched():
    """herd_score=None（指标不可用）→ 完全不调节、不留「已调节」痕迹。"""
    base = derive_position(temp=60.0, bias="中性")
    out = derive_position(temp=60.0, bias="中性", herd_score=None, herd_side="greed")
    assert out["pct"] == base["pct"]


# ───────────── 因子 A：regime 状态门控 ─────────────

def test_regime_panic_caps_60():
    """恐慌 + 高置信度 → 封顶 60（基线 95 被压）。"""
    out = derive_position(**_HI, regime_state="恐慌", regime_confidence=0.8)
    assert out["pct"] == 60
    assert any("状态门控" in r for r in out["reasons"])


def test_regime_crash_caps_50():
    """暴跌 + 高置信度 → 封顶 50。"""
    out = derive_position(**_HI, regime_state="暴跌", regime_confidence=0.9)
    assert out["pct"] == 50


def test_regime_low_confidence_inactive():
    """置信度 <0.5 → 门控不启用（诚实：不确定的判断不硬压仓位）。"""
    out = derive_position(**_HI, regime_state="恐慌", regime_confidence=0.49)
    assert out["pct"] == 95
    assert any("置信度" in r for r in out["reasons"])


def test_regime_missing_confidence_inactive():
    """置信度缺失（None）→ 不启用（不臆造门控）。"""
    out = derive_position(**_HI, regime_state="暴跌", regime_confidence=None)
    assert out["pct"] == 95


def test_regime_bull_no_floor_lift():
    """结构牛/普涨不在门控目录 → 不抬底不封顶（仅防守型门控）。"""
    base = derive_position(**_LO)
    out = derive_position(**_LO, regime_state="结构牛", regime_confidence=0.9)
    assert out["pct"] == base["pct"]


def test_regime_neutral_state_untouched():
    """震荡（最常见状态）→ 与基线一致。"""
    base = derive_position(**_HI)
    out = derive_position(**_HI, regime_state="震荡", regime_confidence=0.6)
    assert out["pct"] == base["pct"]


def test_regime_unknown_state_warns(caplog):
    """未知状态不静默：warning + 不封顶。"""
    with caplog.at_level(logging.WARNING, logger="modules.decision"):
        out = derive_position(**_HI, regime_state="疯牛", regime_confidence=0.9)
    assert out["pct"] == 95
    assert any("未知市场状态" in r.message for r in caplog.records)


def test_regime_valid_ungated_states_silent(caplog):
    """合法非门控状态（震荡/结构牛/普涨）：不告警不留痕（正常状态非噪声）。"""
    with caplog.at_level(logging.WARNING, logger="modules.decision"):
        for st in ("震荡", "结构牛", "普涨"):
            out = derive_position(**_HI, regime_state=st, regime_confidence=0.9)
            assert out["pct"] == 95
            assert not any("不在门控目录" in r for r in out["reasons"]), st
    assert not any("未知市场状态" in r.message for r in caplog.records)


def test_regime_caps_contract():
    """门控目录契约：暴跌 < 恐慌（更严），且只含防守状态。"""
    assert REGIME_CAPS["暴跌"] < REGIME_CAPS["恐慌"]
    assert set(REGIME_CAPS) == {"暴跌", "恐慌"}


# ───────────── 叠加与留痕 ─────────────

def test_dual_factors_stack():
    """双因子叠加：greed 减仓与 regime 封顶并存，最终受封顶约束。"""
    out = derive_position(**_HI, herd_score=95.0, herd_side="greed",
                          regime_state="暴跌", regime_confidence=0.9)
    assert out["pct"] == 50  # 95-8=87 → 暴跌封顶 50
    reasons = " ".join(out["reasons"])
    assert "羊群" in reasons and "状态门控" in reasons


def test_explain_contributions_traceable():
    """explain=True 时 contributions 含新因子条目（可解释性契约）。

    前提：高仓位基线（95）- herd 8pt = 87 → 恐慌封顶 60 真正生效，
    两类因子条目都进入 contributions。
    """
    out = derive_position(**_HI, herd_score=90.0, herd_side="greed",
                          regime_state="恐慌", regime_confidence=0.8, explain=True)
    factors = [c["factor"] for c in out["contributions"]]
    assert any("羊群" in f for f in factors), factors
    assert any("状态门控" in f for f in factors), factors
    assert out["pct"] == 60


# ───────────── mutation 自检锚（防假绿提示：改阈值/改调节量必红） ─────────────

def test_mutation_anchor_cap_values():
    """若把恐慌封顶改回 95/暴跌改 95，test_regime_*_caps 必红——锚定 mutation 面。"""
    assert REGIME_CAPS["恐慌"] == 60.0
    assert REGIME_CAPS["暴跌"] == 50.0
    assert STRONG_CROWD == 85.0
