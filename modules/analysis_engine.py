"""
modules/analysis_engine.py
------------------------
个股深度分析的「纯逻辑」层：不依赖 Streamlit，可被前端页面和后台任务同时调用。

所有耗时操作（行情、新闻、信号）都包在 try/except 中；失败时把提示写入
result["_warnings"] 而不是直接 st.warning，保证在 CLI/后台/Streamlit 三种环境都能跑。
"""
from __future__ import annotations

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

# 分析结果 TTL 缓存：避免重复抓取行情/新闻，显著提速（默认 90 秒）
import time as _time
_ANALYSIS_CACHE: Dict[str, Any] = {}
_ANALYSIS_TTL = 90.0


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


def _sector_analysis(industry_kws: str, fetcher: StockFetcher) -> Dict[str, Any]:
    """判断个股主板块及走势，供「板块分析」模块。

    返回 {name, change_pct, label, rank, total}：
      - name   主板块名（取行业关键词第一项）
      - change_pct 该板块实时涨跌幅（%）
      - label  领涨/走强/走弱/领跌
      - rank/total 该板块在全市场板块中的涨幅排名
    网络不可用时返回基础占位，不抛异常。
    """
    def _clean_industry(name: str) -> str:
        """清理东方财富行业名中的罗马数字后缀，使其与板块名对齐。"""
        if not name:
            return name
        # 去掉 Ⅱ、Ⅲ、Ⅰ 等后缀，以及"及其他"
        for suffix in ["Ⅲ", "Ⅱ", "Ⅰ", "及其他"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        return name.strip()

    kws = [k.strip() for k in (industry_kws or "").split(",") if k.strip()]
    industry = _clean_industry(kws[0]) if kws else ""
    out: Dict[str, Any] = {
        "name": industry or "—", "change_pct": None,
        "label": "—", "rank": None, "total": None,
    }
    if not kws:
        return out
    try:
        sectors = fetcher.get_sector_list()
        if sectors is None or (hasattr(sectors, "empty") and sectors.empty):
            return out
        name_col = "sector" if "sector" in sectors.columns else sectors.columns[0]
        chg_col = next((c for c in sectors.columns if "change" in c.lower()), None)
        if chg_col is None:
            return out

        # 1) 精确匹配（清理后）
        cleaned = sectors[name_col].astype(str).apply(_clean_industry)
        sec = sectors[cleaned == industry]
        # 2) 包含匹配
        if sec.empty:
            sec = sectors[sectors[name_col].astype(str).str.contains(industry, na=False, regex=False)]
        # 3) 关键词任一包含
        if sec.empty:
            sec = sectors[sectors[name_col].astype(str).str.contains("|".join(kws), na=False, regex=True)]
        if sec.empty:
            sec = sectors[sectors[name_col].astype(str).apply(
                lambda x: any(k in x for k in kws))]
        if sec.empty:
            return out

        chg = float(sec.iloc[0][chg_col])
        out["change_pct"] = chg
        out["label"] = ("领涨" if chg >= 1.5 else "走强" if chg >= 0
                        else "走弱" if chg > -1.5 else "领跌")
        ranked = sectors.sort_values(chg_col, ascending=False).reset_index(drop=True)
        sector_full_name = str(sec.iloc[0][name_col])
        # 排名按清理后的名或全名匹配
        idx = ranked[cleaned == _clean_industry(sector_full_name)].index
        if len(idx) == 0:
            idx = ranked[ranked[name_col].astype(str).str.contains(industry, na=False)].index
        if len(idx):
            out["rank"] = int(idx[0]) + 1
            out["total"] = len(ranked)
    except Exception:
        pass
    return out


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


def run_analysis(ticker: str, fetcher: StockFetcher | None = None, _use_cache: bool = True) -> Dict[str, Any]:
    """个股深度分析核心逻辑（纯 Python，无 Streamlit）。"""
    ticker = str(ticker).strip().zfill(6)
    # TTL 缓存：同一 ticker 90 秒内直接返回，避免重复抓取（提速关键）
    if _use_cache:
        _hit = _ANALYSIS_CACHE.get(ticker)
        if _hit is not None and (_time.time() - _hit[0]) < _ANALYSIS_TTL:
            return _hit[1]

    if fetcher is None:
        fetcher = StockFetcher()

    messages: List[str] = []
    ticker = str(ticker).strip().zfill(6)

    # 基础信息
    stock_name = fetcher.get_stock_name(ticker) or ticker
    _code, _name = fetcher.get_stock_basic(ticker)
    display_name = _name or stock_name or ticker

    # 真实行业（优先基本面接口，比名称关键词更准）
    industry = "—"
    fundamentals = {}
    try:
        fundamentals = fetcher.get_fundamentals(ticker)
        industry = (fundamentals.get("industry") or "").strip() or "—"
    except Exception as e:
        messages.append(f"基本面获取失败：{str(e)[:80]}")

    # 与板块列表对齐的清理后行业名（去掉"Ⅱ"/"Ⅲ"/"Ⅰ"/"及其他"）
    def _clean_industry_name(name: str) -> str:
        if not name:
            return name
        for suffix in ["Ⅲ", "Ⅱ", "Ⅰ", "及其他"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        return name.strip()

    industry_for_sector = _clean_industry_name(industry) if industry != "—" else ""

    # 行业事件关键词（用于事件库/新闻匹配）
    try:
        industry_kws = fetcher.get_stock_keywords(ticker, top_k=3)
    except Exception as e:
        industry_kws = ""
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
    signal = SignalEngine().evaluate(
        ticker, keywords, date=None,
        sector_name=(industry_for_sector if industry_for_sector else None)
    )

    tech_score = float(signal.get("price_score", 50))
    news_score = float(signal.get("event_score", 50))
    macro_score = float(signal.get("macro_score", 50))
    vol_score = float(volume_info.get("volume_price_score", 50)) if "error" not in volume_info else 50.0

    sector_score = float(signal.get("sector_score", 55))
    tech_profile = signal.get("technical_profile",
                                {"short": 50, "mid": 50, "long": 50, "trend": 50, "composite": 50})
    # 五维加权：技术0.25 / 情绪0.22 / 量能0.18 / 宏观0.15 / 板块0.20
    composite = int(round(
        tech_score * 0.25 + news_score * 0.22 + vol_score * 0.18
        + macro_score * 0.15 + sector_score * 0.20
    ))
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

    # 支撑 / 压力（重写：不再用 60 日绝对最低/最高，而是真实可交易区间）
    if current_price is None:
        current_price = float(df.iloc[-1]["close"])
    recent20 = df.tail(20)
    recent60 = df.tail(60)
    swing_low_20 = float(recent20["low"].min())
    swing_high_20 = float(recent20["high"].max())
    # ATR（真实波动率）
    _hi = df["high"]; _lo = df["low"]; _cl = df["close"]
    _tr = pd.concat([
        (_hi - _lo),
        (_hi - _cl.shift(1)).abs(),
        (_lo - _cl.shift(1)).abs(),
    ], axis=1).max(axis=1)
    _atr = float(_tr.rolling(14).mean().iloc[-1]) if len(_tr) >= 14 else current_price * 0.025
    if np.isnan(_atr) or _atr <= 0:
        _atr = current_price * 0.025
    # 关键均线（仅取低于现价的，作为支撑参考）
    _ma20v = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else current_price
    _ma60v = float(df["close"].rolling(60).mean().iloc[-1]) if len(df) >= 60 else current_price
    _sup_cands = [swing_low_20, current_price - 1.2 * _atr]
    if _ma20v < current_price:
        _sup_cands.append(_ma20v)
    if _ma60v < current_price:
        _sup_cands.append(_ma60v)
    support = max(_sup_cands)
    support = min(support, current_price * 0.98)  # 安全护栏：支撑必须低于现价
    # 压力：近期摆动高点 / ATR 上沿 / 60 日高点（取最高者，且不低于现价 2%）
    _res_cands = [swing_high_20, current_price + 1.2 * _atr, float(recent60["high"].max())]
    resistance = max(_res_cands)
    resistance = max(resistance, current_price * 1.02)
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
    # 板块分析：主板块 + 实时走势 + 全市场排名（用真实行业名匹配）
    sector_analysis = _sector_analysis(industry_for_sector if industry_for_sector else industry_kws, fetcher)

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

    result = {
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
        "sector_score": sector_score,
        "sector_analysis": sector_analysis,
        "technical_profile": tech_profile,
        "position_advice": position_advice,
        "data_src": data_src,
        "quote_src": quote_src,
        "_warnings": messages,
    }
    if _use_cache:
        _ANALYSIS_CACHE[ticker] = (_time.time(), result)
    return result
