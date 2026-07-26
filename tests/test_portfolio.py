"""
modules/portfolio.py 纯逻辑单元测试。

只构造内存中的 dict / list，不触碰网络 / 数据库 / 文件系统，
验证空输入、缺失键、None、除零、NaN 等退化场景下不会崩溃或产生 NaN。
"""
import math

from modules.portfolio import (
    market_value_of,
    total_market_value,
    position_weights,
    position_pnl,
)


def test_empty_positions_total_value_zero():
    """空持仓列表 -> 总市值 0，不抛异常。"""
    assert total_market_value([]) == 0.0
    assert total_market_value(None) == 0.0


def test_missing_price_or_shares_treated_as_zero():
    """缺失 price / shares 键 -> 视为 0（不产生 NaN）。"""
    pos = {"ticker": "000001", "name": "测试"}  # 没有价格/股数字段
    mv = market_value_of(pos)
    assert mv == 0.0
    assert not math.isnan(mv)

    # None 值也按 0 处理
    pos_none = {"ticker": "000001", "current_price": None, "remaining_shares": None}
    assert market_value_of(pos_none) == 0.0


def test_zero_total_weight_is_zero_not_nan():
    """总市值为 0 时权重应为 0.0，而不是 NaN / inf。"""
    positions = [
        {"ticker": "A", "current_price": 0, "remaining_shares": 100},
        {"ticker": "B", "current_price": None, "remaining_shares": 50},
    ]
    weights = position_weights(positions)
    assert weights == {"A": 0.0, "B": 0.0}
    for w in weights.values():
        assert not math.isnan(w)
        assert not math.isinf(w)


def test_position_weights_normal_case():
    """正常情形：权重按市值占比正确计算。"""
    positions = [
        {"ticker": "A", "current_price": 10, "remaining_shares": 100},  # 1000
        {"ticker": "B", "current_price": 10, "remaining_shares": 300},  # 3000
    ]
    weights = position_weights(positions)
    assert weights["A"] == 25.0
    assert weights["B"] == 75.0


def test_total_market_value_normal_case():
    """正常情形：总市值按 current_price*remaining_shares 求和。"""
    positions = [
        {"ticker": "A", "current_price": 10, "remaining_shares": 100},  # 1000
        {"ticker": "B", "price": 5, "shares": 200},                     # 1000 (兼容旧字段)
    ]
    assert total_market_value(positions) == 2000.0


def test_position_pnl_normal_and_degenerate():
    """盈亏：正常计算；None / NaN 输入安全回退为 0。"""
    assert position_pnl(10, 100, 800) == 200.0
    # 退化输入不产生 NaN
    assert position_pnl(None, None, None) == 0.0
    assert not math.isnan(position_pnl(float("nan"), 10, 100))
