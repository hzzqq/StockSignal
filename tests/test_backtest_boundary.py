"""R14：回测引擎边界测试（无网依赖，纯策略/模拟函数）。

覆盖长电科技回测之外最易崩的边界：
1. 空 DataFrame（0 行）——信号函数 / 模拟器不得抛异常，返回空结构；
2. 单根 K 线（1 行）——信号函数对 i<20 早退返回 [0]，模拟器 1 条记录 0 交易；
3. 无信号边界（全 0 信号 / 横盘）——不产生交易，终值 == 初始资金；
4. 买入→持有→卖出闭环——恰好 1 笔交易且正常平仓（验证 R5「交易可重复/闭环」）。

不调用 Backtester.run（需网络），只测可离线复现的纯逻辑。
"""

import pandas as pd

from modules.backtest import Backtester


def _ma_df(n):
    """构造 _ma_cross_signals 所需列（ma5/ma20/ma60/rsi14）。"""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "close": [10.0] * n,
        "ma5": [10.0] * n,
        "ma20": [10.0] * n,
        "ma60": [10.0] * n,
        "rsi14": [50.0] * n,
    })


def _mf_df(n):
    """构造 _multi_factor_signals 所需全部指标列。"""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "close": [10.0] * n,
        "ma20": [10.0] * n,
        "ma60": [10.0] * n,
        "rsi14": [50.0] * n,
        "rsi2": [25.0] * n,
        "atr_ratio": [0.05] * n,
        "volume": [1_000_000.0] * n,
        "vol_ma20": [1_000_000.0] * n,
        "bb_lower": [9.5] * n,
    })


def _sim_df(n, prices):
    """构造 _simulate 所需最小列（date/close）。"""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "close": prices,
    })


class TestBacktestBoundary:

    # —— 空 DataFrame ——
    def test_ma_cross_empty(self):
        bt = Backtester()
        assert bt._ma_cross_signals(_ma_df(0)) == []

    def test_multi_factor_empty(self):
        bt = Backtester()
        assert bt._multi_factor_signals(_mf_df(0)) == []

    def test_simulate_empty(self):
        bt = Backtester()
        res, trades = bt._simulate(_sim_df(0, []), [])
        assert len(res) == 0 and trades == []

    def test_add_indicators_empty(self):
        bt = Backtester()
        df = pd.DataFrame({"date": pd.to_datetime([]), "open": [], "high": [],
                           "low": [], "close": [], "volume": [],
                           "ma20": [], "ma60": []})
        out = bt._add_indicators(df)
        # 仍应带全部指标列，且不抛异常
        for col in ("rsi14", "atr14", "macd_dif", "bb_lower", "vol_ma20"):
            assert col in out.columns

    # —— 单根 K 线 ——
    def test_ma_cross_single_row(self):
        bt = Backtester()
        assert bt._ma_cross_signals(_ma_df(1)) == [0]   # i<20 早退

    def test_multi_factor_single_row(self):
        bt = Backtester()
        assert bt._multi_factor_signals(_mf_df(1)) == [0]

    def test_simulate_single_row_no_signal(self):
        bt = Backtester()
        res, trades = bt._simulate(_sim_df(1, [10.0]), [0])
        assert len(res) == 1
        assert trades == []
        assert res.iloc[0]["total_asset"] == 100000.0

    def test_add_indicators_single_row(self):
        bt = Backtester()
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01"]),
            "open": [10.0], "high": [10.5], "low": [9.5],
            "close": [10.0], "volume": [1_000_000.0],
            "ma20": [10.0], "ma60": [10.0],
        })
        out = bt._add_indicators(df)
        assert len(out) == 1
        # 单根 K 线 RSI 为 NaN（不足窗口），不应抛异常
        assert out["rsi14"].isna().all()

    # —— 无信号边界（横盘 / 全 0 信号）——
    def test_simulate_all_zero_no_trades(self):
        bt = Backtester()
        res, trades = bt._simulate(_sim_df(30, [10.0] * 30), [0] * 30)
        assert trades == []
        assert res.iloc[-1]["total_asset"] == 100000.0

    def test_simulate_flat_prices_no_signal(self):
        bt = Backtester()
        prices = [10.0] * 30
        res, trades = bt._simulate(_sim_df(30, prices), [0] * 30)
        # 横盘 + 无信号 → 资产始终等于初始资金
        assert (res["total_asset"] == 100000.0).all()
        assert trades == []

    # —— 买入→持有→卖出闭环 ——
    def test_simulate_buy_then_sell_closes(self):
        bt = Backtester()
        prices = [10.0] * 20 + [12.0] * 5 + [9.0] * 5
        signals = [0] * 20 + [1] + [0] * 4 + [-1] + [0] * 4
        res, trades = bt._simulate(_sim_df(len(prices), prices), signals)
        assert len(trades) == 1, "应恰好 1 笔交易并正常平仓"
        assert trades[0]["exit_reason"] == "策略卖出"
        assert trades[0]["entry_price"] > 0

    def test_simulate_no_buy_signal_no_position(self):
        bt = Backtester()
        # 只有卖出信号、从未买入 → 0 交易
        prices = [10.0] * 10
        signals = [-1] * 10
        res, trades = bt._simulate(_sim_df(10, prices), signals)
        assert trades == []
        assert res.iloc[-1]["total_asset"] == 100000.0
