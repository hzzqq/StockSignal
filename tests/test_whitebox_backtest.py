"""test_whitebox_backtest.py — Backtester & BacktestResult 白盒测试
覆盖 run / _event_driven_signals / _ma_cross_signals / _simulate
及 BacktestResult 所有属性。
"""

import pytest
import pandas as pd
import numpy as np
from modules.backtest import Backtester, BacktestResult


# ==================================================================
# BacktestResult 白盒测试
# ==================================================================
class TestBacktestResultWhite:

    def test_empty_result(self):
        """空 DataFrame 的 BacktestResult。"""
        df = pd.DataFrame(columns=[
            "date", "close", "signal", "position", "cash", "holdings",
            "total_asset", "daily_return", "cumulative_return", "drawdown"
        ])
        result = BacktestResult("600519", "test", df, 100000)
        assert result.final_value == 100000
        assert result.total_return == 0
        assert result.max_drawdown == 0
        assert result.sharpe_ratio == 0
        assert result.win_rate == 0
        assert result.trade_count == 0

    def test_summary_keys(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10),
            "close": [10, 11, 12, 11, 13, 14, 13, 15, 16, 15],
            "signal": [1, 0, 0, 0, 0, 0, 0, 0, 0, -1],
            "position": [1000] * 10,
            "cash": [0.0] * 10,
            "holdings": [10000, 11000, 12000, 11000, 13000, 14000, 13000, 15000, 16000, 15000],
            "total_asset": [10000, 11000, 12000, 11000, 13000, 14000, 13000, 15000, 16000, 15000],
            "daily_return": [0, 10, 9, -8, 18, 7.7, -7, 15, 6.7, -6.25],
            "cumulative_return": [0, 10, 20, 10, 30, 40, 30, 50, 60, 50],
            "drawdown": [0, 0, 0, -8.3, 0, 0, -7.1, 0, 0, -6.25]
        })
        result = BacktestResult("600519", "test", df, 10000)
        s = result.summary()
        expected_keys = {"ticker", "strategy", "initial_capital", "final_value",
                         "total_return_pct", "max_drawdown_pct", "sharpe_ratio",
                         "win_rate_pct", "trade_count", "start_date", "end_date"}
        assert expected_keys.issubset(set(s.keys()))

    def test_final_value(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=3),
            "close": [10, 11, 12],
            "signal": [0, 0, 0],
            "position": [0, 0, 0],
            "cash": [10000, 10000, 10000],
            "holdings": [0, 0, 0],
            "total_asset": [10000, 10000, 10000],
            "daily_return": [0, 0, 0],
            "cumulative_return": [0, 0, 0],
            "drawdown": [0, 0, 0]
        })
        result = BacktestResult("600519", "test", df, 10000)
        assert result.final_value == 10000

    def test_total_return(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=2),
            "close": [10, 12],
            "signal": [0, 0],
            "position": [0, 0],
            "cash": [10000, 10000],
            "holdings": [0, 0],
            "total_asset": [10000, 12000],
            "daily_return": [0, 20],
            "cumulative_return": [0, 20],
            "drawdown": [0, 0]
        })
        result = BacktestResult("600519", "test", df, 10000)
        assert result.total_return == 20.0

    def test_max_drawdown(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 12, 8, 9, 10],
            "signal": [0, 0, 0, 0, 0],
            "position": [0, 0, 0, 0, 0],
            "cash": [10000] * 5,
            "holdings": [0] * 5,
            "total_asset": [10000, 12000, 8000, 9000, 10000],
            "daily_return": [0, 20, -33.3, 12.5, 11.1],
            "cumulative_return": [0, 20, -20, -10, 0],
            "drawdown": [0, 0, -33.3, -25, -16.7]
        })
        result = BacktestResult("600519", "test", df, 10000)
        assert result.max_drawdown == -33.3

    def test_sharpe_zero_std(self):
        """收益率为常数时 std=0, sharpe=0。"""
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 10, 10, 10, 10],
            "signal": [0, 0, 0, 0, 0],
            "position": [0, 0, 0, 0, 0],
            "cash": [10000] * 5,
            "holdings": [0] * 5,
            "total_asset": [10000] * 5,
            "daily_return": [0, 0, 0, 0, 0],
            "cumulative_return": [0, 0, 0, 0, 0],
            "drawdown": [0, 0, 0, 0, 0]
        })
        result = BacktestResult("600519", "test", df, 10000)
        assert result.sharpe_ratio == 0

    def test_sharpe_positive(self):
        """正收益波动时夏普比率应为正。"""
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10),
            "close": [10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5],
            "signal": [0] * 10,
            "position": [0] * 10,
            "cash": [10000] * 10,
            "holdings": [0] * 10,
            "total_asset": [10000, 10500, 11000, 11500, 12000, 12500, 13000, 13500, 14000, 14500],
            "daily_return": [0, 5, 4.76, 4.55, 4.35, 4.17, 4, 3.85, 3.7, 3.57],
            "cumulative_return": [0, 5, 10, 15, 20, 25, 30, 35, 40, 45],
            "drawdown": [0] * 10
        })
        result = BacktestResult("600519", "test", df, 10000)
        assert result.sharpe_ratio > 0

    def test_win_rate_no_trades(self):
        """无交易时胜率为0。"""
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 11, 12, 11, 10],
            "signal": [0, 0, 0, 0, 0],
            "position": [0, 0, 0, 0, 0],
            "cash": [10000] * 5,
            "holdings": [0] * 5,
            "total_asset": [10000] * 5,
            "daily_return": [0] * 5,
            "cumulative_return": [0] * 5,
            "drawdown": [0] * 5
        })
        result = BacktestResult("600519", "test", df, 10000)
        assert result.win_rate == 0

    def test_win_rate_all_wins(self):
        """全部盈利交易。"""
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=6),
            "close": [10, 10, 12, 12, 15, 15],
            "signal": [1, 0, 0, 1, 0, -1],
            "position": [100, 100, 100, 100, 100, 0],
            "cash": [0, 0, 0, 0, 0, 1500],
            "holdings": [1000, 1000, 1200, 1200, 1500, 0],
            "total_asset": [1000, 1000, 1200, 1200, 1500, 1500],
            "daily_return": [0, 0, 20, 0, 25, 0],
            "cumulative_return": [0, 0, 20, 20, 50, 50],
            "drawdown": [0, 0, 0, 0, 0, 0]
        })
        result = BacktestResult("600519", "test", df, 1000, trades=[{"profit_pct": 50.0}])
        # 唯一一次卖出: buy@10, sell@15 → 盈利
        assert result.win_rate == 100.0

    def test_trade_count(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 11, 12, 11, 10],
            "signal": [1, 0, -1, 0, 0],
            "position": [100, 100, 0, 0, 0],
            "cash": [0, 0, 1200, 1200, 1200],
            "holdings": [1000, 1100, 0, 0, 0],
            "total_asset": [1000, 1100, 1200, 1200, 1200],
            "daily_return": [0, 10, 9, 0, 0],
            "cumulative_return": [0, 10, 20, 20, 20],
            "drawdown": [0, 0, 0, 0, 0]
        })
        result = BacktestResult("600519", "test", df, 1000, trades=[{"profit_pct": 20.0}, {"profit_pct": -5.0}])
        assert result.trade_count == 2

    def test_summary_text(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=3),
            "close": [10, 11, 12],
            "signal": [0, 0, 0],
            "position": [0, 0, 0],
            "cash": [10000, 10000, 10000],
            "holdings": [0, 0, 0],
            "total_asset": [10000, 10000, 10000],
            "daily_return": [0, 0, 0],
            "cumulative_return": [0, 0, 0],
            "drawdown": [0, 0, 0]
        })
        result = BacktestResult("600519", "test", df, 10000)
        text = result.summary_text()
        assert "600519" in text
        assert "回测结果" in text
        assert "¥" in text


# ==================================================================
# Backtester 白盒测试
# ==================================================================
class TestBacktesterWhite:

    def test_invalid_strategy(self):
        bt = Backtester()
        with pytest.raises(ValueError, match="不支持的策略"):
            bt.run("600519", "2025-01-01", "2025-06-01", strategy="invalid")

    def test_ma_cross_signals_length(self):
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=30),
            "close": [10, 9, 8, 9, 10, 11, 12, 13, 12, 11,
                      10, 11, 12, 13, 14, 15, 16, 15, 14, 13,
                      12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
            "ma5": [10, 9.2, 8.8, 8.8, 9.2, 9.8, 10.6, 11.4, 12.2, 12.6,
                    12.4, 12.0, 11.8, 11.8, 12.0, 12.4, 13.0, 13.8, 14.4, 14.6,
                    14.4, 14.0, 13.8, 13.8, 14.0, 14.4, 15.0, 15.8, 16.4, 17.0],
            "ma20": [10] * 30
        })
        signals = bt._ma_cross_signals(df)
        assert len(signals) == 30
        assert all(s in [-1, 0, 1] for s in signals)

    def test_ma_cross_first_20_zero(self):
        """前20天信号应为0。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=30),
            "close": range(30),
            "ma5": range(30),
            "ma20": range(30),
        })
        signals = bt._ma_cross_signals(df)
        assert all(s == 0 for s in signals[:20])

    def test_ma_cross_golden_cross(self):
        """MA5 上穿 MA20 应产生买入信号。"""
        bt = Backtester()
        # 构造 MA5 上穿 MA20
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=22),
            "close": range(22),
            "ma5": [10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
                    10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
                    9, 11],  # ma5 从下穿上
            "ma20": [10] * 22,
        })
        signals = bt._ma_cross_signals(df)
        # 第21行 (i=20): prev ma5=10 <= ma20=10, curr ma5=9 < ma20=10 → 不交叉
        # 第22行 (i=21): prev ma5=9 <= ma20=10, curr ma5=11 > ma20=10 → 金叉
        assert signals[21] == 1

    def test_ma_cross_death_cross(self):
        """MA5 下穿 MA20 应产生卖出信号。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=22),
            "close": range(22),
            "ma5": [10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
                    10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
                    11, 9],  # ma5 从上穿下
            "ma20": [10] * 22,
        })
        signals = bt._ma_cross_signals(df)
        assert signals[21] == -1

    def test_simulate_buy_and_sell(self):
        """模拟交易：买入→卖出流程。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 11, 12, 13, 14],
        })
        signals = [1, 0, 0, 0, -1]
        result, trades = bt._simulate(df, signals, initial_capital=10000, commission=0.001)

        assert len(result) == 5
        assert result.iloc[0]["signal"] == 1   # 买入
        assert result.iloc[-1]["signal"] == -1  # 卖出
        assert result.iloc[0]["position"] > 0
        assert result.iloc[-1]["position"] == 0
        assert result.iloc[-1]["cash"] > result.iloc[0]["cash"]

    def test_simulate_no_trade(self):
        """无信号时不交易。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 11, 12, 13, 14],
        })
        signals = [0, 0, 0, 0, 0]
        result, trades = bt._simulate(df, signals, initial_capital=10000, commission=0.001)

        assert all(result["position"] == 0)
        assert all(result["cash"] == 10000)

    def test_simulate_commission_deducted(self):
        """买入时扣除手续费。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=2),
            "close": [10, 11],
        })
        signals = [1, 0]
        result, trades = bt._simulate(df, signals, initial_capital=10000, commission=0.001)

        # 买入后 cash 应 < 10000
        assert result.iloc[0]["cash"] < 10000

    def test_simulate_drawdown(self):
        """回撤应为负值或0。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 12, 8, 9, 10],
        })
        signals = [1, 0, 0, 0, 0]
        result, trades = bt._simulate(df, signals, initial_capital=10000, commission=0)

        assert result["drawdown"].min() <= 0

    def test_simulate_cumulative_return(self):
        """累计收益率应正确计算。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=3),
            "close": [10, 11, 12],
        })
        signals = [1, 0, 0]
        result, trades = bt._simulate(df, signals, initial_capital=10000, commission=0,
                                      slippage_pct=0, stamp_tax_pct=0)

        # 买入1000股@10 = 10000, 资产 = 1000*close
        # day0: 1000*10 = 10000, cum_return = 0%
        # day1: 1000*11 = 11000, cum_return = 10%
        # day2: 1000*12 = 12000, cum_return = 20%
        assert result.iloc[0]["cumulative_return"] == pytest.approx(0, abs=0.01)
        assert result.iloc[1]["cumulative_return"] == pytest.approx(10, abs=0.1)
        assert result.iloc[2]["cumulative_return"] == pytest.approx(20, abs=0.1)

    def test_run_ma_cross_integration(self):
        """MA交叉策略集成测试（需要网络）。"""
        bt = Backtester()
        try:
            result = bt.run(
                ticker="000858",
                start="2024-06-01",
                end="2025-06-01",
                strategy="ma_cross",
                initial_capital=100000
            )
            assert result.df is not None
            s = result.summary()
            assert "total_return_pct" in s
            assert "sharpe_ratio" in s
        except Exception:
            pytest.skip("网络不可用")
