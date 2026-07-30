"""
股票技术指标计算库（移植自 stock-selecter skill 的 stock_indicators.py）
纯 pandas/numpy 实现，无任何外部 API 依赖，供智能选股模块复用。
函数：calculate_macd / calculate_rsi / calculate_bollinger_bands /
analyze_trend / detect_bottom_divergence / check_volume_surge /
calculate_financial_ratios / calculate_growth_rates
"""

import logging
import pandas as pd
import numpy as np
from typing import Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)


def calculate_macd(close_prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[pd.Series], Optional[pd.Series], Optional[pd.Series]]:
    if close_prices is None:
        return None, None, None
    if len(close_prices) < slow:
        return None, None, None
    try:
        exp1 = close_prices.ewm(span=fast).mean()
        exp2 = close_prices.ewm(span=slow).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=signal).mean()
        macd_hist = macd_line - signal_line
        return macd_line, signal_line, macd_hist
    except Exception as e:
        logger.warning(f"MACD计算错误: {e}")
        return None, None, None


def calculate_sma(data: pd.Series, window: int) -> Optional[pd.Series]:
    if data is None:
        return None
    if len(data) < window:
        return None
    try:
        return data.rolling(window=window).mean()
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return None


def calculate_ema(data: pd.Series, window: int) -> Optional[pd.Series]:
    if data is None:
        return None
    if len(data) < window:
        return None
    try:
        return data.ewm(span=window).mean()
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return None


def analyze_trend(data: pd.Series, min_points: int = 10) -> Tuple[Optional[float], Optional[float]]:
    if data is None:
        return None, None
    if len(data) < min_points:
        return None, None
    try:
        x = np.arange(len(data))
        y = np.array(data)
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        return slope, r_squared
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return None, None


def detect_bottom_divergence(close_prices: pd.Series, macd_hist: pd.Series,
                             lookback: int = 12, price_threshold: float = 1.02) -> bool:
    if close_prices is None or macd_hist is None:
        return False
    if len(close_prices) < lookback or len(macd_hist) < lookback:
        return False
    try:
        recent_close = close_prices.iloc[-lookback:]
        recent_hist = macd_hist.iloc[-lookback:]
        min_price_idx = recent_close.idxmin()
        price_trough_pos = list(recent_close.index).index(min_price_idx)
        if (lookback - 1 - price_trough_pos) > lookback // 4:
            return False
        last_price = close_prices.iloc[-1]
        min_price = recent_close.min()
        if last_price > min_price * price_threshold:
            return False
        min_hist = recent_hist.min()
        hist_at_trough = recent_hist.iloc[price_trough_pos]
        if min_hist < 0:
            return bool(hist_at_trough > min_hist * 0.5)
        return False
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return False


def detect_top_divergence(close_prices: pd.Series, macd_hist: pd.Series,
                          lookback: int = 12, price_threshold: float = 0.98) -> bool:
    if close_prices is None or macd_hist is None:
        return False
    if len(close_prices) < lookback or len(macd_hist) < lookback:
        return False
    try:
        recent_close = close_prices.iloc[-lookback:]
        recent_hist = macd_hist.iloc[-lookback:]
        max_price_idx = recent_close.idxmax()
        price_peak_pos = list(recent_close.index).index(max_price_idx)
        if (lookback - 1 - price_peak_pos) > lookback // 4:
            return False
        last_price = close_prices.iloc[-1]
        max_price = recent_close.max()
        if last_price < max_price * price_threshold:
            return False
        max_hist = recent_hist.max()
        hist_at_peak = recent_hist.iloc[price_peak_pos]
        if max_hist > 0:
            return bool(hist_at_peak < max_hist * 0.5)
        return False
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return False


def check_volume_surge(volume: pd.Series, weeks: int = 5, threshold: float = 1.5) -> Tuple[bool, Optional[float]]:
    if volume is None:
        return False, None
    if len(volume) < weeks + 2:
        return False, None
    try:
        recent_vol = volume.iloc[-1]
        avg_vol = volume.iloc[-weeks - 1:-1].mean()
        if avg_vol <= 0:
            return False, None
        ratio = recent_vol / avg_vol
        return bool(ratio > threshold), round(ratio, 2)
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return False, None


def calculate_rsi(close_prices: pd.Series, window: int = 14) -> Optional[pd.Series]:
    if close_prices is None:
        return None
    if len(close_prices) < window + 1:
        return None
    try:
        delta = close_prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=window).mean()
        avg_loss = loss.rolling(window=window).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return None


def calculate_bollinger_bands(close_prices: pd.Series, window: int = 20, num_std: int = 2) -> Tuple[Optional[pd.Series], Optional[pd.Series], Optional[pd.Series]]:
    if close_prices is None:
        return None, None, None
    if len(close_prices) < window:
        return None, None, None
    try:
        middle_band = close_prices.rolling(window=window).mean()
        std = close_prices.rolling(window=window).std()
        upper_band = middle_band + (std * num_std)
        lower_band = middle_band - (std * num_std)
        return upper_band, middle_band, lower_band
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return None, None, None


def calculate_financial_ratios(fina_df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """从已归一化为英文列名的财务指标 DataFrame 计算常用财务比率。"""
    if fina_df is None or fina_df.empty:
        return {}
    try:
        latest = fina_df.iloc[0]
        roe = float(latest["roe"]) if latest.get("roe") and latest["roe"] else None
        roa = float(latest["roa"]) if latest.get("roa") and latest["roa"] else None
        gross_margin = float(latest["grossprofit_margin"]) if latest.get("grossprofit_margin") and latest["grossprofit_margin"] else None
        net_margin = float(latest["netprofit_margin"]) if latest.get("netprofit_margin") and latest["netprofit_margin"] else None
        debt_ratio = float(latest["debt_ratio"]) if latest.get("debt_ratio") and latest["debt_ratio"] else None
        current_ratio = float(latest["current_ratio"]) if latest.get("current_ratio") and latest["current_ratio"] else None
        return {
            "roe": roe, "roa": roa,
            "gross_profit_margin": gross_margin,
            "net_profit_margin": net_margin,
            "debt_ratio": debt_ratio, "current_ratio": current_ratio,
            "end_date": latest.get("end_date"),
            "ts_code": latest.get("ts_code"),
        }
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return {}


def calculate_growth_rates(income_df: pd.DataFrame, periods: int = 4) -> Dict[str, Optional[float]]:
    if income_df is None or len(income_df) < 2:
        return {}
    try:
        df = income_df.head(periods).copy()
        revenue_growth = None
        profit_growth = None
        if len(df) >= 4 and "total_revenue" in df.columns:
            current = pd.to_numeric(df.iloc[0].get("total_revenue"), errors='coerce')
            previous = pd.to_numeric(df.iloc[3].get("total_revenue"), errors='coerce')
            if current > 0 and previous > 0:
                revenue_growth = (current - previous) / previous * 100
        if len(df) >= 4 and "netprofit" in df.columns:
            current = pd.to_numeric(df.iloc[0].get("netprofit"), errors='coerce')
            previous = pd.to_numeric(df.iloc[3].get("netprofit"), errors='coerce')
            if current > 0 and previous > 0:
                profit_growth = (current - previous) / previous * 100
        return {"revenue_growth_yoy": revenue_growth, "profit_growth_yoy": profit_growth}
    except Exception as e:
        logger.warning(f"[screener_indicators] 处理异常: {e}")
        return {}