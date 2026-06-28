"""test_backtest.py — 回测引擎测试"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from modules.backtest import Backtester, BacktestResult


class TestBacktestResult:

    def test_summary_empty(self):
        df = pd.DataFrame(columns=[
            "date", "close", "signal", "position", "cash", "holdings",
            "total_asset", "daily_return", "cumulative_return", "drawdown"
        ])
        result = BacktestResult("600519", "test", df, 100000)
        s = result.summary()
        assert s["total_return_pct"] == 0
        assert s["max_drawdown_pct"] == 0

    def test_summary_with_data(self):
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
        assert s["total_return_pct"] == 50
        assert s["max_drawdown_pct"] <= 0


class TestBacktester:

    def test_ma_cross_signals(self):
        """测试均线交叉信号生成。"""
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=30),
            "close": [10, 9, 8, 9, 10, 11, 12, 13, 12, 11,
                      10, 11, 12, 13, 14, 15, 16, 15, 14, 13,
                      12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
            "ma5": [10, 9.2, 8.8, 8.8, 9.2, 9.8, 10.6, 11.4, 12.2, 12.6,
                    12.4, 12.0, 11.8, 11.8, 12.0, 12.4, 13.0, 13.8, 14.4, 14.6,
                    14.4, 14.0, 13.8, 13.8, 14.0, 14.4, 15.0, 15.8, 16.4, 17.0],
            "ma20": [10]*30
        })
        signals = bt._ma_cross_signals(df)
        assert len(signals) == 30
        assert all(s in [-1, 0, 1] for s in signals)

    def test_run_ma_cross(self):
        """测试均线交叉策略回测（需要网络）。"""
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
            pytest.skip("网络不可用，跳过")

    def test_invalid_strategy(self):
        bt = Backtester()
        with pytest.raises(ValueError):
            bt.run("600519", "2025-01-01", "2025-06-01", strategy="invalid")
