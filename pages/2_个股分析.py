"""
页面2：个股分析
暗夜风格「决策仪表盘 · 个股深度分析」（参考「星辰决策仪表盘」组件类 .sf-*）。

严格遵循 A 股配色：涨/利好/买入 = RED(#ff4d4f)，跌/利空/卖出 = GREEN(#00d486)，
中性/持有 = amber(#ffa502)。所有外部数据获取均包在 try/except 中，失败时 st.warning。
仅做前端/UI，不改动 backend 或任何数据逻辑。
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ── 前置：本页为「决策仪表盘」暗色页面，由 ui_theme 按页面作用域(_active_page)强制暗色，
#    不再改写全局 theme_mode，避免访问该页后其它页面被意外变暗（用户投诉的「切模块黑白切换」）──
st.set_page_config(page_title="个股分析", page_icon="🔍", layout="wide")
st.session_state["_active_page"] = __file__

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.news import NewsFetcher, SentimentAnalyzer
from modules.visualizer import Visualizer, UP_COLOR, DOWN_COLOR
from modules.session import init_session_state, require_auth, render_user_badge, api_kline, api_quote
from modules.search_ui import stock_search_input

# A股配色常量（与 ui_theme._DARK_CSS 的 --buy/--sell/--hold 一致）
RED = "#ff4d4f"      # 涨 / 利好 / 买入
GREEN = "#00d486"    # 跌 / 利空 / 卖出
AMBER = "#ffa502"    # 中性 / 持有

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
        <circle cx="70" cy="70" r="{r}" fill="none" stroke="#2d2d44" stroke-width="12"/>
        <circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" stroke-width="12"
                stroke-linecap="round" stroke-dasharray="{dash:.1f} {c:.1f}"
                transform="rotate(-90 70 70)"/>
        <text x="70" y="64" text-anchor="middle" font-size="34" font-weight="700"
              fill="{color}" font-family="Fira Code, monospace">{score}</text>
        <text x="70" y="88" text-anchor="middle" font-size="12" fill="#94a3b8">综合评分</text>
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
    return "#94a3b8"


def _support_resistance_bar(support: float, resistance: float, current: float) -> str:
    """支撑 → 压力 价格刻度条，标注当前价位置。"""
    if resistance <= support:
        return ""
    span = resistance - support
    pos = max(0.0, min(100.0, (current - support) / span * 100.0))
    return f"""
    <div style="margin:10px 0 4px;">
      <div style="position:relative;height:26px;border-radius:13px;
           background:linear-gradient(90deg,{GREEN}33,{AMBER}33,{RED}33);
           border:1px solid #2d2d44;">
        <div style="position:absolute;top:-4px;left:{pos:.1f}%;
             transform:translateX(-50%);width:2px;height:34px;background:#e2e8f0;"></div>
        <div style="position:absolute;top:-22px;left:{pos:.1f}%;
             transform:translateX(-50%);font-size:11px;color:#e2e8f0;white-space:nowrap;">
           现价 ¥{current:.2f}</div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#94a3b8;margin-top:6px;">
        <span>支撑 ¥{support:.2f}</span>
        <span>压力 ¥{resistance:.2f}</span>
      </div>
    </div>
    """


def _sentiment_tag(sentiment: str) -> str:
    """情感 → .sf-tag 类别（利好→win, 利空→weak, 中性→neu）。"""
    m = {"正面": "win", "利好": "win", "负面": "weak", "利空": "weak", "中性": "neu"}
    return m.get(sentiment, "neu")


# ══════════════════════════════════════════════════════════════
# 股票选择（侧边栏，复用 行情看板 的交互）
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("分析标的")
    ticker = stock_search_input(
        label="股票搜索",
        key="analysis_stock",
        default="600519",
        placeholder="输入代码或名称搜索，如：600519 / 贵州茅台 / GZMT / 茅台",
    )
    st.caption("本页强制暗夜模式以匹配决策仪表盘风格。")

# 主区标题
st.markdown(
    '<div class="sf-header"><div class="sf-brand">决策仪表盘 · '
    '<b>个股深度分析</b></div><div class="sf-brand">事件驱动 · 多维归因</div></div>',
    unsafe_allow_html=True,
)

if st.button("🔍 生成分析", type="primary", use_container_width=True):
    with st.spinner("正在拉取行情 / 新闻 / 信号，构建分析..."):
        try:
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

            # ── 实时行情（后端优先，本地兜底）──
            quote_src = "本地 fetcher"
            rt = api_quote(ticker)
            if rt is None:
                try:
                    rt = fetcher.get_realtime_quote(ticker)
                    quote_src = "新浪财经"
                except Exception:
                    rt = None
            if isinstance(rt, dict) and rt.get("current"):
                current_price = float(rt["current"])
                prev_close = float(rt.get("prev_close") or current_price)
                change_pct = (current_price - prev_close) / prev_close * 100 if prev_close else 0.0
            else:
                rt = None
                current_price = None
                change_pct = 0.0

            # ── 日线行情（后端优先，本地兜底）──
            today = datetime.now().date()
            start_str = (today - timedelta(days=365)).strftime("%Y-%m-%d")
            end_str = today.strftime("%Y-%m-%d")
            data_src = "后端 API"
            try:
                _records = api_kline(ticker, start=start_str, end=end_str)
                if _records is None:
                    data_src = "本地四级降级链"
                    df = fetcher.get_daily(ticker, start=start_str, end=end_str)
                else:
                    df = pd.DataFrame(_records)
            except Exception as e:
                st.warning(f"⚠️ 行情获取失败，尝试本地兜底：{str(e)[:80]}")
                data_src = "本地四级降级链"
                df = fetcher.get_daily(ticker, start=start_str, end=end_str)
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

            # 综合评分（四维加权）
            composite = int(round(
                tech_score * 0.35 + news_score * 0.25 + vol_score * 0.15 + macro_score * 0.25
            ))
            composite = max(0, min(100, composite))
            verdict, verdict_color, verdict_cls = _verdict_color(composite)

            # ── 新闻 / 情绪 ──
            try:
                news_df = NewsFetcher().fetch(keyword=display_name, source="auto", limit=50)
            except Exception as e:
                st.warning(f"⚠️ 新闻抓取失败：{str(e)[:80]}")
                news_df = pd.DataFrame(columns=["date", "title", "content", "source", "url"])

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
            entry_price = current_price
            target_price = round(resistance, 2)
            stop_price = round(support, 2)

            # ── 乖离率（收盘价相对 MA20）──
            last = df.iloc[-1]
            ma20 = float(last.get("ma20", last["close"])) if "ma20" in df.columns else float(last["close"])
            deviation = (last["close"] - ma20) / ma20 * 100 if ma20 else 0.0

            # ── 52 周区间定位 ──
            lo52 = float(df["low"].min())
            hi52 = float(df["high"].max())
            pos52 = (last["close"] - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else 50.0

            # ════════════ 模块1：顶部决策摘要 ════════════
            st.markdown("### 顶部决策摘要")
            col_hdr1, col_hdr2, col_hdr3 = st.columns([2, 2, 1])
            with col_hdr1:
                chg_txt = f"{change_pct:+.2f}%" if rt else "—"
                st.markdown(
                    f"<div style='font-size:20px;font-weight:700;color:#e2e8f0;'>"
                    f"{display_name} <span style='color:#94a3b8;font-size:13px;'>({ticker})</span></div>"
                    f"<div style='color:#94a3b8;font-size:13px;margin-top:2px;'>所属行业/概念：{industry}</div>",
                    unsafe_allow_html=True,
                )
            with col_hdr2:
                price_disp = f"¥{current_price:.2f}" if current_price is not None else f"¥{last['close']:.2f}"
                st.markdown(
                    f"<div style='font-size:22px;font-weight:700;color:{_price_color(change_pct)};'>"
                    f"{price_disp} <span style='font-size:14px;'>{chg_txt}</span></div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='font-size:12px;color:#94a3b8;margin-top:4px;'>"
                    f"入场价 <b style='color:#e2e8f0;'>¥{entry_price:.2f}</b> ｜ "
                    f"目标价 <b style='color:{RED};'>¥{target_price:.2f}</b> ｜ "
                    f"止损价 <b style='color:{GREEN};'>¥{stop_price:.2f}</b></div>",
                    unsafe_allow_html=True,
                )
            with col_hdr3:
                st.markdown(
                    f"<div style='text-align:center;'><span class='sf-tag {verdict_cls}' "
                    f"style='font-size:15px;padding:6px 16px;'>{verdict}</span></div>"
                    f"{_score_ring_html(composite, verdict_color)}",
                    unsafe_allow_html=True,
                )

            # ════════════ 模块2：核心结论 ════════════
            st.markdown('<div class="sf-card"><h2>核心结论</h2>', unsafe_allow_html=True)
            trend_label = trend.get("trend_label", "—") if "error" not in trend else "数据不足"
            mom_label = momentum.get("momentum_label", "—") if "error" not in momentum else "—"
            vol_label = volume_info.get("volume_price_label", "—") if "error" not in volume_info else "—"
            one_line = (
                f"{display_name} 现价 ¥{current_price:.2f}（{chg_txt}），技术面「{trend_label}」、"
                f"动量「{mom_label}」、量能「{vol_label}」；新闻情绪正面占比 {pos_pct:.0f}%，"
                f"综合研判 <b>{verdict}</b>。"
            )
            hold_cls = " hold" if verdict == "持有" else ""
            st.markdown(f'<div class="sf-one-line{hold_cls}">{one_line}</div>', unsafe_allow_html=True)
            st.markdown(
                f"<span class='sf-tag {verdict_cls}'>信号 · {verdict}</span>"
                f"<span class='sf-tag neu'>策略 · {'分批建仓' if verdict=='看多' else ('逢高减仓' if verdict=='看空' else '区间波段')}</span>"
                f"<span class='sf-tag neu'>适用 · 事件驱动 / 中短线</span>",
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

            # ════════════ 模块3：数据透视 ════════════
            st.markdown('<div class="sf-card"><h2>数据透视</h2>', unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.markdown("<div style='color:#94a3b8;font-size:12px;'>趋势状态</div>"
                            f"<div style='font-size:16px;font-weight:700;color:#e2e8f0;'>{trend_label}</div>",
                            unsafe_allow_html=True)
            with k2:
                above = trend.get("above_count", 0) if "error" not in trend else 0
                rel = "站上均线" if last["close"] >= ma20 else "跌破均线"
                st.markdown("<div style='color:#94a3b8;font-size:12px;'>价格相对均线</div>"
                            f"<div style='font-size:16px;font-weight:700;color:#e2e8f0;'>{rel}（{above}/4）</div>",
                            unsafe_allow_html=True)
            with k3:
                st.markdown("<div style='color:#94a3b8;font-size:12px;'>乖离率(MA20)</div>"
                            f"<div style='font-size:16px;font-weight:700;color:{_price_color(deviation)};'>"
                            f"{deviation:+.2f}%</div>", unsafe_allow_html=True)
            with k4:
                st.markdown("<div style='color:#94a3b8;font-size:12px;'>52周区间位置</div>"
                            f"<div style='font-size:16px;font-weight:700;color:#e2e8f0;'>{pos52:.0f}%</div>"
                            f"<div style='font-size:11px;color:#94a3b8;'>¥{lo52:.2f}~¥{hi52:.2f}</div>",
                            unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            # ════════════ 模块4：技术指标图表 ════════════
            st.markdown('<div class="sf-card"><h2>技术指标图表</h2>', unsafe_allow_html=True)
            st.markdown(
                Visualizer.kline_legend_html(ma_windows=[5, 10, 20]),
                unsafe_allow_html=True,
            )
            try:
                fig = Visualizer.candlestick(
                    df,
                    title="技术指标图表（K线 + 均线 + 成交量）",
                    show_volume=True,
                    ma_windows=[5, 10, 20],
                    support=support,
                    resistance=resistance,
                )
                st.plotly_chart(fig, use_container_width=True)
                # 图表下方说明：保留原标注样式，同时加入日期区间与参考线说明
                st.markdown(
                    "<div style='font-size:12px;color:#94a3b8;margin-top:4px;'>"
                    "绿柱为上涨、红柱为下跌（A股习惯）。"
                    f"虚线为 MA5/MA10/MA20；支撑线：¥{support:.2f}；压力线：¥{resistance:.2f}。"
                    f"数据区间 {df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}。"
                    "</div>",
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.warning(f"⚠️ K线图渲染失败：{str(e)[:80]}")
            st.markdown("</div>", unsafe_allow_html=True)

            # ════════════ 模块5：情报面 ════════════
            st.markdown('<div class="sf-card"><h2>情报面</h2>', unsafe_allow_html=True)
            st.markdown("<div style='color:#94a3b8;font-size:13px;margin-bottom:6px;'>"
                        f"新闻情绪分布：正面 {pos_pct:.0f}% ｜ 中性 {100-pos_pct-neg_pct:.0f}% ｜ 负面 {neg_pct:.0f}%</div>",
                        unsafe_allow_html=True)
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
            st.markdown('<div class="sf-card"><h2>信号归因 · 四维雷达</h2>', unsafe_allow_html=True)
            try:
                import plotly.graph_objects as go
                radar_fig = go.Figure()
                cats = ["技术指标", "新闻情绪", "资金量能", "市场环境"]
                vals = [tech_score, news_score, vol_score, macro_score]
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
                        radialaxis=dict(range=[0, 100], gridcolor="#2d2d44", tickfont=dict(color="#94a3b8")),
                        bgcolor="rgba(0,0,0,0)",
                        angularaxis=dict(gridcolor="#2d2d44", tickfont=dict(color="#e2e8f0")),
                    ),
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=380,
                    margin=dict(l=40, r=40, t=20, b=20),
                )
                st.plotly_chart(radar_fig, use_container_width=True)
            except Exception as e:
                st.warning(f"⚠️ 雷达图渲染失败：{str(e)[:80]}")

            # 权重表
            st.markdown(
                "<table class='sf-table'>"
                "<thead><tr><th class='l'>维度</th><th>权重</th><th>得分</th></tr></thead><tbody>"
                f"<tr><td class='l'>技术指标（价格/均线/动量）</td><td>35%</td><td>{tech_score:.0f}</td></tr>"
                f"<tr><td class='l'>新闻情绪（事件信号）</td><td>25%</td><td>{news_score:.0f}</td></tr>"
                f"<tr><td class='l'>资金量能（量价配合）</td><td>15%</td><td>{vol_score:.0f}</td></tr>"
                f"<tr><td class='l'>市场环境（PMI 宏观）</td><td>25%</td><td>{macro_score:.0f}</td></tr>"
                f"<tr><td class='l'><b>综合评分</b></td><td>100%</td><td><b>{composite}</b></td></tr>"
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
            st.markdown('<div class="sf-card"><h2>作战计划</h2>', unsafe_allow_html=True)
            st.markdown("<div style='color:#94a3b8;font-size:13px;'>支撑 → 压力 价格刻度</div>", unsafe_allow_html=True)
            st.markdown(_support_resistance_bar(support, resistance, current_price), unsafe_allow_html=True)

            st.markdown("<div style='color:#e2e8f0;font-weight:600;margin:14px 0 4px;'>分批建仓 / 减仓计划</div>",
                        unsafe_allow_html=True)
            plan_rows = [
                ("建仓①", f"回调至支撑区", f"¥{support:.2f}~¥{(support+current_price)/2:.2f}", "30%",
                 "首仓试探，确认支撑有效"),
                ("建仓②", "放量突破 MA20", f"¥{ma20:.2f}~¥{current_price:.2f}", "30%",
                 "趋势确认后加仓"),
                ("加仓", f"突破压力 ¥{target_price:.2f}", f"¥{target_price:.2f} 上方", "20%",
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

            st.markdown("<div style='color:#e2e8f0;font-weight:600;margin:14px 0 4px;'>风险控制清单</div>",
                        unsafe_allow_html=True)
            risk_items = [
                f"止损价：¥{stop_price:.2f}（破位无条件离场）",
                f"止盈价：¥{target_price:.2f}（到达分批兑现）",
                "失效条件：突发利空 / 放量跌穿支撑 / 宏观转弱（PMI<50）",
                "仓位纪律：单标的 ≤ 总仓位 30%，亏损单不补仓摊平",
            ]
            st.markdown("<ul style='color:#94a3b8;font-size:13px;line-height:1.9;'>"
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

        except Exception as e:
            import traceback as _tb
            st.error(f"分析生成失败：{e}")
            with st.expander("调试信息"):
                st.code(_tb.format_exc())
else:
    st.info("👈 在左侧选择股票后，点击「生成分析」查看完整的个股深度决策仪表盘。")
