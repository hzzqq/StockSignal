"""
tests/test_trading_costs.py
===========================
T-274 R10：A 股交易成本模型单源守卫——计算正确性 / 边界 / 诚实语义 /
49.1% 方向锚不受影响的红线声明。
"""
import math

import pytest

from modules import trading_costs as tc


def test_buy_cost_components():
    """买入成本 = max(佣金费率, 最低5元) + 滑点 + 过户费（10 万本金）。"""
    r = tc.buy_cost(100_000)
    assert r["commission"] == pytest.approx(25.0)          # 10万×万2.5 > 5 元
    assert r["slippage"] == pytest.approx(100.0)           # 10万×0.1%
    assert r["transfer_fee"] == pytest.approx(1.0)         # 10万×0.001%
    assert r["total"] == pytest.approx(126.0)
    assert r["total_rate"] == pytest.approx(0.00126)


def test_commission_minimum_applies():
    """小额交易触发最低佣金 5 元（而非费率）。"""
    r = tc.buy_cost(1_000)                                  # 1000×万2.5=0.25 < 5
    assert r["commission"] == 5.0


def test_sell_cost_includes_stamp_tax():
    """卖出多一项印花税 0.05%（仅卖出）。"""
    r = tc.sell_cost(100_000)
    assert r["stamp_tax"] == pytest.approx(50.0)
    assert r["total"] == pytest.approx(25.0 + 50.0 + 100.0 + 1.0)


def test_round_trip_rate_typical_value():
    """一买一卖全成本率 ≈ 0.27%（10 万本金口径）——收益超过它才有正期望空间。"""
    rate = tc.round_trip_rate(100_000)
    assert rate == pytest.approx((126.0 + 176.0) / 100_000, abs=1e-6)
    assert 0.002 < rate < 0.004


def test_invalid_amount_raises_not_zero():
    """非法金额抛 ValueError（不编造、不静默归零——诚实语义）。"""
    for bad in (0, -100, None, "abc"):
        with pytest.raises(ValueError):
            tc.buy_cost(bad)


def test_direction_anchor_untouched_by_costs():
    """红线：成本模型与方向命中锚（49.1%）语义隔离——模块不得引用/修改回测锚。

    源码契约：trading_costs.py 不 import 回测/决策模块（方向命中与成本分属不同
    口径，见 docs/alignment-matrix.md #5/#7）。
    """
    src = (__import__("pathlib").Path(__file__).resolve().parents[1]
           / "modules" / "trading_costs.py").read_text(encoding="utf-8")
    for banned in ("backtest_decision_closure", "derive_position",
                   "shepherd_history", "dir_accuracy"):
        assert banned not in src, f"成本模块不得引用方向锚相关符号: {banned}"
    assert "49.1% 方向命中锚" in src and "不受成本影响" in src, \
        "红线声明缺失（成本与方向锚的口径隔离必须写死在模块头）"


def test_params_documented_as_typical_not_measured():
    """参数必须标注「业界典型值非实测」（不冒充本项目账单——诚实语义）。"""
    src = (__import__("pathlib").Path(__file__).resolve().parents[1]
           / "modules" / "trading_costs.py").read_text(encoding="utf-8")
    assert "业界典型值" in src and "以券商" in src
    assert "2023-08-28" in src, "印花税减半时点必须注明（口径可追溯）"
