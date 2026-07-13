"""
modules/analysis_engine.py
------------------------
个股深度分析的「纯逻辑」层：不依赖 Streamlit，可被前端页面和后台任务同时调用。

所有耗时操作（行情、新闻、信号）都包在 try/except 中；失败时把提示写入
result["_warnings"] 而不是直接 st.warning，保证在 CLI/后台/Streamlit 三种环境都能跑。
"""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.news import NewsFetcher, SentimentAnalyzer


# 配色常量（与个股分析页对齐：参考文档绿涨红跌）
RED = "#009e60"      # 涨 / 利好 / 买入（文档绿）
GREEN = "#dc2626"    # 跌 / 利空 / 卖出（文档红）
AMBER = "#d97706"    # 中性 / 持有


def _verdict_color(composite: float):
    """根据综合评分返回 (信号文案, 颜色, css_class)。"""
    if composite >= 70:
        return "看多", RED, "win"
    elif composite <= 40:
        return "看空", GREEN, "weak"
    return "持有", AMBER, "mid"


def _calc_trade_levels(current_price: float, df: pd.DataFrame, support: float, resistance: float):
    """基于 ATR 与支撑/压力计算入场/目标/止损价。"""
    if current_price is None or current_price <= 0:
        return current_price, resistance, support, 0.0

    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else current_price * 0.025
    if np.isnan(atr14) or atr14 <= 0:
        atr14 = current_price * 0.025

    stop_atr = current_price - 2.5 * atr14
    stop_max_pct = current_price * 0.92
    if support > 0 and support < current_price and support > stop_max_pct:
        stop_price = support
    else:
        stop_price = max(stop_atr, stop_max_pct)
    stop_price = max(stop_price, current_price * 0.80)

    entry_price = max(current_price - 0.5 * atr14, stop_price * 1.01)
    target_atr = current_price + 3 * atr14
    target_pct_cap = current_price * 1.15
    target_price = min(target_atr, resistance, target_pct_cap)
    target_price = max(target_price, current_price * 1.03)

    return round(entry_price, 2), round(target_price, 2), round(stop_price, 2), round(atr14, 2)


def _board(code: str) -> str:
    """由代码派生板块。"""
    if str(code).startswith("60"):
        return "沪市主板"
    if str(code).startswith("00"):
        return "深市主板"
    if str(code).startswith("30"):
        return "创业板"
    if str(code).startswith("68"):
        return "科创板"
    if str(code).startswith(("8", "4")):
        return "北交所"
    return "A股"


def _sentiment_counts(news_df: pd.DataFrame, sa: SentimentAnalyzer, limit: int = 12) -> Tuple[List[Dict[str, Any]], float, float]:
    """对新闻做情绪分析，返回 (news_rows, pos_pct, neg_pct)。"""
    news_rows: List[Dict[str, Any]] = []
    pos_n = neg_n = neu_n = 0
    if news_df is not None and not news_df.empty:
        for _, row in news_df.head(limit).iterrows():
            title = str(row.get("title", ""))
            sent = sa.analyze_news(title, str(row.get("content", "")))
            lab = sent.get("sentiment", "中性")
            if lab == "正面":
                pos_n += 1
            elif lab == "负面":
                neg_n += 1
            else:
                neu_n += 1
            news_rows.append({
                "date": row.get("date"),
                "title": title,
                "sentiment": lab,
                "score": sent.get("score", 0),
            })
        total_n = max(1, pos_n + neg_n + neu_n)
        return news_rows, pos_n / total_n * 100, neg_n / total_n * 100
    return news_rows, 0.0, 0.0


def run_analysis(ticker: str, fetcher: StockFetcher | None = None) -> Dict[str, Any]:
    """个股深度分析核心逻辑（纯 Python，无 Streamlit）。"""
    if fetcher is None:
        fetcher = StockFetcher()

    messages: List[str] = []
    ticker = str(ticker).strip().zfill(6)

    # 基础信息
    stock_name = fetcher.get_stock_name(ticker) or ticker
    _code, _name = fetcher.get_stock_basic(ticker)
    display_name = _name or stock_name or ticker

    try:
        industry_kws = fetcher.get_stock_keywords(ticker, top_k=3)
        industry = industry_kws.split(",")[0] if industry_kws else "—"
    except Exception as e:
        industry = "—"
        messages.append(f"行业关键词获取失败：{str(e)[:80]}")

    # 实时行情（本地 fetcher 直接拉取，避免后台调用 session.api_quote）
    quote_src = "本地 fetcher"
    rt = None
    try:
        rt = fetcher.get_realtime_quote(ticker)
        quote_src = "新浪财经"
    except Exception as e:
        messages.append(f"实时行情获取失败：{str(e)[:80]}")
    if isinstance(rt, dict) and rt.get("current"):
        current_price = float(rt["current"])
        prev_close = float(rt.get("prev_close") or current_price)
        change_pct = (current_price - prev_close) / prev_close * 100 if prev_close else 0.0
    else:
        rt = None
        current_price = None
        prev_close = None
        change_pct = 0.0

    # 日线行情（本地 fetcher 直接拉取）
    today = datetime.now().date()
    start_str = (today - timedelta(days=365)).strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")
    data_src = "本地四级降级链"
    try:
        df = fetcher.get_daily(ticker, start=start_str, end=end_str)
    except Exception as e:
        messages.append(f"行情获取失败：{str(e)[:80]}")
        df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = DataCleaner.full_pipeline(df)

    # 技术面
    technical = technical_full_analysis(df)
    trend = technical.get("trend", {})
    momentum = technical.get("momentum", {})
    volume_info = technical.get("volume", {})
    patterns = technical.get("patterns", []) or []

    # 信号引擎
    keywords = [k.strip() for k in (industry_kws or "").split(",") if k.strip()] or [display_name]
    signal = SignalEngine().evaluate(ticker, keywords, date=None)

    tech_score = float(signal.get("price_score", 50))
    news_score = float(signal.get("event_score", 50))
    macro_score = float(signal.get("macro_score", 50))
    vol_score = float(volume_info.get("volume_price_score", 50)) if "error" not in volume_info else 50.0

    composite = int(round(tech_score * 0.30 + news_score * 0.25 + vol_score * 0.25 + macro_score * 0.20))
    composite = max(0, min(100, composite))
    verdict, verdict_color, verdict_cls = _verdict_color(composite)

    # 新闻 / 情绪
    try:
        news_df = NewsFetcher().fetch(keyword=display_name, source="auto", limit=50)
    except Exception as e:
        messages.append(f"新闻抓取失败：{str(e)[:80]}")
        news_df = pd.DataFrame(columns=["date", "title", "content", "source", "url"])

    sa = SentimentAnalyzer()
    news_rows, pos_pct, neg_pct = _sentiment_counts(news_df, sa)

    # 支撑 / 压力
    recent = df.tail(60)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    if current_price is None:
        current_price = float(df.iloc[-1]["close"])
    entry_price, target_price, stop_price, atr14 = _calc_trade_levels(current_price, df, support, resistance)

    last = df.iloc[-1]
    ma20 = float(last.get("ma20", last["close"])) if "ma20" in df.columns else float(last["close"])
    deviation = (last["close"] - ma20) / ma20 * 100 if ma20 else 0.0

    lo52 = float(df["low"].min())
    hi52 = float(df["high"].max())
    pos52 = (last["close"] - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else 50.0

    ma5v = float(df["close"].rolling(5).mean().iloc[-1]) if len(df) >= 5 else float(last["close"])
    ma10v = float(df["close"].rolling(10).mean().iloc[-1]) if len(df) >= 10 else float(last["close"])
    ma20v = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else float(last["close"])
    trapped = float(df["high"].tail(120).max()) if len(df) >= 20 else float(hi52)

    vol_now = float(df["volume"].iloc[-1])
    vol_prev = float(df["volume"].iloc[-2]) if len(df) >= 2 else vol_now
    vol_avg = float(df["volume"].tail(20).mean())
    vol_chg = (vol_now - vol_prev) / vol_prev * 100 if vol_prev else 0.0

    q_open = float(rt["open"]) if isinstance(rt, dict) and rt.get("open") else None
    q_high = float(rt["high"]) if isinstance(rt, dict) and rt.get("high") else None
    q_low = float(rt["low"]) if isinstance(rt, dict) and rt.get("low") else None
    q_prev = float(rt["prev_close"]) if isinstance(rt, dict) and rt.get("prev_close") else None
    q_amount = float(rt["amount"]) if isinstance(rt, dict) and rt.get("amount") else None

    board = _board(ticker)

    if verdict == "看多":
        position_advice = (
            f"分批低吸，建议首仓在现价附近，回踩 ¥{entry_price:.2f} 补第二笔；"
            f"目标 ¥{target_price:.2f} 分批兑现，止损 ¥{stop_price:.2f}"
        )
    elif verdict == "看空":
        position_advice = (
            f"轻仓观望，等待企稳；若已持仓建议逢高减仓，"
            f"反弹目标 ¥{target_price:.2f} 附近减仓，止损 ¥{stop_price:.2f}"
        )
    else:
        position_advice = (
            f"区间波段，半仓操作；回踩 ¥{entry_price:.2f} 可低吸，"
            f"目标 ¥{target_price:.2f} 分批兑现，跌破止损 ¥{stop_price:.2f} 纪律离场"
        )

    return {
        "ticker": ticker,
        "display_name": display_name,
        "industry": industry,
        "current_price": current_price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "df": df,
        "technical": technical,
        "trend": trend,
        "momentum": momentum,
        "volume_info": volume_info,
        "patterns": patterns,
        "signal": signal,
        "tech_score": tech_score,
        "news_score": news_score,
        "macro_score": macro_score,
        "vol_score": vol_score,
        "composite": composite,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "verdict_cls": verdict_cls,
        "news_rows": news_rows,
        "pos_pct": pos_pct,
        "neg_pct": neg_pct,
        "support": support,
        "resistance": resistance,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_price": stop_price,
        "atr14": atr14,
        "deviation": deviation,
        "lo52": lo52,
        "hi52": hi52,
        "pos52": pos52,
        "ma5v": ma5v,
        "ma10v": ma10v,
        "ma20v": ma20v,
        "trapped": trapped,
        "vol_now": vol_now,
        "vol_prev": vol_prev,
        "vol_avg": vol_avg,
        "vol_chg": vol_chg,
        "q_open": q_open,
        "q_high": q_high,
        "q_low": q_low,
        "q_prev": q_prev,
        "q_amount": q_amount,
        "board": board,
        "position_advice": position_advice,
        "data_src": data_src,
        "quote_src": quote_src,
        "_warnings": messages,
    }
