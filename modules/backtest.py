"""
策略回测引擎
支持事件驱动策略回测，输出累计收益曲线、最大回撤、夏普比率等指标。
"""

import numpy as np
import pandas as pd

from .fetcher import StockFetcher
from .cleaner import DataCleaner
from .signal import SignalEngine


class Backtester:
    """事件驱动策略回测器。"""

    def __init__(self, config_path="config.yaml"):
        self.fetcher = StockFetcher(config_path)
        self.signal_engine = SignalEngine(config_path)
        self.config = self.signal_engine.config
        self.entry_threshold = self.config.get("signal", {}).get("entry_threshold", 70)
        self.exit_threshold = self.config.get("signal", {}).get("exit_threshold", 40)

    def run(self, ticker, start, end, strategy="event_driven",
            keywords=None, initial_capital=100000, commission=0.001):
        """
        运行回测。
        :param ticker: 股票代码
        :param start: 起始日期
        :param end: 结束日期
        :param strategy: 策略类型 event_driven / ma_cross
        :param keywords: 事件关键词列表（event_driven 策略用）
        :param initial_capital: 初始资金
        :param commission: 单边手续费率
        :return: BacktestResult 对象
        """
        # 先校验策略类型，避免无效策略也发起网络请求
        valid_strategies = {"event_driven", "ma_cross"}
        if strategy not in valid_strategies:
            raise ValueError(f"不支持的策略: {strategy}，可选: {valid_strategies}")

        df = self.fetcher.get_daily(ticker, start=start, end=end)
        df = DataCleaner.full_pipeline(df)
        if keywords is None:
            keywords = []

        if strategy == "event_driven":
            signals = self._event_driven_signals(df, ticker, keywords)
        elif strategy == "ma_cross":
            signals = self._ma_cross_signals(df)

        result_df = self._simulate(df, signals, initial_capital, commission)
        return BacktestResult(ticker, strategy, result_df, initial_capital)

    # ------------------------------------------------------------------
    # 策略信号生成
    # ------------------------------------------------------------------
    def _event_driven_signals(self, df, ticker, keywords):
        """
        事件驱动策略：
        - 信号得分 > entry_threshold → 买入
        - 信号得分 < exit_threshold   → 卖出
        """
        signals = []
        window = 20  # 评分窗口
        for i in range(window, len(df)):
            chunk = df.iloc[:i+1]
            date_str = df.iloc[i]["date"].strftime("%Y-%m-%d")

            p_score = self.signal_engine.price_score(chunk)
            e_score = self.signal_engine.event_score(ticker, keywords, date_str)
            m_score = self.signal_engine.macro_score(date_str)

            w = self.signal_engine.weights
            total = int(p_score * w["price"] + e_score * w["event"] + m_score * w["macro"])
            total = min(100, max(0, total))

            if total >= self.entry_threshold:
                signals.append(1)   # 买入
            elif total <= self.exit_threshold:
                signals.append(-1)  # 卖出
            else:
                signals.append(0)   # 持有/观望

        # 前 window 天填充0
        return [0] * window + signals

    def _ma_cross_signals(self, df):
        """均线交叉策略：MA5 上穿 MA20 买入，下穿卖出。"""
        signals = []
        for i in range(len(df)):
            if i < 20 or pd.isna(df.iloc[i].get("ma5")) or pd.isna(df.iloc[i].get("ma20")):
                signals.append(0)
                continue
            prev = df.iloc[i-1]
            curr = df.iloc[i]
            if prev["ma5"] <= prev["ma20"] and curr["ma5"] > curr["ma20"]:
                signals.append(1)
            elif prev["ma5"] >= prev["ma20"] and curr["ma5"] < curr["ma20"]:
                signals.append(-1)
            else:
                signals.append(0)
        return signals

    # ------------------------------------------------------------------
    # 模拟交易
    # ------------------------------------------------------------------
    def _simulate(self, df, signals, initial_capital, commission):
        """
        模拟交易过程。
        :return: DataFrame[date, close, signal, position, cash, holdings, total_asset,
                          daily_return, cumulative_return, drawdown]
        """
        records = []
        position = 0        # 持仓股数
        cash = initial_capital
        peak_value = initial_capital

        for idx, (_, row) in enumerate(df.iterrows()):
            price = row["close"]
            sig = signals[idx] if idx < len(signals) else 0

            # 买入：用全部现金买入
            if sig == 1 and position == 0:
                shares = int(cash / (price * (1 + commission)))
                if shares > 0:
                    cost = shares * price * (1 + commission)
                    cash -= cost
                    position = shares

            # 卖出：清仓
            elif sig == -1 and position > 0:
                revenue = position * price * (1 - commission)
                cash += revenue
                position = 0

            total_asset = cash + position * price
            daily_return = 0
            if records:
                prev_asset = records[-1]["total_asset"]
                if prev_asset > 0:
                    daily_return = (total_asset - prev_asset) / prev_asset * 100

            cum_return = (total_asset - initial_capital) / initial_capital * 100

            peak_value = max(peak_value, total_asset)
            drawdown = (total_asset - peak_value) / peak_value * 100

            records.append({
                "date": row["date"],
                "close": price,
                "signal": sig,
                "position": position,
                "cash": round(cash, 2),
                "holdings": round(position * price, 2),
                "total_asset": round(total_asset, 2),
                "daily_return": round(daily_return, 4),
                "cumulative_return": round(cum_return, 2),
                "drawdown": round(drawdown, 2)
            })

        return pd.DataFrame(records)


class BacktestResult:
    """回测结果封装。"""

    def __init__(self, ticker, strategy, result_df, initial_capital):
        self.ticker = ticker
        self.strategy = strategy
        self.df = result_df
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
        """交易胜率：以卖出时是否盈利为准。"""
        if self.df.empty:
            return 0
        # 找出所有卖出信号
        sell_signals = self.df[self.df["signal"] == -1]
        if sell_signals.empty:
            return 0
        # 统计卖出时持仓盈利的交易
        wins = 0
        for idx in sell_signals.index:
            # 找到最近一次买入后的持仓成本
            buy_rows = self.df.loc[:idx][self.df.loc[:idx, "signal"] == 1]
            if buy_rows.empty:
                continue
            buy_price = buy_rows.iloc[-1]["close"]
            sell_price = self.df.loc[idx, "close"]
            if sell_price > buy_price:
                wins += 1
        return round(wins / len(sell_signals) * 100, 2) if len(sell_signals) > 0 else 0

    @property
    def trade_count(self):
        return len(self.df[self.df["signal"] != 0])

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
            f"  交易次数:   {s['trade_count']}"
        )
