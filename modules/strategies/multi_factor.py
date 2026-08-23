"""趋势动量多因子策略 V5（推荐）。

V5 修复长电科技类「长期 RSI>85 强势上涨股」被系统性排除的问题：
- 动量因子重排，RSI14 70-92 区间给高分（强趋势可买入），仅极端泡沫(>92)降分；
- 买入 RSI 上限放宽到 98（仅挡极端泡沫），让趋势因子主导入场；
- 卖出端增加「RSI14 极度超买(>=92)后回落」止盈，让趋势持仓能闭环、交易可重复。
"""

import pandas as pd

from .base import BaseStrategy
from .registry import register


@register
class MultiFactorStrategy(BaseStrategy):
    name = "multi_factor"
    display_name = "趋势动量多因子（推荐）"
    description = (
        "趋势为核心、动量不惩罚高 RSI 的多因子策略。覆盖短区间数据，"
        "对长电科技类长期强势上涨股也能产生信号。适合趋势确认后买入、趋势走坏时卖出。"
    )
    default_params = {
        "entry_score": 55,
        "rsi_buy_cap": 98,
        "overbought_exit": 92,
    }

    def generate_signals(self, df: pd.DataFrame) -> list:
        self.validate_df(df)
        signals = []
        for i in range(len(df)):
            if i < 20 or pd.isna(df.iloc[i]["rsi14"]):
                signals.append(0)
                continue

            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            ma20_valid = not pd.isna(curr["ma20"])
            ma60_valid = not pd.isna(curr["ma60"])

            # 1. 趋势因子（最高 50）—— MA20 为核心，MA60 为加分项
            trend_score = 0
            if ma20_valid and curr["close"] > curr["ma20"]:
                trend_score += 25  # 站上 MA20
                if i >= 5 and not pd.isna(df.iloc[i - 5]["ma20"]) and curr["ma20"] > df.iloc[i - 5]["ma20"]:
                    trend_score += 10  # MA20 向上
                if ma60_valid and curr["ma20"] > curr["ma60"]:
                    trend_score += 10  # 中长期均线多头排列
                if ma60_valid and curr["close"] > curr["ma60"]:
                    trend_score += 5  # 收盘价在 MA60 上方
            elif ma60_valid and curr["close"] > curr["ma60"]:
                trend_score += 15  # 仅站上 MA60（MA20 缺失或无效时）
            trend_score = min(trend_score, 50)

            # 2. 动量因子（最高 30）—— 强趋势也高分，不再惩罚高 RSI（V5 修复）
            rsi14 = curr["rsi14"]
            if 40 <= rsi14 <= 70:
                momentum_score = 25
            elif 70 < rsi14 <= 85:
                momentum_score = 22      # 强趋势，可买入
            elif 85 < rsi14 <= 92:
                momentum_score = 18      # 超买但未极端，趋势仍强
            elif 30 <= rsi14 < 40:
                momentum_score = 20
            elif rsi14 < 30:
                momentum_score = 10
            else:  # rsi14 > 92 极端泡沫，谨慎
                momentum_score = 8

            rsi2 = curr["rsi2"]
            if rsi2 < 20:
                momentum_score += 5
            elif rsi2 < 30:
                momentum_score += 3
            momentum_score = min(momentum_score, 30)

            # 3. 波动/风险因子（最高 15）—— 给强势股波动保底分
            atr_ratio = curr["atr_ratio"]
            if atr_ratio < 0.05:
                vol_score = 15
            elif atr_ratio < 0.10:
                vol_score = 12
            elif atr_ratio < 0.15:
                vol_score = 8
            else:
                vol_score = 4
            # 布林带下轨反弹作为加分
            if not pd.isna(curr.get("bb_lower")) and not pd.isna(prev.get("bb_lower")):
                if curr["close"] > curr["bb_lower"] and prev["close"] <= prev["bb_lower"]:
                    vol_score += 3
            vol_score = min(vol_score, 18)

            # 4. 量能因子（最高 15）
            vol_ma20 = curr.get("vol_ma20", 0)
            if vol_ma20 > 0:
                vol_ratio = curr["volume"] / vol_ma20
                if vol_ratio >= 1.5:
                    volume_score = 15
                elif vol_ratio >= 1.2:
                    volume_score = 10
                elif vol_ratio >= 0.8:
                    volume_score = 6
                else:
                    volume_score = 0
            else:
                volume_score = 0

            total_score = trend_score + momentum_score + vol_score + volume_score

            # 买入：评分 >= 55 且收盘价在 MA20 上方（或 MA20 缺失时默认允许）
            # V5：买入 RSI 上限从 85 放宽到 98，仅挡极端泡沫——让趋势因子主导入场。
            price_above_trend = (not ma20_valid) or (curr["close"] > curr["ma20"])
            buy = total_score >= self.default_params["entry_score"] and price_above_trend and rsi14 <= self.default_params["rsi_buy_cap"]

            # 防止连续买入
            if buy and signals and signals[-1] == 1:
                buy = False

            # 卖出：趋势走坏 或 极度超买后回落止盈（V5）
            ma_exit = (ma20_valid and curr["close"] < curr["ma20"]
                       and i >= 5 and not pd.isna(prev["ma20"])
                       and curr["ma20"] < prev["ma20"])   # MA20 拐头向下才算趋势破
            overbought_exit = rsi14 < 90 and prev["rsi14"] >= self.default_params["overbought_exit"]
            sell = ma_exit or overbought_exit

            if buy:
                signals.append(1)
            elif sell:
                signals.append(-1)
            else:
                signals.append(0)
        return signals
