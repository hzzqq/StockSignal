"""decision.derive_position 边界与极端行情测试（I9 + I10）。

锁死三件事：
1. 温度基准为 0/100 时仓位被夹在 [5, 95]（基础边界，防黑箱）。
2. 缺失因子（晋级率=None / 周期空串）不加不减、不抛。
3. 极端行情硬约束（I10）：冰点退潮双杀 regime 仓位不超 30%；
   过热高潮分化 regime 仓位不低于 40% —— 作为风控底线的不变量。
"""

import pytest

from modules.decision import derive_position


def test_temp_zero_floor():
    pos = derive_position(0)
    assert pos["pct"] == 5
    assert pos["band"] == "防御"


def test_temp_100_ceiling():
    pos = derive_position(100)
    assert pos["pct"] == 95
    assert pos["band"] == "激进"


def test_temp_none_fallback_to_50():
    pos = derive_position(None)
    assert pos["pct"] == 50
    assert pos["band"] == "中性"


def test_promo_none_no_adjustment():
    base = derive_position(50, overall_promo=None)
    assert base["pct"] == 50
    # 不应出现任何晋级率相关 reason
    assert not any("梯队" in r for r in base["reasons"])


def test_empty_cycle_no_adjustment():
    base = derive_position(50, cycle_name="")
    assert base["pct"] == 50
    assert not any("情绪周期" in r for r in base["reasons"])


def test_basic_accumulation():
    pos = derive_position(50, bias="偏多", cycle_name="主升高潮", overall_promo=70)
    # 50 +8(偏多) +5(主升) +5(晋级率≥60) = 68 → 偏多档
    assert pos["pct"] == 68
    assert pos["band"] == "偏多"
    # 三条调节 reason 都应出现
    assert any("偏多" in r for r in pos["reasons"])
    assert any("主升高潮" in r for r in pos["reasons"])
    assert any("晋级率" in r for r in pos["reasons"])


def test_clamp_5_95_explicit():
    # 极端负向：温度极低 + 退潮 + 偏空 + 晋级率断档
    pos = derive_position(5, bias="偏空", cycle_name="退潮", overall_promo=5)
    # 5 -8 -10 -6 = -19 → clamp 5
    assert pos["pct"] == 5


# ── I10：极端行情硬约束不变量 ──
@pytest.mark.parametrize("temp", [0, 5, 10, 15, 19])
def test_extreme_low_regime_capped_at_30(temp):
    """冰点退潮双杀：温度<20 且退潮，仓位不得越过 30%（风控上沿）。"""
    pos = derive_position(temp, cycle_name="退潮")
    assert pos["pct"] <= 30


@pytest.mark.parametrize("temp", [80, 85, 90, 100])
def test_extreme_high_regime_floored_at_40(temp):
    """过热高潮分化：温度>=80 且高潮分化，仓位不得低于 40%（风控下沿）。"""
    pos = derive_position(temp, cycle_name="高潮分化")
    assert pos["pct"] >= 40


def test_extreme_low_with_bullish_override_still_capped():
    """即便其余因子偏多，冰点退潮 regime 也不许重仓接飞刀（仓位封顶 30%）。

    说明：温度即基准仓位，temp<20 时常规推导已天然 ≤30，
    故硬约束多作为「最后防线」锁死上沿；此处断言不变量成立。
    """
    pos = derive_position(19, bias="偏多", cycle_name="退潮", overall_promo=90)
    assert pos["pct"] <= 30
    # 若约束真正介入（少数高 temp 边界被其他正因子推过线），应留风控留痕
    if pos["pct"] >= 30:
        assert any("极端风控" in r for r in pos["reasons"])
