"""均线交叉策略 V2。

- 仅在中长期上升趋势（MA20 > MA60）中交易，过滤震荡市
- MA5 上穿 MA20 且 RSI < 65 买入
- MA5 下穿 MA20 或 RSI > 75 卖出

注意：原 backtest._ma_cross_signals 依赖 ma5 列，但 Backtester._add_indicators
未计算 ma5，导致该策略历史区间信号恒为 0（废策略）。这里在策略内自行补算 ma5，
不污染 Backtester 的通用指标管线。
"""

import pandas as pd

from .base import BaseStrategy
from .registry import register


@register
class MaCrossStrategy(BaseStrategy):
    name = "ma_cross"
    display_name = "均线交叉"
    description = (
        "MA5 上穿 MA20（金叉）且 RSI<65 买入，死叉或 RSI>75 卖出。"
        "仅在 MA20>MA60 的上升趋势中交易，过滤震荡市噪音。"
    )
    default_params = {"buy_rsi_cap": 65, "sell_rsi_floor": 75}

    def generate_signals(self, df: pd.DataFrame) -> list:
        self.validate_df(df)
        d = df.copy()
        # 补算 ma5（Backtester._add_indicators 未提供，原策略因此失效）
        if "ma5" not in d.columns:
            d["ma5"] = d["close"].rolling(window=5).mean()

        signals = []
        for i in range(len(d)):
            if i < 20 or pd.isna(d.iloc[i].get("ma5")) or pd.isna(d.iloc[i].get("ma20")):
                signals.append(0)
                continue
            prev = d.iloc[i - 1]
            curr = d.iloc[i]
            ma60 = curr.get("ma60", curr["ma20"] - 1)  # 无 MA60 时默认上升趋势
            in_uptrend = curr["ma20"] > ma60

            golden_cross = prev["ma5"] <= prev["ma20"] and curr["ma5"] > curr["ma20"]
            death_cross = prev["ma5"] >= prev["ma20"] and curr["ma5"] < curr["ma20"]

            rsi14 = curr.get("rsi14", 50)
            if golden_cross and in_uptrend and rsi14 < self.default_params["buy_rsi_cap"]:
                signals.append(1)
            elif death_cross or rsi14 > self.default_params["sell_rsi_floor"]:
                signals.append(-1)
            else:
                signals.append(0)
        return signals
