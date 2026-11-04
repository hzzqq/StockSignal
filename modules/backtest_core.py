"""modules/backtest_core.py —— Plan A split：纯函数 + 静态指标。

从 backtest.py 提取：
- RSI_EXCLUDE_THRESHOLD（选股排除阈值常量）
- 6 个顶层 helper（_clamp100 / _final_picker_score / _trend_persistence_ratio /
  _rsi14_health_score / _rsi14_overbought）
- 5 个技术指标静态方法（_rsi / _atr / _macd / _bollinger / _adx）

原始 AST 精确切分，零业务逻辑修改。
"""

import numpy as np
import pandas as pd

import logging

logger = logging.getLogger(__name__)


RSI_EXCLUDE_THRESHOLD = 92


def _clamp100(v: float) -> float:
    """把任意评分收束到 [0,100]。

    多因子分段上限（趋势50+超跌40+健康20+量能15）合计 125，历史债导致
    原始评分可溢出到 ~125，违反「0-100 评分契约」（UI 进度条/配色/排序均按 0-100
    假设）。统一在此封顶，避免「评分 125/100」这类展示与排序失真。
    """
    try:
        return max(0.0, min(100.0, float(v)))
    except (TypeError, ValueError):
        return 50.0


def _final_picker_score(score: float, smoothed: float, enough_days: bool) -> float:
    """混合当前详细评分与多日平滑评分，归一到 [0,100]。

    :param enough_days: 是否已有 >=3 天日评分用于加权平均（否则只用当前详细评分）。
    """
    raw = (score * 0.7 + smoothed * 0.3) if enough_days else score
    return round(_clamp100(raw), 1)


def _trend_persistence_ratio(recent):
    """最近窗口内 close>MA20 的占比（∈[0,1]）。

    锐评 R5：原代码用 min(len(recent),5) 作分母，但 recent 实为最近 10 天，
    导致占比被放大 2 倍、区间 [0,2]，把仅一半交易日站上 MA20 的股票误标为
    '强趋势(持续)'。改为除以窗口实际长度，与 daily_picker_backtest 同源一致。
    """
    if recent is None or len(recent) == 0:
        return 0.0
    above = int((recent["close"] > recent["ma20"]).sum())
    return above / len(recent)


def _rsi14_health_score(rsi14):
    """RSI14 健康分（两条选股打分路径统一调用的单一真理源）。

    锐评 R6：原 _score_for_picker 与 daily_picker_backtest 各自写一套 RSI14 分档，
    且超买阈值不一致（75 vs 80），导致同一 RSI14 在两路径给不同分（如 75→主10/批0），
    批量选股回测与单股诊断结论自相矛盾。统一到此函数后分支无法再漂移。
    """
    try:
        r = float(rsi14)
    except (TypeError, ValueError):
        return 0  # ui_audit_exempt(T-239R2): except 内优雅降级哨兵-已审
    if 40 <= r <= 60:
        return 20
    elif 30 <= r < 40:
        return 15
    elif 60 < r <= 70:
        return 12
    elif 70 < r <= 92:
        return 10
    elif 25 <= r < 30:
        return 8
    return 0


def _rsi14_overbought(recent):
    """最近窗口内 RSI14>75 的交易日数（与主路径一致，阈值 75）。"""
    if recent is None or len(recent) == 0:
        return 0
    return int((recent["rsi14"] > 75).sum())


def _rsi(series, window=14):
    if series is None or len(series) < 2:
        return pd.Series(dtype=float)
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _atr(df, window=14):
    if df is None or df.empty or not all(c in df.columns for c in ("high", "low", "close")):
        return pd.Series(dtype=float)
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=window).mean()


def _macd(df):
    if df is None or df.empty or "close" not in df.columns:
        empty = pd.Series(dtype=float)
        return empty, empty, empty
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def _bollinger(df, window=20, std=2):
    if df is None or df.empty or "close" not in df.columns:
        empty = pd.Series(dtype=float)
        return empty, empty, empty
    ma = df["close"].rolling(window=window).mean()
    std_dev = df["close"].rolling(window=window).std()
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    return upper, lower, ma


def _adx(df, period=14):
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


# 导出清单
__all__ = [
    "RSI_EXCLUDE_THRESHOLD",
    "_clamp100", "_final_picker_score", "_trend_persistence_ratio",
    "_rsi14_health_score", "_rsi14_overbought",
    "_rsi", "_atr", "_macd", "_bollinger", "_adx",
    "np", "pd", "logger", "logging",
]
