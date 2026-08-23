"""事件驱动策略。

综合价格、事件、宏观三类评分（来自 signal_engine）：
- 综合评分 >= entry_threshold → 买入
- 综合评分 <= exit_threshold → 卖出

本策略需要 Backtester 上下文（signal_engine / ticker / keywords），
因此 needs_context=True，由 Backtester.run() 传入 ctx 调用
generate_signals_with_context 实现。
"""

import pandas as pd

from .base import BaseStrategy
from .registry import register


@register
class EventDrivenStrategy(BaseStrategy):
    name = "event_driven"
    display_name = "事件驱动"
    description = (
        "融合价格信号、事件催化、宏观环境的综合评分策略。"
        "需提供股票代码与事件关键词，由后端 signal_engine 实时打分。"
    )
    default_params = {}
    needs_context = True

    def generate_signals(self, df: pd.DataFrame) -> list:
        # 无上下文时退化为空信号（不应被直接调用）
        return [0] * len(df)

    def generate_signals_with_context(self, df: pd.DataFrame, ctx: dict) -> list:
        signal_engine = ctx.get("signal_engine")
        ticker = ctx.get("ticker", "")
        keywords = ctx.get("keywords") or []
        if signal_engine is None:
            return [0] * len(df)

        entry = signal_engine.entry_threshold
        exit_ = signal_engine.exit_threshold

        signals = []
        window = 20
        for i in range(window, len(df)):
            chunk = df.iloc[: i + 1]
            date_str = df.iloc[i]["date"].strftime("%Y-%m-%d")

            p_score = signal_engine.price_score(chunk)
            e_score = signal_engine.event_score(ticker, keywords, date_str)
            m_score = signal_engine.macro_score(date_str)

            w = signal_engine.weights
            total = int(p_score * w["price"] + e_score * w["event"] + m_score * w["macro"])
            total = min(100, max(0, total))

            if total >= entry:
                signals.append(1)
            elif total <= exit_:
                signals.append(-1)
            else:
                signals.append(0)

        return [0] * window + signals
