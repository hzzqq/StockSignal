"""
回归测试：回测 _simulate 单笔净收益率成本重复扣除缺陷（cycle 46）。

缺陷：旧实现
    gross_profit = (sell_price - entry_price) / entry_price * 100
    total_cost_rate = 2 * commission + stamp_tax_pct + 2 * slippage_pct
    net_profit = gross_profit - total_cost_rate * 100
其中 entry_price 已经含买入滑点+买入佣金、sell_price 已经含卖出滑点，
gross_profit 已把买入佣金、双边滑点都算进去了，却又整体再减一次
2*commission+2*slippage —— 买入佣金与双边滑点被扣两次，
每笔 profit_pct 系统性低估约 0.28 个百分点，并污染 profit_factor/win_rate/avg_trade_return。

修复：净收益率直接取 实际现金流入(revenue)/实际现金流出(position*entry_price) - 1，
不重复扣费。
"""

import os
import pandas as pd
import pytest

from modules.backtest import Backtester

COMM = 0.001
SLIP = 0.001
STAMP = 0.001


def _true_net(p_buy, p_sell, comm=COMM, slip=SLIP, stamp=STAMP):
    """独立按真实现金流入/流出计算的单笔净收益率（%）。

    买入每股实付 = p_buy*(1+slip)*(1+comm)
    卖出每股实收 = p_sell*(1-slip)*(1-comm-stamp)
    net% = 实收/实付 - 1
    """
    paid = p_buy * (1 + slip) * (1 + comm)
    received = p_sell * (1 - slip) * (1 - comm - stamp)
    return (received / paid - 1) * 100


def _run(prices, signals, **kw):
    bt = Backtester()
    df = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=len(prices)),
        "close": prices,
    })
    defaults = dict(initial_capital=100000, commission=COMM,
                    stop_loss_pct=0, take_profit_pct=0, trailing_stop_pct=0,
                    max_holding=15, min_holding=2, slippage_pct=SLIP, stamp_tax_pct=STAMP)
    defaults.update(kw)
    return bt._simulate(df, signals, **defaults)


class TestNetProfitNoDoubleCount:
    def test_profit_pct_equals_true_cashflow_net(self):
        """最关键的断言：profit_pct 必须等于独立现金流水算出的真实净收益率。"""
        # 买入@100, 第3根(索引2)卖出@110, 满足 min_holding=2
        prices = [100, 100, 110]
        signals = [1, 0, -1]
        _, trades = _run(prices, signals)
        assert len(trades) == 1, "应恰好成交一笔"
        expected = _true_net(100, 110)
        assert trades[0]["profit_pct"] == pytest.approx(expected, abs=0.02)
        # 旧实现会偏离约 0.28pp，远超 0.02 容差 → 抓得到

    def test_profit_pct_zero_cost_is_raw_price_move(self):
        """零成本时净收益率应等于裸涨跌幅（不重复扣费、也不漏扣）。"""
        prices = [100, 100, 110]
        signals = [1, 0, -1]
        _, trades = _run(prices, signals, commission=0, slippage_pct=0, stamp_tax_pct=0)
        assert trades[0]["profit_pct"] == pytest.approx(10.0, abs=0.01)

    def test_higher_commission_lowers_profit(self):
        """单调性：手续费越高，净收益率越低（双成本场景都应成立）。"""
        prices = [100, 100, 110]
        signals = [1, 0, -1]
        _, trades_low = _run(prices, signals, commission=0.0005)
        _, trades_high = _run(prices, signals, commission=0.003)
        assert trades_high[0]["profit_pct"] < trades_low[0]["profit_pct"]

    def test_loss_case_not_overstated(self):
        """下跌场景：净亏损不应被重复扣费放大（真实亏损绝对值应小于旧实现的亏损）。"""
        prices = [100, 100, 90]
        signals = [1, 0, -1]
        _, trades = _run(prices, signals)
        expected = _true_net(100, 90)
        assert trades[0]["profit_pct"] == pytest.approx(expected, abs=0.02)
        # 旧实现亏损更深（更负），与新值明显不同
        assert trades[0]["profit_pct"] > _true_net(100, 90) - 0.5


class TestSourceNoDoubleCount:
    def test_source_removed_double_count_lines(self):
        """源码级防回退：旧实现必须被清除。"""
        path = os.path.join(os.path.dirname(__file__), "..", "modules", "backtest.py")
        src = open(path, encoding="utf-8").read()
        # 旧公式特征：把双边手续+双边滑点再减一次
        assert "total_cost_rate = 2 * commission" not in src
        # 新公式：直接使用 revenue / buy_cost
        assert "revenue /" in src
        assert "buy_cost" in src
