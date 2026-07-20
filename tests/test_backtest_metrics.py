"""R21：BacktestResult 绩效指标属性无网单测（绕过含网络预热的 __init__）。

BacktestResult.__init__ 仅做属性赋值（ticker/strategy/df/trades/initial_capital），
本身不触发网络；但其所在模块 import 链会加载 fetcher/cleaner/signal。
为了避免任何 __init__ 副作用并聚焦纯数值属性，这里用 object.__new__
构造裸实例，再手动注入 df / trades / initial_capital，专测六个绩效属性：

- total_return      = df["cumulative_return"].iloc[-1]（空 df → 0）
- max_drawdown      = df["drawdown"].min()（空 df → 0）
- sharpe_ratio      = 年化夏普（rf=3%，std=0 → 0，空 df → 0）
- win_rate          = 盈利交易占比 * 100（无 trades → 0）
- profit_factor     = 总盈利 / |总亏损|（无亏损 → 0，无 trades → 0）
- avg_trade_return  = 单笔平均 profit_pct（无 trades → 0）

附带覆盖 final_value / trade_count 两个辅助属性，确保回测结果封装的数值契约稳定。
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd

from modules.backtest import BacktestResult


def _make(cumulative_return=None, drawdown=None, daily_return=None,
          total_asset=None, trades=None, initial_capital=100000):
    """构造裸 BacktestResult 并注入合成数据，规避 __init__。"""
    res = object.__new__(BacktestResult)
    data = {}
    if cumulative_return is not None:
        data["cumulative_return"] = cumulative_return
    if drawdown is not None:
        data["drawdown"] = drawdown
    if daily_return is not None:
        data["daily_return"] = daily_return
    if total_asset is not None:
        data["total_asset"] = total_asset
    res.df = pd.DataFrame(data) if data else pd.DataFrame()
    res.trades = trades or []
    res.initial_capital = initial_capital
    return res


# ---------- total_return ----------

def test_total_return_normal():
    res = _make(cumulative_return=[1.0, 5.0, 12.0, 25.0])
    assert res.total_return == 25.0


def test_total_return_rounds_to_two_decimals():
    res = _make(cumulative_return=[12.6789])
    assert res.total_return == 12.68


def test_total_return_empty_df_is_zero():
    res = _make()
    assert res.total_return == 0


# ---------- max_drawdown ----------

def test_max_drawdown_picks_most_negative():
    res = _make(drawdown=[-2.5, -10.3, -3.1])
    assert res.max_drawdown == -10.3


def test_max_drawdown_empty_df_is_zero():
    res = _make()
    assert res.max_drawdown == 0


# ---------- final_value / trade_count 辅助属性 ----------

def test_final_value_last_total_asset():
    res = _make(total_asset=[100000, 102000, 105500])
    assert res.final_value == 105500


def test_final_value_empty_falls_back_to_initial_capital():
    res = _make(initial_capital=123456)
    assert res.final_value == 123456


def test_trade_count_reflects_trades():
    res = _make(trades=[{"profit_pct": 1.0}, {"profit_pct": 2.0}])
    assert res.trade_count == 2


# ---------- sharpe_ratio ----------

def test_sharpe_zero_volatility_is_zero():
    # 日收益全相同 → 标准差为 0 → 直接返回 0
    res = _make(daily_return=[1.0, 1.0, 1.0, 1.0])
    assert res.sharpe_ratio == 0


def test_sharpe_empty_df_is_zero():
    res = _make()
    assert res.sharpe_ratio == 0


def test_sharpe_normal_matches_formula():
    # 注意：属性内部用 pandas Series.std()（默认 ddof=1，样本标准差），
    # 故复算也用 pd.Series 以锁定同一条公式路径（列名 / rf=3% / 年化因子 252 / ddof / round 顺序）。
    daily = [5.0, 5.0, 0.0]
    res = _make(daily_return=daily)
    s = pd.Series(np.array(daily) / 100)
    annual_return = s.mean() * 252
    annual_std = s.std() * np.sqrt(252)
    risk_free = 0.03 / 252
    expected = round((annual_return - risk_free) / annual_std, 2)
    assert res.sharpe_ratio == expected


# ---------- win_rate ----------

def test_win_rate_counts_profitable_trades():
    trades = [{"profit_pct": 5.0}, {"profit_pct": -2.0}, {"profit_pct": 3.0}]
    # 2 / 3 盈利 → 66.67
    res = _make(trades=trades)
    assert res.win_rate == 66.67


def test_win_rate_empty_trades_is_zero():
    res = _make()
    assert res.win_rate == 0


# ---------- profit_factor ----------

def test_profit_factor_gross_profit_over_loss():
    trades = [{"profit_pct": 5.0}, {"profit_pct": -2.0}, {"profit_pct": 3.0}]
    # 总盈利 8 / |总亏损| 2 = 4.0
    res = _make(trades=trades)
    assert res.profit_factor == 4.0


def test_profit_factor_all_profit_returns_zero():
    trades = [{"profit_pct": 5.0}, {"profit_pct": 3.0}]
    res = _make(trades=trades)
    assert res.profit_factor == 0


def test_profit_factor_empty_trades_is_zero():
    res = _make()
    assert res.profit_factor == 0


# ---------- avg_trade_return ----------

def test_avg_trade_return_mean_profit():
    trades = [{"profit_pct": 5.0}, {"profit_pct": -2.0}, {"profit_pct": 3.0}]
    # (5 - 2 + 3) / 3 = 2.0
    res = _make(trades=trades)
    assert res.avg_trade_return == 2.0


def test_avg_trade_return_empty_trades_is_zero():
    res = _make()
    assert res.avg_trade_return == 0
