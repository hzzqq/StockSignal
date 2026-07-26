"""
tests/test_backtest_result.py
==============================
回测结果封装（modules.backtest.BacktestResult）指标计算测试。

锁定边界行为：空 df / 空交易 / 零波动 / 盈亏比 / 年化各类退化输入均不崩溃且返回合理默认。
"""
import numpy as np
import pandas as pd
import pytest

from modules.backtest import BacktestResult


def _df(daily_returns, *, total_asset=None, position=None, dates=None):
    n = len(daily_returns)
    if total_asset is None:
        total_asset = [10000.0 * (1 + r / 100) ** (i + 1) for i, r in enumerate(daily_returns)]
    if position is None:
        position = [1] * n
    if dates is None:
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
    cum = np.cumprod([1 + r / 100 for r in daily_returns]) - 1
    df = pd.DataFrame({
        "date": dates,
        "daily_return": daily_returns,
        "total_asset": total_asset,
        "cumulative_return": (cum * 100).tolist(),
        "drawdown": [0.0] * n,
        "position": position,
    })
    return df


def test_empty_df_returns_sane_defaults():
    r = BacktestResult("600519", "ma_cross", pd.DataFrame(), 10000.0)
    assert r.final_value == 10000.0
    assert r.total_return == 0
    assert r.max_drawdown == 0
    assert r.sharpe_ratio == 0
    assert r.exposure_pct == 0.0
    assert r.annualized_return_pct == 0.0


def test_empty_trades_returns_zero_rates():
    df = _df([1.0, 2.0, -1.0, 0.5])
    r = BacktestResult("600519", "ma_cross", df, 10000.0, trades=[])
    assert r.win_rate == 0
    assert r.profit_factor == 0
    assert r.avg_trade_return == 0
    assert r.trade_count == 0


def test_trade_metrics_computed():
    df = _df([1.0, 2.0, -1.0, 0.5])
    trades = [
        {"profit_pct": 10.0},
        {"profit_pct": -5.0},
        {"profit_pct": 20.0},
        {"profit_pct": -10.0},
    ]
    r = BacktestResult("600519", "ma_cross", df, 10000.0, trades=trades)
    assert r.trade_count == 4
    assert r.win_rate == 50.0           # 2 盈 / 4
    assert r.profit_factor == pytest.approx(2.0)   # 30 / 15
    assert r.avg_trade_return == pytest.approx(3.75)  # 15/4


def test_sharpe_zero_volatility_returns_zero():
    # 日收益恒为 0 → 标准差 0 → 夏普应为 0（不除零）
    df = _df([0.0, 0.0, 0.0, 0.0])
    r = BacktestResult("600519", "flat", df, 10000.0)
    assert r.sharpe_ratio == 0


def test_sharpe_positive_for_uptrend():
    # 有波动的上涨（非恒定收益）→ 标准差>0 → 正夏普
    df = _df([1.0, 0.5, 2.0, 0.3, 1.5])
    r = BacktestResult("600519", "up", df, 10000.0)
    assert r.sharpe_ratio > 0


def test_exposure_with_no_position():
    df = _df([1.0, 2.0, -1.0], position=[0, 0, 0])
    r = BacktestResult("600519", "flat", df, 10000.0)
    assert r.exposure_pct == 0.0


def test_exposure_full_position():
    df = _df([1.0, 2.0, -1.0], position=[1, 1, 1])
    r = BacktestResult("600519", "flat", df, 10000.0)
    assert r.exposure_pct == pytest.approx(100.0)


def test_annualized_degenerate_inputs():
    # total <= -100（且 bars>1） → 0
    df_neg = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=2),
        "daily_return": [-90.0, -100.0],
        "total_asset": [1000.0, 0.0],
        "cumulative_return": [-90.0, -100.0],
        "drawdown": [0.0, 0.0],
        "position": [1, 1],
    })
    r_neg = BacktestResult("x", "s", df_neg, 10000.0)
    assert r_neg.total_return == -100.0
    assert r_neg.annualized_return_pct == 0.0
    # bars <= 1 → 0
    df_one = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=1),
        "daily_return": [1.0],
        "total_asset": [10100.0],
        "cumulative_return": [1.0],
        "drawdown": [0.0],
        "position": [1],
    })
    assert BacktestResult("x", "s", df_one, 10000.0).annualized_return_pct == 0.0


def test_summary_keys_present():
    df = _df([1.0, 2.0, -1.0, 0.5])
    r = BacktestResult("600519", "ma_cross", df, 10000.0,
                       trades=[{"profit_pct": 5.0}, {"profit_pct": -2.0}])
    s = r.summary()
    for k in ("ticker", "strategy", "final_value", "total_return_pct",
              "max_drawdown_pct", "sharpe_ratio", "win_rate_pct",
              "profit_factor", "trade_count", "start_date", "end_date"):
        assert k in s
    assert s["start_date"] == "2024-01-01"
