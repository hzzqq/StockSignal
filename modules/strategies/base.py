"""策略抽象基类 + 共享技术指标工具。

所有策略类都继承 BaseStrategy，实现 generate_signals(df)。
把 ADX / RSI 等工具方法放这里，保证策略类能脱离 Backtester 独立运行、
可被 pickle 跨进程传输（批量回测用 ProcessPoolExecutor 时需要）。
"""

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class BaseStrategy(ABC):
    """回测策略抽象基类。

    子类必须定义：
    - name: 机器名（英文，唯一，用于 registry key 与页面 value）
    - display_name: 中文展示名（页面 label）
    - description: 策略说明（方法论 expander 用）
    - generate_signals(self, df) -> list[int]: 返回与 df 等长的信号序列
    - default_params: dict，策略默认参数（供参数扫描 UI 读取）

    信号约定：1=买入, -1=卖出, 0=持有。
    """

    #: DataFrame 必须包含的标准列（generate_signals 可依赖的最小集合）
    DF_COLUMNS = (
        "date", "open", "high", "low", "close", "volume",
        "rsi14", "rsi2", "atr14", "atr_ratio",
        "ma20", "ma60", "bb_upper", "bb_lower", "vol_ma20",
    )

    name: str = ""
    display_name: str = ""
    description: str = ""
    default_params: dict = {}
    #: 是否需要 Backtester 上下文（signal_engine / ticker / keywords 等）
    needs_context: bool = False

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> list:
        """根据已含技术指标的 df 生成信号序列。

        不需要外部上下文的策略（多数）只实现这个。
        """
        raise NotImplementedError

    def generate_signals_with_context(self, df: pd.DataFrame, ctx: dict) -> list:
        """需要 Backtester 上下文的策略（如事件驱动）实现这个。

        :param ctx: {"signal_engine":..., "ticker":..., "keywords":[...]}
        """
        # 默认降级为无上下文版本（needs_context=False 的策略用不到）
        return self.generate_signals(df)

    # ------------------------------------------------------------------
    # 共享技术指标工具（静态，便于独立使用与 pickle）
    # ------------------------------------------------------------------
    @staticmethod
    def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
        if series is None or len(series) < 2:
            return pd.Series(dtype=float)
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
        if df is None or df.empty or not all(c in df.columns for c in ("high", "low", "close")):
            return pd.Series(dtype=float)
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=window).mean()

    @staticmethod
    def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Wilder ADX：衡量趋势强度（>20 有趋势，>40 强趋势）。"""
        if df is None or df.empty or not all(c in df.columns for c in ("high", "low", "close")):
            return pd.Series(dtype=float)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / period).mean()

        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()
        plus_dm = plus_dm.where(plus_dm > 0, 0.0)
        minus_dm = minus_dm.where(minus_dm > 0, 0.0)
        cond = plus_dm > minus_dm
        plus_dm = plus_dm.where(cond, 0.0)
        minus_dm = minus_dm.where(~cond, 0.0)

        plus_di = 100 * (plus_dm.ewm(alpha=1 / period).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1 / period).mean() / atr)
        denom = (plus_di + minus_di).replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / denom
        return dx.ewm(alpha=1 / period).mean()

    def validate_df(self, df: pd.DataFrame) -> None:
        """校验 df 含必要列，缺失则抛清晰错误（便于用户自写策略时快速定位）。"""
        missing = [c for c in self.DF_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"策略[{self.name}] 需要列 {missing}，但 df 缺失。"
                f"请先用 Backtester 的 _add_indicators 处理数据。"
            )
