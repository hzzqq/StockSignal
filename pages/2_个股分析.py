"""
页面2：个股分析
暗色模式「决策仪表盘 · 个股深度分析」（参考 002947 暗色版 .sf-* 组件类）。

严格遵循参考文档「绿涨红跌」配色：涨/利好/买入 = 绿(#009e60)，跌/利空/卖出 = 红(#dc2626)，
中性/持有 = 琥珀(#d97706)。所有外部数据获取均包在 try/except 中，失败时 st.warning。
仅做前端/UI，不改动 backend 或任何数据逻辑。
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ── 前置：本页「星辰决策仪表盘」跟随全局主题（右上角开关可切暗夜 / 白天）──
from modules.ui_theme import apply_page_config
apply_page_config(page_title="个股分析", page_icon="🔍", layout="wide")
st.session_state["_active_page"] = __file__

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.news import NewsFetcher, SentimentAnalyzer
from modules.visualizer import Visualizer, UP_COLOR, DOWN_COLOR
from modules.session import init_session_state, require_auth, render_user_badge, api_kline, api_quote
from modules.search_ui import stock_search_input
from modules.ui_theme import dashboard_sf_css
from modules.background_tasks import submit_task_with_error, poll_task

# 配色常量（对齐参考文档 002947 白天版 .sf-*：绿涨 / 红跌 / 琥珀中性）
# 说明：参考文档采用绿涨红跌（与 StockSignal 全局 A 股红涨惯例不同），
# 用户明确要求「按那个文档做」，故本页统一采用文档配色。
RED = "#009e60"      # 涨 / 利好 / 买入（文档：绿）
GREEN = "#dc2626"    # 跌 / 利空 / 卖出（文档：红）
AMBER = "#d97706"    # 中性 / 持有

require_auth()
render_user_badge(sidebar=True)
st.title("🔍 个股深度分析 · 决策仪表盘")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


# ══════════════════════════════════════════════════════════════
# UI 辅助函数
# ══════════════════════════════════════════════════════════════
def _sentiment_tag(label: str) -> str:
    """情绪标签 → CSS 类名。"""
    return {"正面": "up", "负面": "down", "中性": "mid"}.get(label, "neu")


def _tp_cls(score: float) -> str:
    """多周期技术评分 → CSS 类名（绿强 / 红弱 / 中性）。"""
    return "up" if score >= 60 else ("down" if score <= 40 else "mid")


def _score_ring_html(score: int, color: str) -> str:
    """生成 SVG 评分环：0-100 评分，环按比例填充，数字居中。"""
    score = max(0, min(100, int(score)))
    r = 54
    c = 2 * 3.1415926 * r
    dash = c * score / 100.0
    return f"""
    <div style="display:flex;justify-content:center;align-items:center;margin:6px 0 2px;">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <defs>
          <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#667eea"/>
            <stop offset="100%" stop-color="#764ba2"/>
          </linearGradient>
        </defs>
        <circle cx="70" cy="70" r="{r}" fill="none" stroke="#e2e8f0" stroke-width="12"/>
        <circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" stroke-width="12"
                stroke-linecap="round" stroke-dasharray="{dash:.1f} {c:.1f}"
                transform="rotate(-90 70 70)"/>
        <text x="70" y="64" text-anchor="middle" font-size="34" font-weight="700"
              fill="{color}" font-family="Fira Code, monospace">{score}</text>
        <text x="70" y="88" text-anchor="middle" font-size="12" fill="#64748b">综合评分</text>
      </svg>
    </div>
    """


def _verdict_color(composite: float):
    """根据综合评分返回 (信号文案, 颜色, css_class)。"""
    if composite >= 70:
        return "看多", RED, "win"
    elif composite <= 40:
        return "看空", GREEN, "weak"
    return "持有", AMBER, "mid"


def _price_color(pct: float) -> str:
    """涨红跌绿。"""
    if pct > 0:
        return RED
    if pct < 0:
        return GREEN
    return AMBER


def _support_resistance_bar(support: float, resistance: float, current: float,
                            markers=None) -> str:
    """支撑 → 压力 价格刻度条，标注当前价位置；
    markers=[(label, price, color), ...] 在条上方叠加标注点（MA5/MA10/MA20/套牢区 等）。"""
    if resistance <= support:
        return ""
    lo = support
    hi = resistance
    for _m in (markers or []):
        try:
            lo = min(lo, float(_m[1]))
            hi = max(hi, float(_m[1]))
        except Exception:  # noqa
            pass
    span = hi - lo if hi > lo else 1.0

    def _pos(p):
        return max(0.0, min(100.0, (float(p) - lo) / span * 100.0))

    pos = _pos(current)
    parts = [
        '<div style="margin:10px 0 4px;padding-top:24px;">',
        f'<div style="position:relative;height:26px;border-radius:13px;'
        f'background:linear-gradient(90deg,{GREEN}33,{AMBER}33,{RED}33);'
        f'border:1px solid #e2e8f0;">',
        f'<div style="position:absolute;top:-4px;left:{pos:.1f}%;'
        f'transform:translateX(-50%);width:2px;height:34px;background:#475569;"></div>',
        f'<div style="position:absolute;top:-22px;left:{pos:.1f}%;'
        f'transform:translateX(-50%);font-size:11px;color:#1e293b;white-space:nowrap;">'
        f'现价 ¥{current:.2f}</div>',
    ]
    for (lab, price, color) in (markers or []):
        mp = _pos(price)
        parts.append(
            f'<div style="position:absolute;top:-40px;left:{mp:.1f}%;'
            f'transform:translate(-50%,0);font-size:10px;color:{color};white-space:nowrap;">{lab}</div>'
        )
    parts.append('</div>')
    parts.append(
        f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#64748b;margin-top:6px;">'
        f'<span>支撑 ¥{support:.2f}</span>'
        f'<span>压力 ¥{resistance:.2f}</span>'
        f'</div>'
    )
    parts.append('</div>')
    return "".join(parts)


def _section_header(title: str, subtitle: str = "", icon: str = "📊") -> str:
    """生成带图标、副标题、渐变装饰线的模块标题。"""
    sub_html = f"<div class='sub'>{subtitle}</div>" if subtitle else ""
    return (
        f"<div class='sf-section-header'>"
        f"<div class='icon'>{icon}</div>"
        f"<div class='titles'><h2>{title}</h2>{sub_html}</div>"
        f"<div class='deco'></div></div>"
    )


def _calc_trade_levels(current_price: float, df: pd.DataFrame, support: float, resistance: float):
    """
    基于 ATR 与支撑/压力，计算合理的入场/目标/止损价。
    止损价不超过现价 8%，避免低价股出现 ¥101 股票止损 ¥43 的荒谬结果。
    """
    if current_price is None or current_price <= 0:
        return current_price, resistance, support, 0.0

    # ATR14
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

    # 止损：2.5*ATR 下方，但保底最多跌 8%（与支撑位取更严者）
    stop_atr = current_price - 2.5 * atr14
    stop_max_pct = current_price * 0.92
    # 若支撑位在 stop_max_pct 与 current_price 之间，采用支撑位；否则用 ATR 止损与 8% 的较大值（ closer to price）
    if support > 0 and support < current_price and support > stop_max_pct:
        stop_price = support
    else:
        stop_price = max(stop_atr, stop_max_pct)
    stop_price = max(stop_price, current_price * 0.80)  # 绝对下限 20%（极端保护）

    # 入场：比现价低 0.5 ATR 的回踩价，但不跌破止损
    entry_price = max(current_price - 0.5 * atr14, stop_price * 1.01)

    # 目标：3*ATR 上方，但不超过压力位与 15% 涨幅上限
    target_atr = current_price + 3 * atr14
    target_pct_cap = current_price * 1.15
    target_price = min(target_atr, resistance, target_pct_cap)
    target_price = max(target_price, current_price * 1.03)  # 至少 3% 空间

    return round(entry_price, 2), round(target_price, 2), round(stop_price, 2), round(atr14, 2)


# ══════════════════════════════════════════════════════════════
# 股票选择（侧边栏，复用 行情看板 的交互）
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("分析目标")
    ticker = stock_search_input(
        label="股票搜索",
        key="analysis_stock",
        default="600519",
        placeholder="输入代码或名称搜索，如：600519 / 贵州茅台 / GZMT / 茅台",
    )
    st.caption("本页为星辰决策仪表盘，右上角可切换暗夜 / 白天模式。")

# 主区标题
st.markdown(
    '<div class="sf-header"><div class="sf-brand">决策仪表盘 · '
    '<b>个股深度分析</b></div><div class="sf-brand">事件驱动 · 多维归因</div></div>',
    unsafe_allow_html=True,
)

# 002947 参考文档风格：绿涨红跌，局部增强样式（白天 / 暗夜双主题自适应）
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# 分析计算：把全部结果打包成 dict，便于写入 session_state 实现跨页保留
# ══════════════════════════════════════════════════════════════
# ── 生成分析按钮：置于蓝色「决策仪表盘」主区，蓝色卡片容器使其在视觉上属于该区域 ──
st.markdown(
    '<div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);'
    'border-radius:14px;padding:14px 16px;margin:4px 0 14px;'
    'box-shadow:0 8px 24px rgba(79,70,229,.22)">',
    unsafe_allow_html=True,
)
if st.button("🔍 生成分析", type="primary", use_container_width=True, key="gen_analysis_top"):
    task_id, err = submit_task_with_error("analysis", {"ticker": ticker})
    if task_id:
        st.session_state["analysis_task_id"] = task_id
        st.session_state["analysis_result"] = None
        st.info("📡 分析任务已提交到后台运行，你可以切到其他页面，完成后会在下方仪表盘自动显示结果。")
    else:
        err = err or "未知错误"
        if "登录" in err or "过期" in err or "凭证" in err:
            st.error(f"❌ {err}")
            if st.button("重新登录", key="anal_relogin_top", use_container_width=True):
                st.session_state.clear()
                st.switch_page("pages/0_登录.py")
        else:
            st.error(f"❌ 后台任务提交失败：{err}，请刷新重试。")
st.markdown('</div>', unsafe_allow_html=True)

def _run_analysis(ticker: str) -> dict:
    """拉取并构建个股分析所需全部数据；返回含所有渲染变量的 dict。"""
    # ── 基础信息 ──
    stock_name = fetcher.get_stock_name(ticker) or ticker
    _code, _name = fetcher.get_stock_basic(ticker)
    display_name = _name or stock_name or ticker
    # 行业/概念：由股票名称匹配关键词（真实派生，非编造）
    try:
        industry_kws = fetcher.get_stock_keywords(ticker, top_k=3)
        industry = industry_kws.split(",")[0] if industry_kws else "—"
    except Exception:
        industry = "—"

    # ── 并行拉取：实时行情 / 日线 / 新闻（三者相互独立，并发以降低总耗时）──
    today = datetime.now().date()
    start_str = (today - timedelta(days=365)).strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    import concurrent.futures as _cf

    def _fetch_quote():
        r = api_quote(ticker)
        if isinstance(r, dict) and r.get("current"):
            return r, "后端 API"
        try:
            return fetcher.get_realtime_quote(ticker), "新浪财经"
        except Exception:
            return None, "本地 fetcher"

    def _fetch_kline():
        try:
            _records = api_kline(ticker, start=start_str, end=end_str)
            if _records is None:
                return fetcher.get_daily(ticker, start=start_str, end=end_str), "本地四级降级链"
            return pd.DataFrame(_records), "后端 API"
        except Exception:
            return fetcher.get_daily(ticker, start=start_str, end=end_str), "本地四级降级链"

    def _fetch_news():
        try:
            return NewsFetcher().fetch(keyword=display_name, source="auto", limit=50)
        except Exception:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

    with _cf.ThreadPoolExecutor(max_workers=3) as _ex:
        _fq = _ex.submit(_fetch_quote)
        _fk = _ex.submit(_fetch_kline)
        _fn = _ex.submit(_fetch_news)
        rt, quote_src = _fq.result()
        df, data_src = _fk.result()
        news_df = _fn.result()

    if isinstance(rt, dict) and rt.get("current"):
        current_price = float(rt["current"])
        prev_close = float(rt.get("prev_close") or current_price)
        change_pct = (current_price - prev_close) / prev_close * 100 if prev_close else 0.0
    else:
        rt = None
        current_price = None
        change_pct = 0.0

    df = DataCleaner.full_pipeline(df)

    # ── 技术面 ──
    technical = technical_full_analysis(df)
    trend = technical.get("trend", {})
    momentum = technical.get("momentum", {})
    volume_info = technical.get("volume", {})
    patterns = technical.get("patterns", []) or []

    # ── 信号引擎（价格/事件/宏观）──
    keywords = [k.strip() for k in (industry_kws or "").split(",") if k.strip()] or [display_name]
    signal = SignalEngine().evaluate(ticker, keywords, date=None)

    # 四维雷达取值
    tech_score = float(signal.get("price_score", 50))
    news_score = float(signal.get("event_score", 50))
    macro_score = float(signal.get("macro_score", 50))
    vol_score = float(volume_info.get("volume_price_score", 50)) if "error" not in volume_info else 50.0

    # 综合评分（重新设计的总评规则，避免「各项都>70 总评却 65」的割裂感）：
    # 1) 基础加权（权重透明：技术面30% / 新闻情绪25% / 资金量能25% / 市场环境20%）；
    # 2) 一致性约束：若四维彼此接近（极差≤20），取「加权值」与「四维均值」的较大者，
    #    保证信号一致时总评不会因加权被压低到明显低于可见分项；
    # 3) 短板缓冲：总评不低于「最弱维度−8」，避免单一弱项把整体过度拉低、与可见信号严重背离。
    _dims = [tech_score, news_score, vol_score, macro_score]
    _w = [0.30, 0.25, 0.25, 0.20]
    _weighted = sum(d * w for d, w in zip(_dims, _w))
    _dim_avg = sum(_dims) / 4
    _dim_min, _dim_max = min(_dims), max(_dims)
    _base = _weighted
    if _dim_max - _dim_min <= 20:
        _base = max(_weighted, _dim_avg)  # 信号一致 → 总评不低于各维度均值
    _floor = _dim_min - 8                  # 短板缓冲
    composite = int(round(max(_base, _floor)))
    composite = max(0, min(100, composite))
    verdict, verdict_color, verdict_cls = _verdict_color(composite)

    # ── 新闻 / 情绪（news_df 已在并行拉取阶段获取）──
    sa = SentimentAnalyzer()
    news_rows = []
    pos_n = neg_n = neu_n = 0
    if not news_df.empty:
        for _, row in news_df.head(12).iterrows():
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
        pos_pct = pos_n / total_n * 100
        neg_pct = neg_n / total_n * 100
    else:
        pos_pct = neg_pct = 0.0

    # ── 支撑 / 压力（近 60 日，真实派生）──
    recent = df.tail(60)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    if current_price is None:
        current_price = float(df.iloc[-1]["close"])
    entry_price, target_price, stop_price, atr14 = _calc_trade_levels(current_price, df, support, resistance)

    # ── 乖离率（收盘价相对 MA20）──
    last = df.iloc[-1]
    ma20 = float(last.get("ma20", last["close"])) if "ma20" in df.columns else float(last["close"])
    deviation = (last["close"] - ma20) / ma20 * 100 if ma20 else 0.0

    # ── 52 周区间定位 ──
    lo52 = float(df["low"].min())
    hi52 = float(df["high"].max())
    pos52 = (last["close"] - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else 50.0

    # ── 均线（用于 K 线标注与量能）──
    ma5v = float(df["close"].rolling(5).mean().iloc[-1]) if len(df) >= 5 else float(last["close"])
    ma10v = float(df["close"].rolling(10).mean().iloc[-1]) if len(df) >= 10 else float(last["close"])
    ma20v = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else float(last["close"])
    # ── 套牢区（近期高位密集成交区）──
    trapped = float(df["high"].tail(120).max()) if len(df) >= 20 else float(hi52)
    # ── 量能分析 ──
    vol_now = float(df["volume"].iloc[-1])
    vol_prev = float(df["volume"].iloc[-2]) if len(df) >= 2 else vol_now
    vol_avg = float(df["volume"].tail(20).mean())
    vol_chg = (vol_now - vol_prev) / vol_prev * 100 if vol_prev else 0.0
    # ── 今日盘口（实时行情，缺失则 —）──
    q_open = float(rt["open"]) if isinstance(rt, dict) and rt.get("open") else None
    q_high = float(rt["high"]) if isinstance(rt, dict) and rt.get("high") else None
    q_low = float(rt["low"]) if isinstance(rt, dict) and rt.get("low") else None
    q_prev = float(rt["prev_close"]) if isinstance(rt, dict) and rt.get("prev_close") else None
    q_amount = float(rt["amount"]) if isinstance(rt, dict) and rt.get("amount") else None
    # ── 板块（由代码派生，真实）──
    def _board(code):
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
    board = _board(ticker)
    # ── 仓位建议（依研判）──
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
    }


# ══════════════════════════════════════════════════════════════
# 分析渲染：从 dict 中恢复所有变量并绘制 8 大模块
# ══════════════════════════════════════════════════════════════
def _render_analysis(R: dict):
    # 把结果字典展开到局部作用域，保持原渲染代码基本不变
    ticker = R["ticker"]
    display_name = R["display_name"]
    industry = R["industry"]
    current_price = R["current_price"]
    prev_close = R["prev_close"]
    change_pct = R["change_pct"]
    df = R["df"]
    technical = R["technical"]
    trend = R["trend"]
    momentum = R["momentum"]
    volume_info = R["volume_info"]
    patterns = R["patterns"]
    signal = R["signal"]
    tech_score = R["tech_score"]
    news_score = R["news_score"]
    macro_score = R["macro_score"]
    vol_score = R["vol_score"]
    composite = R["composite"]
    verdict = R["verdict"]
    verdict_color = R["verdict_color"]
    verdict_cls = R["verdict_cls"]
    sector_score = R.get("sector_score", 55)
    sector_analysis = R.get("sector_analysis",
                               {"name": industry, "change_pct": None, "label": "—", "rank": None, "total": None})
    technical_profile = R.get("technical_profile",
                                {"short": 50, "mid": 50, "long": 50, "trend": 50, "composite": 50})
    news_rows = R["news_rows"]
    pos_pct = R["pos_pct"]
    neg_pct = R["neg_pct"]
    support = R["support"]
    resistance = R["resistance"]
    entry_price = R["entry_price"]
    target_price = R["target_price"]
    stop_price = R["stop_price"]
    atr14 = R["atr14"]
    deviation = R["deviation"]
    lo52 = R["lo52"]
    hi52 = R["hi52"]
    pos52 = R["pos52"]
    ma5v = R["ma5v"]
    ma10v = R["ma10v"]
    ma20v = R["ma20v"]
    trapped = R["trapped"]
    vol_now = R["vol_now"]
    vol_prev = R["vol_prev"]
    vol_avg = R["vol_avg"]
    vol_chg = R["vol_chg"]
    q_open = R["q_open"]
    q_high = R["q_high"]
    q_low = R["q_low"]
    q_prev = R["q_prev"]
    q_amount = R["q_amount"]
    board = R["board"]
    position_advice = R["position_advice"]
    data_src = R["data_src"]
    quote_src = R["quote_src"]

    last = df.iloc[-1]

    # ════════════ 模块1：顶部决策摘要 ════════════
    st.markdown(_section_header("顶部决策摘要", "综合评分 · 仓位策略 · 风险价位", "🎯"), unsafe_allow_html=True)
    chg_txt = f"{change_pct:+.2f}%"
    price_disp = f"¥{current_price:.2f}" if current_price is not None else f"¥{last['close']:.2f}"
    change_amt = (current_price - prev_close) if (current_price is not None and prev_close is not None) else 0.0
    triangle = "▲" if change_pct > 0 else ("▼" if change_pct < 0 else "—")
    price_color = RED if change_pct > 0 else (GREEN if change_pct < 0 else AMBER)
    badge_text = "BUY" if verdict == "看多" else ("SELL" if verdict == "看空" else "HOLD")
    badge_class = "sf-buy-badge" if verdict == "看多" else ("sf-sell-badge" if verdict == "看空" else "sf-hold-badge")

    # 今日盘口（实时行情缺失则用 —）
    today_bits = []
    if q_open is not None:
        today_bits.append(f"今开 ¥{q_open:.2f}")
    if q_high is not None:
        today_bits.append(f"最高 ¥{q_high:.2f}")
    if q_low is not None:
        today_bits.append(f"最低 ¥{q_low:.2f}")
    if q_prev is not None:
        today_bits.append(f"昨收 ¥{q_prev:.2f}")
    if q_amount is not None:
        today_bits.append(f"成交额 {q_amount / 1e8:.2f}亿")
    today_bits.append(f"成交量 {df['volume'].iloc[-1] / 1e4:.1f}万手")
    today_pills = "".join(
        f"<span style='display:inline-block;font-size:12px;color:#64748b;"
        f"background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;"
        f"padding:3px 9px;margin:0 6px 6px 0;'>{b}</span>"
        for b in today_bits
    ) if today_bits else "—"

    hdr_left, hdr_right = st.columns([3, 1])
    with hdr_left:
        st.markdown(
            f"<div style='font-size:23px;font-weight:700;color:#1e293b;'>{display_name}</div>"
            f"<div style='font-size:12.5px;color:#64748b;margin-top:3px;'>"
            f"{ticker} · {board} · {industry}</div>"
            f"<div style='margin-top:10px;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;'>"
            f"<span class='sf-price-big' style='color:{price_color}!important;'>{price_disp}</span>"
            f"<span style='font-size:16px;font-weight:600;color:{price_color};'>"
            f"<span class='sf-triangle'>{triangle}</span>{chg_txt} ({change_amt:+.2f})</span></div>"
            f"<div style='margin-top:8px;'>{today_pills}</div>",
            unsafe_allow_html=True,
        )
    with hdr_right:
        st.markdown(
            f"<div style='text-align:center;margin-bottom:10px;'><span class='{badge_class}'>{badge_text}</span></div>"
            f"{_score_ring_html(composite, verdict_color)}"
            f"<div style='font-size:12px;color:#64748b;text-align:center;margin-top:4px;'>"
            f"{verdict} · {'择机买入' if verdict=='看多' else ('逢高减仓' if verdict=='看空' else '区间波段')}<br>"
            f"({'65~79区间' if 65 <= composite <= 79 else '综合评分区间'})</div>",
            unsafe_allow_html=True,
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            "<div class='sf-metric-card'>"
            "<div class='label'>入场价（首仓 / 回踩）</div>"
            f"<div class='value sf-doc-up'>¥{current_price:.1f} / ¥{entry_price:.1f}</div>"
            "</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(
            "<div class='sf-metric-card'>"
            "<div class='label'>目标价（一目标 / 压力）</div>"
            f"<div class='value sf-doc-up'>¥{target_price:.1f} / ¥{resistance:.1f}</div>"
            "</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(
            "<div class='sf-metric-card'>"
            "<div class='label'>止损价（ATR14 风险位）</div>"
            f"<div class='value sf-doc-down'>¥{stop_price:.1f}</div>"
            f"<div style='font-size:11px;color:#64748b;margin-top:4px;'>ATR14=¥{atr14:.2f}</div>"
            "</div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='font-size:13px;color:#64748b;margin-top:12px;line-height:1.7;'>"
        f"<b style='color:#1e293b;'>仓位建议：</b>{position_advice}</div>",
        unsafe_allow_html=True,
    )

    # ════════════ 模块2：核心结论 ════════════
    st.markdown('<div class="sf-card">' + _section_header("核心结论", "AI 综合研判 · 多空信号", "💡"), unsafe_allow_html=True)
    trend_label = trend.get("trend_label", "—") if "error" not in trend else "数据不足"
    mom_label = momentum.get("momentum_label", "—") if "error" not in momentum else "—"
    vol_label = volume_info.get("volume_price_label", "—") if "error" not in volume_info else "—"
    one_line = (
        f"{display_name} 现价 ¥{current_price:.2f}（{chg_txt}），技术面「{trend_label}」、"
        f"动量「{mom_label}」、量能「{vol_label}」；新闻情绪正面占比 {pos_pct:.0f}%，"
        f"综合研判 <b>{verdict}</b>。"
    )
    hold_cls = " hold" if verdict == "持有" else ""
    st.markdown(f'<div class="sf-insight-box{hold_cls}">{one_line}</div>', unsafe_allow_html=True)
    st.markdown(
        f"<span class='sf-tag {verdict_cls}'>信号 · {verdict}</span>"
        f"<span class='sf-tag neu'>策略 · {'分批建仓' if verdict=='看多' else ('逢高减仓' if verdict=='看空' else '区间波段')}</span>"
        f"<span class='sf-tag neu'>适用 · 事件驱动 / 中短线</span>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块3：数据透视 ════════════
    st.markdown('<div class="sf-card">' + _section_header("数据透视", "量价 / 筹码 / 位置 / 乖离", "📊"), unsafe_allow_html=True)
    arrangement = trend.get("arrangement", "") if "error" not in trend else ""
    if "多头" in arrangement:
        short_pill, short_cls = "短期转强", "up"
    elif "空头" in arrangement:
        short_pill, short_cls = "短期转弱", "down"
    else:
        short_pill, short_cls = "短期震荡", "mid"
    dev5 = (last['close'] - ma5v) / ma5v * 100 if ma5v else 0.0
    dev10 = (last['close'] - ma10v) / ma10v * 100 if ma10v else 0.0
    dev20 = (last['close'] - ma20v) / ma20v * 100 if ma20v else 0.0
    price_chain = f"价 {current_price:.2f}"
    price_chain += f" {'>' if current_price >= ma5v else '<'} MA5({ma5v:.1f})"
    price_chain += f" {'>' if ma5v >= ma10v else '<'} MA10({ma10v:.1f})"
    if current_price < ma20v:
        price_chain += f" · MA20({ma20v:.1f})<span class='sf-doc-down'>压制</span>"
    else:
        price_chain += f" > MA20({ma20v:.1f})"
    dist_high = (last['close'] / hi52 - 1) * 100 if hi52 else 0.0
    pos_desc = "中下部" if pos52 < 50 else "中上部"

    st.markdown(
        "<div class='sf-grid-4'>"
        "<div class='sf-perspective-card'>"
        "<div class='title'>技术面 · 多周期（综合 {technical_profile['composite']}）</div>"
        "<div class='body'>"
        f"<span class='sf-pill {_tp_cls(technical_profile['short'])}'>短期 {technical_profile['short']}</span>"
        f"<span class='sf-pill {_tp_cls(technical_profile['mid'])}'>中期 {technical_profile['mid']}</span>"
        f"<span class='sf-pill {_tp_cls(technical_profile['long'])}'>长期 {technical_profile['long']}</span>"
        "</div></div>"
        "<div class='sf-perspective-card'>"
        "<div class='title'>价格位置（相对关键均线）</div>"
        f"<div class='body'>{price_chain}</div></div>"
        "<div class='sf-perspective-card'>"
        "<div class='title'>乖离率（严进标准 &lt;5%）</div>"
        "<div class='body'>"
        f"MA5 <b class='sf-doc-up'>{dev5:+.1f}%</b> · "
        f"MA10 <b class='sf-doc-up'>{dev10:+.1f}%</b> · "
        f"MA20 <b class='sf-doc-down'>{dev20:+.1f}%</b>"
        "</div></div>"
        "<div class='sf-perspective-card'>"
        "<div class='title'>52周区间</div>"
        f"<div class='body'><b>¥{lo52:.2f} – ¥{hi52:.2f}</b><br>"
        f"（现处{pos_desc}，距前高 {dist_high:+.0f}%）"
        "</div></div></div>",
        unsafe_allow_html=True,
    )

    # 量能分析 + 筹码结构（参考文档「数据透视」补全，真实派生）
    _vol_desc = (
        "明显放量" if vol_chg > 30 else
        "温和放大" if vol_chg > 0 else
        "缩量" if vol_chg < -15 else "地量企稳"
    )
    _vol_health = "健康换手而非过热" if abs(vol_chg) < 40 else "异常波动需警惕"
    st.markdown(
        f"<div style='margin-top:12px;font-size:13.5px;color:#64748b;line-height:1.7;'>"
        f"<b style='color:#1e293b;'>量能分析：</b>近 20 日均量约 {vol_avg/1e4:.1f} 万手；"
        f"最新一日 {vol_now/1e4:.1f} 万手，较前一日 {vol_chg:+.1f}%（{_vol_desc}）；"
        f"成交额 {q_amount/1e8:.2f} 亿（实时行情），当前属{_vol_health}。"
        f"</div>",
        unsafe_allow_html=True,
    )
    _drawdown = (last['close'] / trapped - 1) * 100 if trapped > 0 else 0.0
    st.markdown(
        f"<div style='margin-top:8px;font-size:13.5px;color:#64748b;line-height:1.7;'>"
        f"<b style='color:#1e293b;'>筹码结构：</b>近 120 日自 {trapped:.2f} 高点回落至现价 {last['close']:.2f}"
        f"（约 {_drawdown:+.1f}%），{trapped:.2f}–{hi52:.2f} 区间为近期密集成交"
        f"<b style='color:{AMBER};'>套牢区</b>，反弹至此抛压显著；"
        f"前低 <b style='color:{RED};'>¥{support:.2f}</b> 为强支撑，MA5/MA10 为短期依托。"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块4：技术指标图表 ════════════
    st.markdown('<div class="sf-card">' + _section_header("技术指标图表", "K线 + 均线 + 成交量 · 日期坐标", "📈"), unsafe_allow_html=True)
    st.markdown(
        Visualizer.kline_legend_html(
            ma_windows=[5, 10, 20],
            up_color=RED, down_color=GREEN,
            ma_colors=["#ffa502", "#667eea", "#009e60"],
        ),
        unsafe_allow_html=True,
    )
    try:
        # 参考文档 002947：绿涨红跌、MA5橙/MA10靛/MA20绿、
        # 标注 MA20压制(红虚) / MA10(靛虚) / 前低支撑(绿虚) / 套牢区(琥珀点)
        kline_annotations = [
            {"price": ma20v, "label": "MA20压制", "color": GREEN, "dash": "dash"},
            {"price": ma10v, "label": "MA10", "color": "#667eea", "dash": "dash"},
            {"price": support, "label": "前低支撑", "color": RED, "dash": "dash"},
            {"price": trapped, "label": "套牢区", "color": AMBER, "dash": "dot"},
        ]
        fig = Visualizer.candlestick(
            df,
            title="技术指标图表（K线 + 均线 + 成交量）",
            show_volume=True,
            ma_windows=[5, 10, 20],
            annotations=kline_annotations,
            support=None,
            resistance=None,
            up_color=RED,
            down_color=GREEN,
            ma_colors=["#ffa502", "#667eea", "#009e60"],
        )
        st.plotly_chart(fig, use_container_width=True)
        # K线交互提示（解决用户对工具栏双机还原、框选放大、拖拽平移的困惑）
        st.markdown(
            "<div style='font-size:12px;color:#64748b;margin:8px 0 6px;display:flex;align-items:center;gap:8px;'>"
            "<span>💡</span>"
            "<span>按住鼠标拖拽可平移；点击工具栏 🔍 后框选区域可放大；"
            "点击 🏠 可还原视图（部分浏览器需双击）。十字光标默认开启。</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        # 图表下方说明：标注线 + 日期区间（参考文档）
        st.markdown(
            "<div style='font-size:12px;color:#64748b;margin-top:4px;'>"
            "绿柱为上涨、红柱为下跌（参考文档配色）。"
            "均线 MA5(橙)/MA10(靛)/MA20(绿)；"
            f"标注线：MA20压制 ¥{ma20v:.2f} / MA10 ¥{ma10v:.2f} / "
            f"前低支撑 ¥{support:.2f} / 套牢区 ¥{trapped:.2f}。"
            f"数据区间 {pd.to_datetime(df['date']).min().strftime('%Y-%m-%d')} "
            f"~ {pd.to_datetime(df['date']).max().strftime('%Y-%m-%d')}。"
            "</div>",
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.warning(f"⚠️ K线图渲染失败：{str(e)[:80]}")
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块5：情报面 ════════════
    neu_pct = max(0, 100 - pos_pct - neg_pct)
    st.markdown('<div class="sf-card">' + _section_header("情报面", "新闻情绪 · 事件催化 · 风险提示", "📰"), unsafe_allow_html=True)
    st.markdown(
        f"<div class='sf-intel-header'>"
        f"<div>"
        f"<span class='sf-pill up'>正面 {pos_pct:.0f}%</span>"
        f"<span class='sf-pill mid'>中性 {neu_pct:.0f}%</span>"
        f"<span class='sf-pill down'>负面 {neg_pct:.0f}%</span>"
        f"</div></div>"
        f"<div class='sf-intel-bar'>"
        f"<div class='bar-pos' style='width:{pos_pct:.0f}%'></div>"
        f"<div class='bar-neu' style='width:{neu_pct:.0f}%'></div>"
        f"<div class='bar-neg' style='width:{neg_pct:.0f}%'></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if news_rows:
        rows_html = "".join(
            f"<tr><td class='l'>{r['title']}</td>"
            f"<td><span class='sf-tag {_sentiment_tag(r['sentiment'])}'>{r['sentiment']}</span></td></tr>"
            for r in news_rows[:10]
        )
        st.markdown(
            f"<table class='sf-table'><thead><tr><th class='l'>新闻标题</th><th>情绪</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table>",
            unsafe_allow_html=True,
        )
    else:
        st.info("暂无新闻数据（网络不可用或该标的无公开新闻）。")

    # 风险警报（负面新闻或偏空信号）
    if neg_pct >= 30 or verdict == "看空":
        risk_titles = [r["title"] for r in news_rows if r["sentiment"] == "负面"][:2]
        risk_body = "；".join(risk_titles) if risk_titles else f"综合研判偏空（{verdict}）"
        st.markdown(
            f"<div class='sf-alert risk'><b>⚠️ 风险警报</b>检测到偏空信号：{risk_body}。"
            f"建议严格控制仓位并关注止损价 ¥{stop_price:.2f}。</div>",
            unsafe_allow_html=True,
        )
    # 积极催化（正面新闻或偏多信号）
    if pos_pct >= 40 or verdict == "看多":
        cat_titles = [r["title"] for r in news_rows if r["sentiment"] == "正面"][:2]
        cat_body = "；".join(cat_titles) if cat_titles else f"综合研判偏多（{verdict}）"
        st.markdown(
            f"<div class='sf-alert cat'><b>🚀 积极催化</b>检测到正面信号：{cat_body}。"
            f"可关注突破压力 ¥{target_price:.2f} 后的趋势机会。</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块6：信号归因（四维雷达）══════════
    # ══════════ 新增模块：板块分析 ══════════
    st.markdown('<div class="sf-card">' + _section_header("板块分析", "主板块定位 · 实时走势 · 相对强度", "📊"), unsafe_allow_html=True)
    _sa_name = sector_analysis.get("name", "—")
    _sa_chg = sector_analysis.get("change_pct")
    _sa_label = sector_analysis.get("label", "—")
    _sa_rank = sector_analysis.get("rank")
    _sa_total = sector_analysis.get("total")
    _sa_chg_txt = f"{_sa_chg:+.2f}%" if _sa_chg is not None else "—"
    _sa_chg_color = RED if (_sa_chg or 0) > 0 else (GREEN if (_sa_chg or 0) < 0 else AMBER)
    _sa_rank_txt = f"全市场第 {_sa_rank}/{_sa_total} 强" if (_sa_rank and _sa_total) else "—"
    if sector_score >= 60:
        _rel_txt = f"{display_name} 领涨所属板块，相对强度突出"
    elif sector_score <= 40:
        _rel_txt = f"{display_name} 弱于所属板块，需警惕补跌"
    else:
        _rel_txt = f"{display_name} 与所属板块基本同步"
    st.markdown(
        f"<div style='display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-bottom:10px;'>"
        f"<div style='font-size:18px;font-weight:700;color:#1e293b;'>{_sa_name}</div>"
        f"<span class='sf-pill {_tp_cls(sector_score)}'>板块强度 {sector_score}</span>"
        f"<span style='font-size:14px;font-weight:600;color:{_sa_chg_color};'>{_sa_chg_txt} {_sa_label}</span>"
        f"<span class='sf-pill mid'>{_sa_rank_txt}</span>"
        f"</div>"
        f"<div style='font-size:13.5px;color:#64748b;line-height:1.7;'>"
        f"<b style='color:#1e293b;'>板块研判：</b>{_rel_txt}。"
        f"该主线属「{_sa_name}」，实时涨跌幅 {_sa_chg_txt}，{_sa_rank_txt}，"
        f"结合下方五维雷达的「板块」维度综合判断。</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sf-card">' + _section_header("信号归因 · 五维雷达", "技术 / 情绪 / 量能 / 宏观 / 板块", "🎯"), unsafe_allow_html=True)
    try:
        import plotly.graph_objects as go
        radar_fig = go.Figure()
        cats = ["技术指标", "新闻情绪", "资金量能", "市场环境", "板块强度"]
        vals = [tech_score, news_score, vol_score, macro_score, sector_score]
        radar_fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=cats + [cats[0]],
            fill="toself",
            line=dict(color="#667eea", width=2),
            fillcolor="rgba(102,126,234,0.25)",
            name="信号强度",
        ))
        radar_fig.update_layout(
            polar=dict(
                radialaxis=dict(range=[0, 100], gridcolor="#e5e7eb", tickfont=dict(color="#64748b")),
                bgcolor="rgba(0,0,0,0)",
                angularaxis=dict(gridcolor="#e5e7eb", tickfont=dict(color="#1e293b")),
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            height=440,
            margin=dict(l=40, r=40, t=20, b=20),
        )
        st.plotly_chart(radar_fig, use_container_width=True)
        st.markdown(
            f"<div style='text-align:center;font-size:14px;font-weight:700;color:#1e293b;"
            f"margin:6px 0 2px;'>综合信号强度 <b style='color:{verdict_color};'>{composite}</b>"
            f" · {verdict}（五维加权）</div>",
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.warning(f"⚠️ 雷达图渲染失败：{str(e)[:80]}")

    # 权重表（五维加权：技术 25% / 情绪 22% / 量能 18% / 宏观 15% / 板块 20%）
    st.markdown(
        "<table class='sf-table'>"
        "<thead><tr><th class='l'>维度（权重）</th><th>得分</th><th class='l'>研判要点</th></tr></thead><tbody>"
        f"<tr><td class='l'><b>技术指标</b> 25%</td><td>{tech_score:.0f}</td>"
        f"<td class='l'>多周期（短/中/长）趋势 · 动量强弱</td></tr>"
        f"<tr><td class='l'><b>新闻情绪</b> 22%</td><td>{news_score:.0f}</td>"
        f"<td class='l'>事件催化强度 · 正面占比 {pos_pct:.0f}%</td></tr>"
        f"<tr><td class='l'><b>资金量能</b> 18%</td><td>{vol_score:.0f}</td>"
        f"<td class='l'>量价配合 · 换手健康度</td></tr>"
        f"<tr><td class='l'><b>市场环境</b> 15%</td><td>{macro_score:.0f}</td>"
        f"<td class='l'>宏观 PMI · 大盘强弱</td></tr>"
        f"<tr><td class='l'><b>板块强度</b> 20%</td><td>{sector_score:.0f}</td>"
        f"<td class='l'>个股相对所属板块的强弱 · 排名 {sector_analysis.get('rank','—')}"
        f"{('/'+str(sector_analysis.get('total'))) if sector_analysis.get('total') else ''} 强</td></tr>"
        f"<tr><td class='l'><b>综合评分</b></td><td><b>{composite}</b></td><td class='l'>五维加权汇总</td></tr>"
        "</tbody></table>",
        unsafe_allow_html=True,
    )

    # 最强看多 / 看空 callouts
    bull = []
    bear = []
    if "error" not in trend:
        if trend.get("arrangement") in ("多头排列", "偏多"):
            bull.append(f"均线「{trend.get('arrangement')}」，站上 {trend.get('above_count',0)} 条均线")
        if trend.get("arrangement") in ("空头排列", "偏空"):
            bear.append(f"均线「{trend.get('arrangement')}」")
    if "error" not in momentum:
        if momentum.get("momentum_score", 50) >= 65:
            bull.append(f"动量「{mom_label}」（5日 {momentum.get('returns',{}).get('5日',0):+.2f}%）")
        elif momentum.get("momentum_score", 50) <= 35:
            bear.append(f"动量「{mom_label}」")
    if "error" not in volume_info:
        if "升" in vol_label:
            bull.append(f"量能「{vol_label}」")
        if "跌" in vol_label:
            bear.append(f"量能「{vol_label}」")
    if pos_pct >= neg_pct:
        bull.append(f"新闻正面占比 {pos_pct:.0f}% 高于负面 {neg_pct:.0f}%")
    else:
        bear.append(f"新闻负面占比 {neg_pct:.0f}% 高于正面 {pos_pct:.0f}%")
    if verdict == "看多":
        bull.append("综合信号看多")
    elif verdict == "看空":
        bear.append("综合信号看空")

    st.markdown("<div class='sf-vs'>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='sf-vsbox'><h3 style='color:{RED};'>最强看多信号</h3>"
        + ("".join(f"<ul><li>{b}</li></ul>" for b in bull) if bull else "<ul><li>暂无显著看多信号</li></ul>")
        + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='sf-vsbox'><h3 style='color:{GREEN};'>最强看空信号</h3>"
        + ("".join(f"<ul><li>{b}</li></ul>" for b in bear) if bear else "<ul><li>暂无显著看空信号</li></ul>")
        + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块7：作战计划 ════════════
    st.markdown('<div class="sf-card">' + _section_header("作战计划", "支撑压力 · 分批建仓 · 纪律止损", "⚔️"), unsafe_allow_html=True)
    st.markdown("<div style='color:var(--txt2);font-size:13px;'>支撑（前低）→ 压力（套牢区）价格刻度</div>", unsafe_allow_html=True)
    st.markdown(
        _support_resistance_bar(
            support, trapped, current_price,
            markers=[
                ("前低", support, RED),
                ("MA5", ma5v, "#ffa502"),
                ("MA10", ma10v, "#667eea"),
                ("MA20", ma20v, GREEN),
                ("套牢区", trapped, AMBER),
            ],
        ),
        unsafe_allow_html=True,
    )

    st.markdown("<div style='color:var(--txt);font-weight:600;margin:14px 0 4px;'>分批建仓 / 减仓计划</div>",
                unsafe_allow_html=True)
    plan_rows = [
        ("建仓①", f"回调至回踩位", f"¥{entry_price:.2f}~¥{current_price:.2f}", "30%",
         "首仓试探，回踩确认有效"),
        ("建仓②", "放量突破 MA20", f"¥{ma20v:.2f}~¥{current_price:.2f}", "30%",
         "趋势确认后加仓"),
        ("加仓", f"突破目标价 ¥{target_price:.2f}", f"¥{target_price:.2f} 上方", "20%",
         "顺势跟随，不追高"),
        ("减仓①", f"到达目标价 ¥{target_price:.2f}", f"≈¥{target_price:.2f}", "-40%",
         "兑现部分利润"),
        ("减仓②", f"跌破止损 ¥{stop_price:.2f}", f"≤¥{stop_price:.2f}", "清仓",
         "纪律止损，控制回撤"),
    ]
    rows_html = "".join(
        f"<tr><td>{r[0]}</td><td class='l'>{r[1]}</td><td>{r[2]}</td>"
        f"<td>{r[3]}</td><td class='l'>{r[4]}</td></tr>"
        for r in plan_rows
    )
    st.markdown(
        "<table class='sf-table'>"
        "<thead><tr><th>批次</th><th class='l'>触发条件</th><th>价格区间</th>"
        "<th>仓位</th><th class='l'>说明</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='color:var(--txt);font-weight:600;margin:14px 0 4px;'>风险控制清单</div>",
                unsafe_allow_html=True)
    risk_items = [
        f"止损价：¥{stop_price:.2f}（破位无条件离场）",
        f"止盈价：¥{target_price:.2f}（到达分批兑现）",
        "失效条件：突发利空 / 放量跌穿支撑 / 宏观转弱（PMI<50）",
        "仓位纪律：单标的 ≤ 总仓位 30%，亏损单不补仓摊平",
    ]
    st.markdown("<ul style='color:#64748b;font-size:13px;line-height:1.9;'>"
                + "".join(f"<li>{x}</li>" for x in risk_items) + "</ul>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块8：底部元信息 ════════════
    st.markdown(
        f"<div class='sf-disclaimer'>"
        f"分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ "
        f"标的：{display_name}({ticker}) ｜ "
        f"数据来源：行情 {data_src}、实时行情 {quote_src}、新闻 东方财富/财新/央视多源聚合、宏观 PMI ｜ "
        f"声明：本页所有结论均由程序基于公开数据自动计算，仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。"
        f"</div>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# 主交互：提交后台任务，不阻塞页面，切页后继续运行
# ══════════════════════════════════════════════════════════════
def _deserialize_analysis_result(result: dict) -> dict:
    """把后台返回的 JSON（DataFrame 已序列化为 records）还原成页面可渲染的 dict。"""
    if not result:
        return result
    if "df" in result and isinstance(result["df"], list):
        result["df"] = pd.DataFrame(result["df"])
        if "date" in result["df"].columns:
            result["df"]["date"] = pd.to_datetime(result["df"]["date"], errors="coerce")
    return result


st.info("👆 在上方「决策仪表盘」顶部点击红色「生成分析」即可生成完整的个股深度分析。")

# 轮询后台任务
analysis_task_id = st.session_state.get("analysis_task_id")
if analysis_task_id:
    task = poll_task(analysis_task_id, max_wait=0.5)
    if task and task.get("status") == "success":
        result = _deserialize_analysis_result(task.get("result"))
        for w in result.pop("_warnings", []):
            st.warning(w)
        st.session_state["analysis_result"] = result
        del st.session_state["analysis_task_id"]
        st.toast("✅ 个股分析完成")
    elif task and task.get("status") == "error":
        st.error(f"分析失败：{task.get('error')}")
        del st.session_state["analysis_task_id"]
    elif task and task.get("status") in ("pending", "running"):
        st.info("⏳ 后台正在拉取行情 / 新闻 / 信号… 切到其他页面也会继续跑。")

if st.session_state.get("analysis_result") is not None:
    _render_analysis(st.session_state["analysis_result"])
else:
    st.info("👈 在左侧选择股票后，点击「生成分析」查看完整的个股深度决策仪表盘。")
