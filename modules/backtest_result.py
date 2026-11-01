"""modules/backtest_result.py —— Plan A split：回测结果数据类。

从 backtest.py 提取：
- DailyPickerResult（每日选股回测结果）
- BacktestResult（单次策略回测结果）

原始 AST 精确切分，零业务逻辑修改。
"""

import numpy as np
import pandas as pd


class DailyPickerResult:
    """每日选股回测结果封装。"""

    def __init__(self, picks_df, returns_df):
        self.picks_df = picks_df
        self.returns_df = returns_df

    def summary(self):
        if self.returns_df.empty:
            return {
                "total_days": 0,
                "avg_daily_return_pct": 0,
                "total_return_pct": 0,
                "win_day_pct": 0,
                "total_picks": 0,
                "win_pick_pct": 0,
            }
        total_return = self.returns_df["cumulative_return_pct"].iloc[-1]
        avg_daily = self.returns_df["avg_return_pct"].mean()
        win_days = (self.returns_df["avg_return_pct"] > 0).sum()
        win_day_pct = win_days / len(self.returns_df) * 100

        total_picks = len(self.picks_df)
        win_picks = (self.picks_df["hold_return_pct"] > 0).sum() if not self.picks_df.empty else 0
        win_pick_pct = win_picks / total_picks * 100 if total_picks > 0 else 0

        return {
            "total_days": len(self.returns_df),
            "avg_daily_return_pct": round(avg_daily, 2),
            "total_return_pct": round(total_return, 2),
            "win_day_pct": round(win_day_pct, 2),
            "total_picks": total_picks,
            "win_pick_pct": round(win_pick_pct, 2),
        }

    def latest_picks(self, n=10):
        """返回最近一个交易日的推荐股票。"""
        if self.picks_df.empty:
            return pd.DataFrame()
        latest_date = self.picks_df["date"].max()
        return self.picks_df[self.picks_df["date"] == latest_date].sort_values("score", ascending=False).head(n)

    def prev_picks(self, n=10):
        """返回前一个交易日的推荐股票（用于观察明日表现）。"""
        if self.picks_df.empty:
            return pd.DataFrame()
        dates = sorted(self.picks_df["date"].unique())
        if len(dates) < 2:
            return pd.DataFrame()
        prev_date = dates[-2]
        return self.picks_df[self.picks_df["date"] == prev_date].sort_values("score", ascending=False).head(n)


class BacktestResult:
    """回测结果封装。"""

    def __init__(self, ticker, strategy, result_df, initial_capital, trades=None):
        self.ticker = ticker
        self.strategy = strategy
        self.df = result_df
        self.trades = trades or []
        self.initial_capital = initial_capital

    @property
    def final_value(self):
        return self.df["total_asset"].iloc[-1] if not self.df.empty else self.initial_capital

    @property
    def total_return(self):
        return round(self.df["cumulative_return"].iloc[-1], 2) if not self.df.empty else 0

    @property
    def max_drawdown(self):
        return round(self.df["drawdown"].min(), 2) if not self.df.empty else 0

    @property
    def sharpe_ratio(self):
        """年化夏普比率（无风险利率取3%）。"""
        if self.df.empty:
            return 0
        daily_returns = self.df["daily_return"] / 100
        if daily_returns.std() == 0:
            return 0
        annual_return = daily_returns.mean() * 252
        annual_std = daily_returns.std() * np.sqrt(252)
        risk_free = 0.03 / 252
        return round((annual_return - risk_free) / annual_std, 2) if annual_std > 0 else 0

    @property
    def win_rate(self):
        """交易胜率：以每笔完整交易净盈亏为正为准。"""
        if not self.trades:
            return 0
        wins = sum(1 for t in self.trades if t["profit_pct"] > 0)
        return round(wins / len(self.trades) * 100, 2)

    @property
    def profit_factor(self):
        """盈亏比：总盈利 / |总亏损|。无亏损交易（全胜）或无交易时分母为 0，盈亏比无定义，返回 None（而非误导性的 0）。"""
        if not self.trades:
            return None
        gross_profit = sum(t["profit_pct"] for t in self.trades if t["profit_pct"] > 0)
        gross_loss = abs(sum(t["profit_pct"] for t in self.trades if t["profit_pct"] < 0))
        # 无亏损交易（全胜）时分母为 0，盈亏比无定义：返回 None 而非误导性的 0
        # （与 run_batch 的 is not None 过滤、页面的「—」展示口径一致，见锐评 R4）。
        return round(gross_profit / gross_loss, 2) if gross_loss > 0 else None

    @property
    def avg_trade_return(self):
        """单笔交易平均收益率。"""
        if not self.trades:
            return 0
        return round(sum(t["profit_pct"] for t in self.trades) / len(self.trades), 2)

    @property
    def trade_count(self):
        return len(self.trades)

    @property
    def exposure_pct(self):
        """持仓时间占比（%）：持有头寸的交易日数 / 总交易日数。"""
        if self.df.empty or "position" not in self.df.columns:
            return 0.0
        bars = len(self.df)
        if bars == 0:
            return 0.0
        held = int((self.df["position"] > 0).sum())
        return round(held / bars * 100, 2)

    @property
    def annualized_return_pct(self):
        """年化收益率（%）：以总交易日近似 252 交易日/年做几何年化。"""
        if self.df.empty:
            return 0.0
        total = self.total_return
        bars = len(self.df)
        if bars <= 1 or total <= -100:
            return 0.0
        growth = 1 + total / 100
        if growth <= 0:
            return 0.0
        years = bars / 252
        return round((growth ** (1 / years) - 1) * 100, 2)

    def summary(self):
        """返回回测摘要字典。"""
        return {
            "ticker": self.ticker,
            "strategy": self.strategy,
            "initial_capital": self.initial_capital,
            "final_value": self.final_value,
            "total_return_pct": self.total_return,
            "max_drawdown_pct": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate_pct": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_trade_return_pct": self.avg_trade_return,
            "trade_count": self.trade_count,
            "start_date": self.df["date"].iloc[0].strftime("%Y-%m-%d") if not self.df.empty else "",
            "end_date": self.df["date"].iloc[-1].strftime("%Y-%m-%d") if not self.df.empty else "",
        }

    def summary_text(self):
        """返回文本摘要。"""
        s = self.summary()
        return (
            f"=== 回测结果 [{s['ticker']}] [{s['strategy']}] ===\n"
            f"  回测区间:   {s['start_date']} ~ {s['end_date']}\n"
            f"  初始资金:   ¥{s['initial_capital']:,.0f}\n"
            f"  最终资产:   ¥{s['final_value']:,.2f}\n"
            f"  累计收益:   {s['total_return_pct']:+.2f}%\n"
            f"  最大回撤:   {s['max_drawdown_pct']:.2f}%\n"
            f"  夏普比率:   {s['sharpe_ratio']}\n"
            f"  胜率:       {s['win_rate_pct']:.2f}%\n"
            f"  盈亏比:     {s['profit_factor']}\n"
            f"  平均单笔:   {s['avg_trade_return_pct']:+.2f}%\n"
            f"  交易次数:   {s['trade_count']}"
        )

# 导出清单
__all__ = ["DailyPickerResult", "BacktestResult", "np", "pd"]
