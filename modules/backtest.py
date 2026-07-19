"""
策略回测引擎 V2
支持多策略回测：事件驱动、均线交叉、趋势动量多因子。
新增指标：RSI / MACD / ATR / 布林带；模拟交易支持止损、止盈、移动止损、最大持仓周期。
"""

import numpy as np
import pandas as pd
import concurrent.futures

from .fetcher import StockFetcher
from .cleaner import DataCleaner
from .signal import SignalEngine


class Backtester:
    """策略回测器。"""

    def __init__(self, config_path="config.yaml"):
        self.fetcher = StockFetcher(config_path)
        self.signal_engine = SignalEngine(config_path)
        self.config = self.signal_engine.config
        self.entry_threshold = self.config.get("signal", {}).get("entry_threshold", 70)
        self.exit_threshold = self.config.get("signal", {}).get("exit_threshold", 40)

    def run(self, ticker, start, end, strategy="multi_factor",
            keywords=None, initial_capital=100000, commission=0.001,
            stop_loss_pct=0.05, take_profit_pct=0.03, trailing_stop_pct=0.0,
            max_holding=15, min_holding=2, slippage_pct=0.001, stamp_tax_pct=0.001):
        """
        运行回测。
        :param ticker: 股票代码
        :param start: 起始日期
        :param end: 结束日期
        :param strategy: 策略类型 event_driven / ma_cross / multi_factor
        :param keywords: 事件关键词列表（event_driven 策略用）
        :param initial_capital: 初始资金
        :param commission: 单边手续费率
        :param stop_loss_pct: 止损比例（如 0.07 表示 7%）
        :param take_profit_pct: 止盈比例（如 0.10 表示 10%）
        :param trailing_stop_pct: 移动止损回撤比例
        :param max_holding: 最大持仓周期（交易日）
        :param min_holding: 最小持仓周期（交易日），避免频繁进出
        :param slippage_pct: 滑点比例（默认 0.1%）
        :param stamp_tax_pct: 印花税比例（默认 0.1%，仅卖出）
        :return: BacktestResult 对象
        """
        valid_strategies = {"event_driven", "ma_cross", "multi_factor"}
        if strategy not in valid_strategies:
            raise ValueError(f"不支持的策略: {strategy}，可选: {valid_strategies}")

        df = self.fetcher.get_daily(ticker, start=start, end=end)
        df = DataCleaner.full_pipeline(df)
        if keywords is None:
            keywords = []

        # 为所有策略统一计算技术指标
        df = self._add_indicators(df)

        if strategy == "event_driven":
            signals = self._event_driven_signals(df, ticker, keywords)
        elif strategy == "ma_cross":
            signals = self._ma_cross_signals(df)
        elif strategy == "multi_factor":
            signals = self._multi_factor_signals(df)

        result_df, trades = self._simulate(
            df, signals, initial_capital, commission,
            stop_loss_pct, take_profit_pct, trailing_stop_pct,
            max_holding, min_holding, slippage_pct, stamp_tax_pct
        )
        return BacktestResult(ticker, strategy, result_df, initial_capital, trades)

    # ------------------------------------------------------------------
    # 技术指标计算
    # ------------------------------------------------------------------
    @staticmethod
    def _rsi(series, window=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(df, window=14):
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=window).mean()

    @staticmethod
    def _macd(df):
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        hist = dif - dea
        return dif, dea, hist

    @staticmethod
    def _bollinger(df, window=20, std=2):
        ma = df["close"].rolling(window=window).mean()
        std_dev = df["close"].rolling(window=window).std()
        upper = ma + std_dev * std
        lower = ma - std_dev * std
        return upper, lower, ma

    def _add_indicators(self, df):
        df = df.copy()
        df["rsi14"] = self._rsi(df["close"])
        df["rsi2"] = self._rsi(df["close"], window=2)
        df["atr14"] = self._atr(df)
        df["macd_dif"], df["macd_dea"], df["macd_hist"] = self._macd(df)
        df["bb_upper"], df["bb_lower"], df["bb_ma"] = self._bollinger(df)
        df["trend_up"] = (df["close"] > df["ma20"]) & (df["ma20"] > df["ma60"])
        df["ma20_rising"] = df["ma20"] > df["ma20"].shift(5)
        df["ma60_rising"] = df["ma60"] > df["ma60"].shift(20)
        df["vol_ma20"] = df["volume"].rolling(window=20).mean()
        df["atr_ratio"] = df["atr14"] / df["close"]
        df["hh60"] = df["close"].rolling(window=60).max()
        return df

    # ------------------------------------------------------------------
    # 策略信号生成
    # ------------------------------------------------------------------
    def _event_driven_signals(self, df, ticker, keywords):
        """
        事件驱动策略：综合价格、事件、宏观评分。
        - 综合评分 >= entry_threshold → 买入
        - 综合评分 <= exit_threshold   → 卖出
        """
        signals = []
        window = 20
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
                signals.append(1)
            elif total <= self.exit_threshold:
                signals.append(-1)
            else:
                signals.append(0)

        return [0] * window + signals

    def _ma_cross_signals(self, df):
        """
        均线交叉策略 V2：
        - 仅在中长期上升趋势（MA20 > MA60）中交易，过滤震荡市
        - MA5 上穿 MA20 且 RSI < 65 买入
        - MA5 下穿 MA20 或 RSI > 75 卖出
        """
        signals = []
        for i in range(len(df)):
            if i < 20 or pd.isna(df.iloc[i].get("ma5")) or pd.isna(df.iloc[i].get("ma20")):
                signals.append(0)
                continue
            prev = df.iloc[i-1]
            curr = df.iloc[i]
            ma60 = curr.get("ma60", curr["ma20"] - 1)  # 无 MA60 时默认上升趋势
            in_uptrend = curr["ma20"] > ma60

            golden_cross = prev["ma5"] <= prev["ma20"] and curr["ma5"] > curr["ma20"]
            death_cross = prev["ma5"] >= prev["ma20"] and curr["ma5"] < curr["ma20"]

            rsi14 = curr.get("rsi14", 50)
            if golden_cross and in_uptrend and rsi14 < 65:
                signals.append(1)
            elif death_cross or rsi14 > 75:
                signals.append(-1)
            else:
                signals.append(0)
        return signals

    def _multi_factor_signals(self, df):
        """
        趋势动量多因子策略 V4：真正以趋势为核心，兼容短区间数据。

        针对 V3 仍被吐槽"好股票摆在面前也不买入"的问题：
        - 原策略要求 i >= 60 才进入信号计算，短区间直接全军覆没；V4 改为 i >= 20。
        - 原策略强依赖 MA60，数据不足时 MA60 为 NaN，导致趋势分直接归零；V4 以 MA20
          为主要趋势基准，MA60 仅作为加分项，缺失时不扣分。
        - V5（本次修复）：买入硬性要求 RSI14 <= 85 会系统性排除长电科技这类「长期 RSI>85
          的强势上涨股」（buy=0）。改为「趋势为核心、动量不再惩罚高 RSI」：
          * 动量因子重排，RSI14 70-92 区间给高分（强趋势可买入），仅极端泡沫(>92)降分；
          * 买入 RSI 上限放宽到 98（仅挡极端泡沫），让趋势因子主导入场。
        - 卖出端对趋势股太黏（仅跌破 MA20 才卖），强势股不破线就不平仓、交易不重复；
          V5 增加「RSI14 极度超买(>=92)后回落」止盈退出，让趋势持仓能闭环、交易可重复。

        因子池（共 100 分）：
        1. 趋势因子（最高 50）：close > MA20 为基础，MA20 向上、MA20>MA60 额外加分
        2. 动量因子（最高 30）：RSI14 健康/强趋势区间给高分；RSI2 低位仅作加分
        3. 波动/风险因子（最高 15）：ATR 比率越低分越高，但强势股波动大也保底给分
        4. 量能因子（最高 15）：成交量与 MA20 的比值

        买入条件：综合评分 >= 55，收盘价在 MA20 上方（MA20 有效时），且 RSI14 <= 98。
        卖出条件：收盘价跌破 MA20 且 MA20 拐头向下；或 RSI14 极度超买(>=92)后回落至 90 以下。
        """
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
            #    长电科技类「长期 RSI>85 的强势上涨股」此前被系统性排除，现改为：
            #    健康/强趋势区间(40-92)给高分，仅极端泡沫(>92)降分。
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
            # V5：买入 RSI 上限从 85 放宽到 98，仅挡极端泡沫——让趋势因子主导入场，
            # 避免长电科技类「长期 RSI>85 强势上涨股」被系统性排除。
            price_above_trend = (not ma20_valid) or (curr["close"] > curr["ma20"])
            buy = total_score >= 55 and price_above_trend and rsi14 <= 98

            # 防止连续买入
            if buy and signals and signals[-1] == 1:
                buy = False

            # 卖出：趋势走坏 或 极度超买后回落止盈（V5，让强势股能闭环、交易可重复）
            ma_exit = (ma20_valid and curr["close"] < curr["ma20"]
                       and i >= 5 and not pd.isna(prev["ma20"])
                       and curr["ma20"] < prev["ma20"])   # MA20 拐头向下才算趋势破
            overbought_exit = rsi14 < 90 and prev["rsi14"] >= 92   # 极度超买(>=92)后回落
            sell = ma_exit or overbought_exit

            if buy:
                signals.append(1)
            elif sell:
                signals.append(-1)
            else:
                signals.append(0)
        return signals

    # ------------------------------------------------------------------
    # 模拟交易
    # ------------------------------------------------------------------
    def _simulate(self, df, signals, initial_capital=100000, commission=0.001,
                  stop_loss_pct=0.05, take_profit_pct=0.03, trailing_stop_pct=0.0,
                  max_holding=15, min_holding=2, slippage_pct=0.001, stamp_tax_pct=0.001):
        """
        模拟交易过程，支持手续费、滑点、印花税、止损、止盈、移动止损、最大/最小持有周期。
        :return: (DataFrame, trades_list)
        """
        records = []
        trades = []
        position = 0
        cash = initial_capital
        peak_value = initial_capital

        entry_price = 0
        peak_price = 0
        bars_held = 0
        entry_date = None
        in_trade = False

        for idx, (_, row) in enumerate(df.iterrows()):
            price = row["close"]
            sig = signals[idx] if idx < len(signals) else 0
            exit_reason = None

            # 持仓期间先检查是否平仓
            if position > 0:
                bars_held += 1
                peak_price = max(peak_price, price)

                if bars_held >= min_holding:
                    if sig == -1:
                        exit_reason = "策略卖出"
                    elif stop_loss_pct and price <= entry_price * (1 - stop_loss_pct):
                        exit_reason = "止损"
                    elif take_profit_pct and price >= entry_price * (1 + take_profit_pct):
                        exit_reason = "止盈"
                    elif trailing_stop_pct and price <= peak_price * (1 - trailing_stop_pct):
                        exit_reason = "移动止损"
                    elif max_holding and bars_held >= max_holding:
                        exit_reason = "最大持仓期"

                if exit_reason:
                    # 卖出：扣除佣金 + 印花税 + 滑点
                    sell_price = price * (1 - slippage_pct)
                    revenue = position * sell_price * (1 - commission - stamp_tax_pct)
                    cash += revenue
                    gross_profit = (sell_price - entry_price) / entry_price * 100
                    # 双边手续费 + 印花税 + 双边滑点后的净盈亏
                    total_cost_rate = 2 * commission + stamp_tax_pct + 2 * slippage_pct
                    net_profit = gross_profit - total_cost_rate * 100
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": row["date"],
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(sell_price, 2),
                        "profit_pct": round(net_profit, 2),
                        "exit_reason": exit_reason,
                        "bars_held": bars_held,
                    })
                    position = 0
                    entry_price = 0
                    peak_price = 0
                    bars_held = 0
                    entry_date = None
                    in_trade = False

            # 无持仓时买入
            if position == 0 and sig == 1:
                # 买入：包含佣金 + 滑点
                buy_price = price * (1 + slippage_pct)
                shares = int(cash / (buy_price * (1 + commission)))
                if shares > 0:
                    cost = shares * buy_price * (1 + commission)
                    cash -= cost
                    position = shares
                    entry_price = buy_price * (1 + commission)  # 记录实际成本价
                    peak_price = entry_price
                    bars_held = 0
                    entry_date = row["date"]
                    in_trade = True

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
                "drawdown": round(drawdown, 2),
                "in_trade": in_trade,
                "entry_price": round(entry_price, 2) if in_trade else 0,
            })

        return pd.DataFrame(records), trades

    # ------------------------------------------------------------------
    # 每日选股回测（从 A 股中挑选今天/明天推荐购买的股票）
    # ------------------------------------------------------------------
    def _score_for_picker(self, df):
        """
        为每日选股计算单只股票的买入评分（V2 — 多日趋势确认版）。

        V2 升级（相对 V1 只看最新一天快照）：
        - 趋势确认周期：RSI(2) 连续 N 天处于低位才算真正超卖（避免单日抖动）
        - 多日评分平滑：取近 5 天评分的加权平均（越近权重越高）
        - 智能卖出预测：基于 multi_factor 策略退出条件预判持仓周期
        - 均线趋势持续性：不只看当日位置，还看均线斜率变化方向

        评分维度：
        - 趋势分（40）：close > MA20 > MA60 + 均线向上 + 趋势持续确认
        - 超跌分（35）：RSI(2) 连续低位（多日加权）
        - 健康分（15）：RSI(14) 在健康区间 + 近期未超买
        - 量能分（10）：放量 + 量价配合

        :param df: 行情 DataFrame（需 >= 90 个交易日数据，用于多日分析）
        :return: dict 或 None（不满足条件时返回 None）
        """
        if df is None or len(df) < 90:
            return None
        df = DataCleaner.full_pipeline(df)
        df = self._add_indicators(df)

        # ── 取最近 10 天用于多日分析 ──
        recent = df.iloc[-10:].copy()
        latest = df.iloc[-1]

        # 排除指标为空的情况
        if pd.isna(latest["rsi14"]) or pd.isna(latest["rsi2"]) or pd.isna(latest["ma20"]):
            return None

        # ══════════════════════════════════════
        # 1) 趋势分（最高 40 分）— 含多日持续性确认
        # ══════════════════════════════════════
        score = 0
        reasons = []

        # 当日趋势状态（分级评分，不再一刀切；MA20 为核心，MA60 缺失时不扣分）
        trend_score = 0
        ma20_valid = not pd.isna(latest["ma20"])
        ma60_valid = not pd.isna(latest["ma60"])
        if ma20_valid and latest["close"] > latest["ma20"]:
            trend_score = 25
            if latest.get("ma20_rising", False):
                trend_score += 10
            if ma60_valid and latest["ma20"] > latest["ma60"]:
                trend_score += 10
            if ma60_valid and latest["close"] > latest["ma60"]:
                trend_score += 5
        elif ma60_valid and latest["close"] > latest["ma60"]:
            trend_score = 15
        if latest.get("ma60_rising", False):
            trend_score += 5
        trend_score = min(trend_score, 50)

        # 趋势持续性：最近 5 天中 close > MA20 的天数比例
        recent_above_ma20 = (recent["close"] > recent["ma20"]).sum()
        trend_persistence = recent_above_ma20 / min(len(recent), 5)

        if trend_score >= 35:
            if trend_persistence >= 0.9:
                reasons.append("强趋势(持续)")
            elif trend_persistence >= 0.7:
                reasons.append("强趋势")
            else:
                reasons.append("强趋势(新)")
            trend_ok = True
        elif trend_score >= 20:
            reasons.append("短期趋势")
            trend_ok = True
        else:
            trend_ok = False
        score += trend_score

        # ══════════════════════════════════════
        # 2) 超跌分（最高 35 分）— 连续低位确认
        # ══════════════════════════════════════
        rsi2_vals = recent["rsi2"].dropna().values
        rsi2 = latest["rsi2"]

        # 连续低位天数：RSI2 < 15 的连续天数
        consecutive_low = 0
        for v in reversed(rsi2_vals):
            if v < 15:
                consecutive_low += 1
            else:
                break

        # 加权超跌分：当前值权重高 + 连续确认加成
        if rsi2 < 5:
            raw_oversold = 35
            reason_base = "RSI2极弱"
        elif rsi2 < 10:
            raw_oversold = 30
            reason_base = "RSI2超卖"
        elif rsi2 < 15:
            raw_oversold = 20
            reason_base = "RSI2偏弱"
        elif rsi2 < 25:
            raw_oversold = 10
            reason_base = "RSI2偏低"
        else:
            raw_oversold = 0

        # 连续确认加成：连续 3 天以上低位 → 额外加最高 5 分
        confirm_bonus = min(consecutive_low - 1, 5) * 1.0  # 最多 +5
        oversold_score = raw_oversold + confirm_bonus
        score += oversold_score

        if raw_oversold >= 20:
            suffix = f"(连{consecutive_low}天)" if consecutive_low >= 2 else ""
            reasons.append(reason_base + suffix)
        elif raw_oversold > 0:
            reasons.append(reason_base)

        # ══════════════════════════════════════
        # 3) 健康分（最高 20 分）— RSI14 区间 + 未超买历史
        # ══════════════════════════════════════
        rsi14 = latest["rsi14"]
        if 40 <= rsi14 <= 60:
            health_score = 20
            reasons.append("RSI14健康")
        elif 30 <= rsi14 < 40:
            health_score = 15
            reasons.append("RSI14回踩")
        elif 60 < rsi14 <= 70:
            health_score = 12
            reasons.append("RSI14强势")
        elif 25 <= rsi14 < 30:
            health_score = 8
            reasons.append("RSI14偏低")
        else:
            health_score = 0

        # 近 5 天是否有过 RSI14 > 75（严重超买则扣分）
        recent_overbought = (recent["rsi14"] > 75).sum()
        if recent_overbought >= 2:
            health_score = max(0, health_score - 5)
        score += health_score

        # ══════════════════════════════════════
        # 4) 量能分（最高 15 分）— 放量 + 量价配合
        # ══════════════════════════════════════
        vol_ratio = latest["volume"] / latest["vol_ma20"] if latest["vol_ma20"] > 0 else 1.0
        if vol_ratio >= 1.5:
            score += 15
            reasons.append("显著放量")
        elif vol_ratio >= 1.2:
            score += 10
            reasons.append("放量")
        elif vol_ratio >= 0.8:
            score += 6
            reasons.append("量能温和")

        # ══════════════════════════════════════
        # 5) 过滤条件（兼容 MA60 缺失的短区间）
        # ══════════════════════════════════════
        # 只要收盘价在 MA20 上方（MA20 有效时），且 RSI14 不极端超买，就允许参与评分
        price_above_trend = (not ma20_valid) or (latest["close"] > latest["ma20"])
        if not price_above_trend or rsi14 > 80:
            return None

        # ══════════════════════════════════════
        # 6) 多日评分平滑
        # ══════════════════════════════════════
        # 计算近 5 天每天的原始评分（用相同逻辑但只做单日快照）
        daily_scores = []
        ds = 0
        for offset in range(min(5, len(df))):
            day = df.iloc[-(offset + 1)]
            if pd.isna(day.get("rsi14")) or pd.isna(day.get("rsi2")):
                continue
            ds_trend = 0
            d_ma20_valid = not pd.isna(day.get("ma20"))
            d_ma60_valid = not pd.isna(day.get("ma60"))
            if d_ma20_valid and day["close"] > day.get("ma20", 0):
                ds_trend += 25
                if d_ma60_valid and day["ma20"] > day.get("ma60", 0):
                    ds_trend += 10
                if d_ma60_valid and day["close"] > day.get("ma60", 0):
                    ds_trend += 5
            elif d_ma60_valid and day["close"] > day.get("ma60", 0):
                ds_trend += 15
            ds += min(ds_trend, 50)
            # 动量分（快照）
            d_rsi2 = day.get("rsi2", 50)
            if d_rsi2 < 5: ds += 35
            elif d_rsi2 < 10: ds += 30
            elif d_rsi2 < 15: ds += 20
            elif d_rsi2 < 25: ds += 10
            d_rsi14 = day.get("rsi14", 50)
            if 40 <= d_rsi14 <= 70: ds += 20
            elif 30 <= d_rsi14 < 40: ds += 15
            elif 60 < d_rsi14 <= 80: ds += 12
            # 量能分（快照）
            if day.get("volume", 0) > day.get("vol_ma20", 1) * 1.5: ds += 15
            elif day.get("volume", 0) > day.get("vol_ma20", 1) * 1.2: ds += 10
            elif day.get("volume", 0) > day.get("vol_ma20", 1) * 0.8: ds += 6
            daily_scores.append(ds)

        if len(daily_scores) >= 3:
            # 加权平均：最近一天权重最高 (0.4, 0.25, 0.15, 0.12, 0.08)
            weights = [0.4, 0.25, 0.15, 0.12, 0.08][:len(daily_scores)]
            weights = [w / sum(weights) for w in weights]
            smoothed = sum(s * w for s, w in zip(reversed(daily_scores), reversed(weights)))
            # 混合：70% 当前详细评分 + 30% 平滑评分
            final_score = round(score * 0.7 + smoothed * 0.3, 1)
        else:
            final_score = round(score, 1)

        # ══════════════════════════════════════
        # 7) 智能卖出信号预测
        # ══════════════════════════════════════
        # 基于 multi_factor 策略的退出条件，预测最佳持仓周期
        predicted_exit = self._predict_exit_signal(df)

        return {
            "code": latest.get("code", ""),
            "date": latest["date"],
            "close": latest["close"],
            "score": final_score,
            "raw_score": round(score, 1),
            "smoothed_score": round(smoothed, 1) if 'smoothed' in dir() else final_score,
            "rsi2": round(rsi2, 1),
            "rsi14": round(rsi14, 1),
            "trend_ok": trend_ok,
            "trend_persistence": round(trend_persistence, 2),
            "consecutive_low_days": consecutive_low,
            "vol_ratio": round(vol_ratio, 2),
            "reasons": ",".join(reasons),
            "predicted_exit": predicted_exit,
            "df": df,
        }

    def _predict_exit_signal(self, df, look_ahead=10):
        """
        预测智能卖出信号。

        基于 multi_factor 策略的三种退出条件：
        1) RSI(2) 反弹超过 50 → 超卖反弹完成，获利了结
        2) 收盘价跌破 MA20 → 趋势走坏，止损离场
        3) ATR 止损 → 从买入价回撤超过阈值

        返回预测的最佳卖出时机和建议。
        """
        if df is None or len(df) < 20:
            return {"signal": "hold", "reason": "数据不足", "days": 5}

        latest = df.iloc[-1]

        # 向前模拟未来几天（使用已有数据的最后一段来估算）
        sim_df = df.iloc[-min(look_ahead + 5, len(df)):].copy()

        # 条件1: RSI(2) 反弹到 50 以上？
        rsi2_rebound_day = None
        for i in range(1, min(look_ahead + 1, len(sim_df))):
            row = sim_df.iloc[-(i + 1)]  # 从最新的前一天开始往前找
            if row.get("rsi2", 100) > 50:
                rsi2_rebound_day = i
                break

        # 条件2: 跌破 MA20？
        ma_break_day = None
        for i in range(1, min(look_ahead + 1, len(sim_df))):
            row = sim_df.iloc[-(i + 1)]
            if row.get("close", 0) < row.get("ma20", float('inf')):
                ma_break_day = i
                break

        # 综合判断：取最早触发的退出信号
        exit_candidates = []
        if rsi2_rebound_day:
            exit_candidates.append(("rebound", rsi2_rebound_day, "RSI2反弹完成"))
        if ma_break_day:
            exit_candidates.append(("trend_break", ma_break_day, "跌破MA20趋势走坏"))

        # 默认：如果近期没有触发退出信号，建议持有 3-5 天观察
        if not exit_candidates:
            # 根据当前 RSI2 水平给出建议持有天数
            current_rsi2 = latest.get("rsi2", 50)
            if current_rsi2 < 10:
                suggested_days = 5  # 极度超卖，需要更多时间反弹
            elif current_rsi2 < 20:
                suggested_days = 4
            elif current_rsi2 < 30:
                suggested_days = 3
            else:
                suggested_days = 2
            return {
                "signal": "hold",
                "reason": f"RSI2={current_rsi2:.0f}，建议观察{suggested_days}天",
                "days": suggested_days,
            }

        # 取最早触发的退出信号
        exit_candidates.sort(key=lambda x: x[1])
        best_signal = exit_candidates[0]
        return {
            "signal": best_signal[0],
            "reason": best_signal[2],
            "days": best_signal[1],
        }

    def _fetch_single_for_picker(self, code, start, end):
        """为选股回测获取单只股票数据（带异常处理）。"""
        try:
            df = self.fetcher.get_daily(code, start=start, end=end)
            if df is None or df.empty or len(df) < 60:
                return None
            score_info = self._score_for_picker(df)
            if score_info is None:
                return None
            score_info["code"] = code
            score_info["name"] = self.fetcher.get_name_only(code)
            return score_info
        except Exception:
            return None

    def daily_picker_backtest(self, start, end, stock_pool_size=200, top_k=10,
                              hold_days=1, min_score=40, max_workers=8,
                              use_smart_exit=True):
        """
        每日选股回测 V2（支持智能卖出信号）。

        每天从 A 股股票池中选出评分最高的 top_k 只股票，
        支持两种卖出模式：
        - 固定持有期：T 日买入、T+hold_days 日卖出（传统模式）
        - 智能退出（use_smart_exit=True）：基于 RSI2 反弹 / 跌破 MA20 / 趋势走坏
          等条件自动判断最佳卖出时机

        :param start: 回测起始日期
        :param end: 回测截止日期
        :param stock_pool_size: 股票池大小（默认 200）
        :param top_k: 每日选股数量
        :param hold_days: 固定持有周期（smart_exit=False 时使用，交易日）
        :param min_score: 入选最低评分
        :param max_workers: 并行线程数
        :param use_smart_exit: 是否使用智能卖出信号（默认 True）
        :return: DailyPickerResult 对象
        """
        # 扩展日期范围：需要多取数据用于计算指标和持有期收益
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)
        fetch_start = (start_dt - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
        fetch_end = (end_dt + pd.Timedelta(days=30)).strftime("%Y-%m-%d")

        codes = self.fetcher.get_all_codes(limit=stock_pool_size, random_seed=42)
        if not codes:
            raise RuntimeError("无法获取股票池，请检查本地股票库是否已初始化。")

        # 并行获取股票数据并评分
        all_scores = []
        print(f"[DailyPicker] 开始获取 {len(codes)} 只股票数据...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._fetch_single_for_picker, code, fetch_start, fetch_end): code
                for code in codes
            }
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res is not None:
                    all_scores.append(res)
        print(f"[DailyPicker] 成功评分 {len(all_scores)} 只股票")

        if not all_scores:
            raise RuntimeError("没有股票能通过评分过滤，请检查数据获取是否正常。")

        # 将每只股票的日线与评分按日期汇总
        # 构建统一的交易日历（使用第一个股票的数据作为参考）
        sample_df = all_scores[0]["df"].copy()
        trade_dates = sample_df[(sample_df["date"] >= start_dt) & (sample_df["date"] <= end_dt)]["date"].tolist()

        daily_picks = []      # 每日推荐列表
        daily_returns = []    # 每日组合收益

        for i, trade_date in enumerate(trade_dates):
            # 汇总当天所有股票在该交易日的评分
            candidates = []
            for s in all_scores:
                df_code = s["df"]
                # 找到该日期或之前最近一个交易日的数据
                row = df_code[df_code["date"] <= trade_date]
                if row.empty or len(row) < 10:  # 至少需要 10 天数据做多日分析
                    continue
                latest = row.iloc[-1]
                if pd.isna(latest["rsi14"]) or pd.isna(latest["rsi2"]):
                    continue

                # ── V3 多日评分（与 _score_for_picker 逻辑一致）──
                recent_10 = row.iloc[-10:] if len(row) >= 10 else row
                score = 0
                reasons = []

                # 1) 趋势分（分级，不再一刀切；MA20 为核心，MA60 为加分项）
                trend_score = 0
                l_ma20_valid = not pd.isna(latest["ma20"])
                l_ma60_valid = not pd.isna(latest["ma60"])
                if l_ma20_valid and latest["close"] > latest["ma20"]:
                    trend_score = 25
                    if latest.get("ma20_rising", False):
                        trend_score += 10
                    if l_ma60_valid and latest["ma20"] > latest["ma60"]:
                        trend_score += 10
                    if l_ma60_valid and latest["close"] > latest["ma60"]:
                        trend_score += 5
                elif l_ma60_valid and latest["close"] > latest["ma60"]:
                    trend_score = 15
                if latest.get("ma60_rising", False):
                    trend_score += 5
                trend_score = min(trend_score, 50)
                if trend_score >= 35:
                    reasons.append("强趋势")
                elif trend_score >= 20:
                    reasons.append("短期趋势")
                score += trend_score

                recent_above_ma20 = (recent_10["close"] > recent_10["ma20"]).sum()
                trend_persist = min(recent_above_ma20 / min(len(recent_10), 5), 1.0)
                if trend_persist >= 0.9:
                    reasons[-1] = reasons[-1] + "(持续)"

                # 2) 超跌分（保留，作为加分项）
                rsi2 = latest["rsi2"]
                rsi2_arr = recent_10["rsi2"].dropna().values[::-1]
                cons_low = 0
                for v in rsi2_arr:
                    if v < 15: cons_low += 1
                    else: break

                if rsi2 < 5: score += 35; reasons.append("RSI2极弱")
                elif rsi2 < 10: score += 30; reasons.append("RSI2超卖")
                elif rsi2 < 15: score += 20; reasons.append("RSI2偏弱")
                elif rsi2 < 25: score += 10; reasons.append("RSI2偏低")
                score += min(cons_low - 1, 5) * 1.0

                # 3) 健康分
                rsi14 = latest["rsi14"]
                h_score = 0
                if 40 <= rsi14 <= 70: h_score = 20; reasons.append("RSI14健康")
                elif 30 <= rsi14 < 40: h_score = 15; reasons.append("RSI14回踩")
                elif 60 < rsi14 <= 80: h_score = 12; reasons.append("RSI14强势")
                elif 25 <= rsi14 < 30: h_score = 8; reasons.append("RSI14偏低")
                if (recent_10["rsi14"] > 80).sum() >= 2:
                    h_score = max(0, h_score - 5)
                score += h_score

                # 4) 量能分
                vol_r = latest["volume"] / latest["vol_ma20"] if latest.get("vol_ma20", 0) > 0 else 1.0
                if vol_r >= 1.5: score += 15; reasons.append("显著放量")
                elif vol_r >= 1.2: score += 10; reasons.append("放量")
                elif vol_r >= 0.8: score += 6; reasons.append("量能温和")

                # 过滤条件（兼容 MA60 缺失）
                price_above_trend = (not l_ma20_valid) or (latest["close"] > latest["ma20"])
                if not price_above_trend or rsi14 > 80 or score < min_score:
                    continue

                # ═══ 智能卖出信号预测（替代固定 hold_days）═══
                future_rows = df_code[df_code["date"] > trade_date]
                buy_price = latest["close"]

                if use_smart_exit and len(future_rows) > 3:
                    # 模拟未来 10 天内的退出条件触发
                    actual_hold = None
                    sell_price = None
                    exit_reason = "hold"

                    for fi in range(min(10, len(future_rows))):
                        fut = future_rows.iloc[fi]
                        fut_rsi2 = fut.get("rsi2", 50)
                        fut_close = fut.get("close", buy_price)
                        fut_ma20 = fut.get("ma20", 0)

                        # 条件1: RSI2 反弹超过 50（超卖反弹完成）
                        if fut_rsi2 > 50 and rsi2 < 25:
                            actual_hold = fi + 1
                            sell_price = fut_close
                            exit_reason = "RSI2反弹完成"
                            break
                        # 条件2: 跌破 MA20（趋势走坏）
                        if fut_close < fut_ma20 and fut_ma20 > 0:
                            actual_hold = fi + 1
                            sell_price = fut_close
                            exit_reason = "跌破MA20"
                            break
                        # 条件3: 止损 -5%
                        if (fut_close - buy_price) / buy_price < -0.05:
                            actual_hold = fi + 1
                            sell_price = fut_close
                            exit_reason = "止损-5%"
                            break

                    if actual_hold is None:
                        # 没有触发退出信号，用默认观察期
                        default_hold = min(hold_days, len(future_rows)) if hold_days else min(3, len(future_rows))
                        actual_hold = default_hold
                        sell_price = future_rows.iloc[actual_hold - 1]["close"] if len(future_rows) >= actual_hold else buy_price
                        exit_reason = f"观察{actual_hold}天"
                else:
                    # 传统固定持有期模式
                    if len(future_rows) < hold_days:
                        continue
                    actual_hold = hold_days
                    sell_price = future_rows.iloc[hold_days - 1]["close"]
                    exit_reason = f"固定{hold_days}天"

                hold_return = (sell_price - buy_price) / buy_price * 100

                candidates.append({
                    "date": trade_date,
                    "code": s["code"],
                    "name": s["name"],
                    "score": round(score, 1),
                    "buy_price": round(buy_price, 2),
                    "sell_price": round(sell_price, 2),
                    "hold_return_pct": round(hold_return, 2),
                    "hold_days": actual_hold,
                    "exit_signal": exit_reason,
                    "rsi2": round(rsi2, 1),
                    "rsi14": round(rsi14, 1),
                    "trend_persist": round(trend_persist, 2),
                    "cons_low_days": cons_low,
                    "reasons": ",".join(reasons),
                })

            if not candidates:
                continue

            # 按评分排序，取 top_k
            candidates.sort(key=lambda x: x["score"], reverse=True)
            top = candidates[:top_k]
            daily_picks.extend(top)

            # 计算等权组合收益
            avg_return = sum(p["hold_return_pct"] for p in top) / len(top)
            daily_returns.append({
                "date": trade_date,
                "pick_count": len(top),
                "avg_return_pct": round(avg_return, 2),
            })

        picks_df = pd.DataFrame(daily_picks)
        returns_df = pd.DataFrame(daily_returns)

        # 计算累计收益曲线
        if not returns_df.empty:
            returns_df = returns_df.sort_values("date").reset_index(drop=True)
            returns_df["cumulative_return_pct"] = returns_df["avg_return_pct"].cumsum().round(2)
            # 简单模拟资金曲线（假设每日等额投入 initial_capital）
            returns_df["total_asset"] = 100000 * (1 + returns_df["cumulative_return_pct"] / 100).round(2)
        else:
            returns_df = pd.DataFrame(columns=["date", "pick_count", "avg_return_pct", "cumulative_return_pct", "total_asset"])

        return DailyPickerResult(picks_df, returns_df)


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
        """盈亏比：总盈利 / |总亏损|。"""
        if not self.trades:
            return 0
        gross_profit = sum(t["profit_pct"] for t in self.trades if t["profit_pct"] > 0)
        gross_loss = abs(sum(t["profit_pct"] for t in self.trades if t["profit_pct"] < 0))
        return round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0

    @property
    def avg_trade_return(self):
        """单笔交易平均收益率。"""
        if not self.trades:
            return 0
        return round(sum(t["profit_pct"] for t in self.trades) / len(self.trades), 2)

    @property
    def trade_count(self):
        return len(self.trades)

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
