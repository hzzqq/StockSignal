"""双趋势共振策略（GMMA + 一目均衡 + ADX）。

纯趋势跟踪，不看 RSI，天然覆盖长电科技类「长期超买的强势上涨股」：
只要 GMMA 多头排列不破坏，就一路持有。

入场（全部满足）：
- GMMA 多头：EMA15 > EMA30 且短期组均值 > 长期组均值
- 一目均衡看多：价格在云层上方，或（云未形成时）转换线 > 基准线
- ADX >= 20：确认有趋势（拒绝震荡市假信号）
出场（满足其一）：
- GMMA 转空：EMA15 < EMA30（趋势主结构破坏）
- 收盘价跌破基准线 kijun
"""

import pandas as pd

from .base import BaseStrategy
from .registry import register


@register
class DualTrendStrategy(BaseStrategy):
    name = "dual_trend"
    display_name = "双趋势共振 GMMA+一目（强势股）"
    description = (
        "两套独立趋势系统（GMMA 顾比均线 + 一目均衡表）同时看多才入场，"
        "ADX>=20 过滤震荡。完全不看 RSI，专攻长电科技类长期超买的强势上涨股，"
        "建议搭配移动止损、放大止盈让利润奔跑。"
    )
    default_params = {"adx_threshold": 20}

    def generate_signals(self, df: pd.DataFrame) -> list:
        self.validate_df(df)
        d = df.copy()
        # ── GMMA 顾比均线（短期组 3-15 / 长期组 30-60）──
        gmma_s = [3, 5, 8, 10, 12, 15]
        gmma_l = [30, 35, 40, 45, 50, 60]
        for p in gmma_s + gmma_l:
            d[f"ema_{p}"] = d["close"].ewm(span=p, adjust=False).mean()
        d["gmma_s_avg"] = d[[f"ema_{p}" for p in gmma_s]].mean(axis=1)
        d["gmma_l_avg"] = d[[f"ema_{p}" for p in gmma_l]].mean(axis=1)
        d["gmma_bull"] = (d["ema_15"] > d["ema_30"]) & (d["gmma_s_avg"] > d["gmma_l_avg"])

        # ── 一目均衡表 ──
        d["tenkan"] = (d["high"].rolling(9).max() + d["low"].rolling(9).min()) / 2
        d["kijun"] = (d["high"].rolling(26).max() + d["low"].rolling(26).min()) / 2
        d["senkou_a"] = ((d["tenkan"] + d["kijun"]) / 2).shift(26)
        d["senkou_b"] = ((d["high"].rolling(52).max() + d["low"].rolling(52).min()) / 2).shift(26)
        d["cloud_top"] = d[["senkou_a", "senkou_b"]].max(axis=1)
        d["tk_bull"] = d["tenkan"] > d["kijun"]

        # ── ADX 趋势强度 ──
        d["adx"] = self._adx(d)

        signals = []
        in_bull = False
        for i in range(len(d)):
            curr = d.iloc[i]
            # 预热期：GMMA 长期组需要 30 根、一目基准线需要 26 根
            if i < 30 or pd.isna(curr["kijun"]) or pd.isna(curr["adx"]):
                signals.append(0)
                continue

            # 一目看多：云已形成看云，云未形成（短区间）退化为 TK 多头
            if not pd.isna(curr["cloud_top"]):
                ichimoku_bull = curr["close"] > curr["cloud_top"] or (
                    bool(curr["tk_bull"]) and curr["close"] > curr["kijun"])
            else:
                ichimoku_bull = bool(curr["tk_bull"])

            entry = bool(curr["gmma_bull"]) and ichimoku_bull and curr["adx"] >= self.default_params["adx_threshold"]
            exit_ = (not bool(curr["gmma_bull"])) or curr["close"] < curr["kijun"]

            if not in_bull and entry:
                signals.append(1)
                in_bull = True
            elif in_bull and exit_:
                signals.append(-1)
                in_bull = False
            else:
                signals.append(0)
        return signals
