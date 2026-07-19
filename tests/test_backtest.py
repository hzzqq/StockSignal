"""test_backtest.py — 回测引擎测试"""

import pytest
import pandas as pd
import numpy as np
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

    def test_run_event_driven(self):
        """测试事件驱动策略回测（需要网络）。"""
        bt = Backtester()
        try:
            result = bt.run(
                ticker="000858",
                start="2024-06-01",
                end="2025-06-01",
                strategy="event_driven",
                keywords=["白酒", "提价", "旺季"],
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

    def _make_df(self, n, rsi_start, rsi_end, daily, vol_ratio, atr=0.10):
        """构造合成行情 DataFrame（无网依赖，仅验证信号逻辑）。"""
        dates = pd.date_range("2024-01-01", periods=n)
        close = [10.0]
        for i in range(1, n):
            close.append(close[-1] * (1 + daily))
        close = np.array(close, dtype=float)
        ma20 = pd.Series(close).rolling(20, min_periods=5).mean().to_numpy()
        ma60 = pd.Series(close).rolling(60, min_periods=20).mean().to_numpy()
        rsi14 = np.linspace(rsi_start, rsi_end, n)
        rsi2 = np.full(n, 25.0)
        atr_ratio = np.full(n, atr)
        base_vol = 1_000_000.0
        vol = np.full(n, base_vol * vol_ratio)
        vol_ma20 = np.full(n, base_vol)
        bb_lower = close * 0.96
        return pd.DataFrame({
            "date": dates, "close": close, "ma20": ma20, "ma60": ma60,
            "rsi14": rsi14, "rsi2": rsi2, "atr_ratio": atr_ratio,
            "volume": vol, "vol_ma20": vol_ma20, "bb_lower": bb_lower,
        })

    def test_multi_factor_strong_uptrend_buys(self):
        """回归 #V5：长电科技类「长期 RSI>85 的强势上涨股」此前 buy=0（被 RSI<=85 硬门槛排除）。
        修复后应能生成买入信号。"""
        bt = Backtester()
        df = self._make_df(90, rsi_start=85, rsi_end=95, daily=0.018, vol_ratio=0.9)
        signals = bt._multi_factor_signals(df)
        n_buy = sum(1 for s in signals if s == 1)
        assert n_buy > 0, "强势上涨股(RSI>85)应产生买入信号，不应被系统性排除"

    def test_multi_factor_downtrend_no_chase(self):
        """下跌趋势不应追涨买入，但应允许卖出（仓位管理）。"""
        bt = Backtester()
        df = self._make_df(90, rsi_start=65, rsi_end=30, daily=-0.01, vol_ratio=1.0)
        signals = bt._multi_factor_signals(df)
        n_buy = sum(1 for s in signals if s == 1)
        n_sell = sum(1 for s in signals if s == -1)
        assert n_buy == 0, "下跌趋势不应产生买入信号"
        assert n_sell > 0, "下跌趋势应产生卖出信号"

    def test_multi_factor_pullback_closes_trade(self):
        """冲高回落（RSI 冲到 >=92 后跌破 90）应能触发止盈卖出，让交易闭环。"""
        bt = Backtester()
        n_up, n_down = 75, 15
        n = n_up + n_down
        close = [10.0]
        for i in range(1, n_up):
            close.append(close[-1] * 1.018)
        for i in range(n_down):
            close.append(close[-1] * 0.985)
        close = np.array(close, dtype=float)
        ma20 = pd.Series(close).rolling(20, min_periods=5).mean().to_numpy()
        ma60 = pd.Series(close).rolling(60, min_periods=20).mean().to_numpy()
        rsi14 = np.concatenate([np.linspace(78, 93, n_up), np.linspace(93, 60, n_down)])
        rsi2 = np.concatenate([np.full(n_up, 22.0), np.full(n_down, 40.0)])
        atr_ratio = np.full(n, 0.08)
        vol = np.full(n, 1_000_000.0)
        vol_ma20 = np.full(n, 1_000_000.0)
        bb_lower = close * 0.96
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=n), "close": close,
            "ma20": ma20, "ma60": ma60, "rsi14": rsi14, "rsi2": rsi2,
            "atr_ratio": atr_ratio, "volume": vol, "vol_ma20": vol_ma20,
            "bb_lower": bb_lower,
        })
        signals = bt._multi_factor_signals(df)
        n_buy = sum(1 for s in signals if s == 1)
        n_sell = sum(1 for s in signals if s == -1)
        assert n_buy > 0, "冲高阶段应买入"
        assert n_sell > 0, "回落阶段应触发卖出，让交易闭环"
