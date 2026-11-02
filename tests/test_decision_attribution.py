"""决策闭环可解释归因单元测试。

守卫要点：
* explain=True 返回 contributions（因子贡献）+ sensitivity（单因子 ±5 局部敏感度）；
* contributions 各 delta 之和 == 最终仓位 − 基准温度（内部一致，单一真理源）；
* 默认 explain=False 不返回 contributions（向后兼容，不改既有调用方语义）；
* overall_promo=None 时既不加不减也不崩溃；
* 极端输入下 pct 仍被 clamp 在 [5,95]（双保险守卫不变）。
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.decision import derive_position  # noqa: E402


def test_explain_returns_contrib_and_sensitivity():
    r = derive_position(temp=65, bias="偏多", cycle_name="主升", overall_promo=70,
                        event_adj=3, explain=True)
    assert "contributions" in r and "sensitivity" in r
    assert len(r["contributions"]) >= 4  # 基准 + 方向 + 周期(若有) + 梯队 + 事件


def test_contrib_sum_consistent():
    temp = 60
    r = derive_position(temp=temp, bias="偏多", cycle_name="修复确认",
                        overall_promo=50, event_adj=None, explain=True)
    total_delta = sum(c["delta"] for c in r["contributions"])
    last = r["contributions"][-1]["running"]
    # 2026-11-02 守卫纠偏：毕设#1 model_adj 引入 0.01pp 小数步长（有界修正），
    # 返回的 pct 仍是整数展示值 int(round())（见 test_decision_model_adj 不变量2），
    # 旧断言「末项 running == pct」只在全整数调节时代成立。
    # 链内一致性（真值层）：Σdelta == 末项 running − 基准，精度由 delta 决定；
    # 展示层：整数 pct 必须是链末真值的四舍五入（差 ≤ 0.5）。
    assert abs(total_delta - (last - temp)) < 1e-6
    assert abs(last - r["pct"]) <= 0.5 + 1e-9


def test_default_explain_backward_compatible():
    r = derive_position(temp=60, bias="偏多")
    assert "contributions" not in r
    assert "sensitivity" not in r


def test_promo_none_no_crash_no_contrib():
    r = derive_position(temp=50, bias="中性", cycle_name=None,
                        overall_promo=None, explain=True)
    assert r["pct"] == 50
    # 无梯队贡献项
    assert not any("梯队" in c["factor"] for c in r["contributions"])


def test_sensitivity_temp_moves_position():
    base = derive_position(temp=50, explain=True)
    assert base["sensitivity"]["temp_+5"] == 5
    assert base["sensitivity"]["temp_-5"] == -5


def test_clamp_bounds_under_extreme():
    r = derive_position(temp=999, bias="偏多", overall_promo=99, event_adj=50, explain=False)
    assert 5 <= r["pct"] <= 95
    r2 = derive_position(temp=-999, bias="偏空", overall_promo=0, event_adj=-50, explain=False)
    assert 5 <= r2["pct"] <= 95
