"""
页面2：个股分析
暗色模式「决策仪表盘 · 个股深度分析」（参考 002947 暗色版 .sf-* 组件类）。

严格遵循参考文档「绿涨红跌」配色：涨/利好/买入 = 绿(#009e60)，跌/利空/卖出 = 红(#dc2626)，
中性/持有 = 琥珀(#d97706)。所有外部数据获取均包在 try/except 中，失败时 st.warning。
仅做前端/UI，不改动 backend 或任何数据逻辑。
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# ── 前置：本页「星辰决策仪表盘」跟随全局主题（右上角开关可切暗夜 / 白天）──
from modules.ui_theme import apply_page_config
from modules.page_guard import safe_fragment

apply_page_config(page_title="个股分析", page_icon="🔍", layout="wide")
st.session_state["_active_page"] = __file__

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.visualizer import Visualizer
from modules.session import require_auth, render_user_badge, api_kline
from modules.search_ui import stock_search_input
from modules.ui_theme import dashboard_sf_css, _theme_is_dark
from modules.background_tasks import submit_task_with_error, poll_task
from modules.page_widgets import _empty_info
from streamlit_autorefresh import st_autorefresh

# 配色常量 + UI/计算纯函数簇已抽到 modules/stock_analysis_helpers（#408 拆分超大文件）。
# 参考文档 002947「绿涨红跌」配色随常量一并迁移，页面行为完全不变。
from modules.stock_analysis_helpers import (
    RED, GREEN, AMBER,
    _sentiment_tag, _tp_cls, _score_ring_html,
    _battle_plan_scale, _build_risk_iron_rules,
    _risk_iron_html, _build_plan_rows, _section_header, _build_rise_fall_factors,
    _factor_list_html, _build_logic_lists, _logic_list_html,
)

require_auth()
render_user_badge(sidebar=True)
st.title("🔍 个股深度分析 · 决策仪表盘")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


# ══════════════════════════════════════════════════════════════
# 股票选择（侧边栏；嵌入合并页时自动改写入主区域，避免覆盖导航）
# ══════════════════════════════════════════════════════════════
from modules.widgets import sidebar_target
with sidebar_target():
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

# ══════════════════════════════════════════════════════════════
# 分析渲染：从 dict 中恢复所有变量并绘制 8 大模块
# ══════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False, ttl=300)
def _cached_period_kline(ticker: str, start: str, end: str, period: str):
    """#78 周/月 K 线数据（复用 1_股票选取.py 已验证的取数模式）。"""
    recs = api_kline(ticker, start=start, end=end, period=period)
    if recs is None:
        return StockFetcher().get_kline(ticker, start=start, end=end, period=period)
    return pd.DataFrame(recs)


def _render_analysis(R: dict):
    # 把结果字典展开到局部作用域，保持原渲染代码基本不变
    ticker = R["ticker"]
    display_name = R["display_name"]
    industry = R["industry"]
    current_price = R["current_price"]
    prev_close = R["prev_close"]
    change_pct = R["change_pct"]
    df = R["df"]
    trend = R["trend"]
    momentum = R["momentum"]
    volume_info = R["volume_info"]
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
    lo52 = R["lo52"]
    hi52 = R["hi52"]
    pos52 = R["pos52"]
    ma5v = R["ma5v"]
    ma10v = R["ma10v"]
    ma20v = R["ma20v"]
    trapped = R["trapped"]
    vol_now = R["vol_now"]
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
    st.markdown('<div class="sf-card">' + _section_header("顶部决策摘要", "🎯"), unsafe_allow_html=True)
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
            f"<div style='font-size:23px;font-weight:700;color:var(--txt);'>{display_name}</div>"
            f"<div style='font-size:12.5px;color:var(--txt2);margin-top:3px;'>"
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
        f"<div style='margin-top:14px;border-left:4px solid var(--acc1);background:var(--card2);"
        f"border-radius:0 12px 12px 0;padding:12px 16px;font-size:13.5px;color:var(--txt2);line-height:1.7;'>"
        f"<b style='color:var(--txt);'>📌 仓位建议：</b>{position_advice}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块2：核心结论（视觉强化）══════════
    st.markdown('<div class="sf-card">' + _section_header("核心结论", "AI 综合研判 · 多空信号", "💡"), unsafe_allow_html=True)
    trend_label = trend.get("trend_label", "—") if "error" not in trend else "数据不足"
    mom_label = momentum.get("momentum_label", "—") if "error" not in momentum else "—"
    vol_label = volume_info.get("volume_price_label", "—") if "error" not in volume_info else "—"
    one_line = (
        f"{display_name} 现价 ¥{current_price:.2f}（{chg_txt}），技术面「{trend_label}」、"
        f"动量「{mom_label}」、量能「{vol_label}」；新闻情绪正面占比 {pos_pct:.0f}%，"
        f"综合研判 <b>{verdict}</b>。"
    )
    st.markdown(
        f"<div style='border-radius:14px;padding:18px 20px;"
        f"background:linear-gradient(135deg, {verdict_color}22, {verdict_color}08);"
        f"border:1px solid {verdict_color}55;'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;'>"
        f"<div style='font-size:22px;font-weight:800;color:{verdict_color};'>{verdict} · {display_name}</div>"
        f"<span class='sf-tag {verdict_cls}' style='font-size:13px;padding:5px 14px;'>{badge_text}</span>"
        f"</div>"
        f"<div style='margin-top:10px;font-size:14px;color:var(--txt);line-height:1.8;'>{one_line}</div>"
        f"<div style='margin-top:12px;display:flex;flex-wrap:wrap;gap:8px;'>"
        f"<span class='sf-tag neu'>综合评分 {composite}</span>"
        f"<span class='sf-tag {verdict_cls}'>信号 · {verdict}</span>"
        f"<span class='sf-tag neu'>策略 · {'分批建仓' if verdict=='看多' else ('逢高减仓' if verdict=='看空' else '区间波段')}</span>"
        f"<span class='sf-tag neu'>适用 · 事件驱动 / 中短线</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块2.5：综合信息（舆情 / 评分 / 五维 / 关联板块 / 股评）══════════
    st.markdown('<div class="sf-card">' + _section_header("综合信息", "舆情 · 评分 · 五维 · 关联板块", "🧩"), unsafe_allow_html=True)
    _sec = sector_analysis or {}
    _sec_name = _sec.get("name") or industry or "—"
    _sec_chg = _sec.get("change_pct")
    _sec_chg_txt = f"{_sec_chg:+.2f}%" if isinstance(_sec_chg, (int, float)) else "—"
    _sec_rank = _sec.get("rank")
    _sec_total = _sec.get("total")
    _sec_rank_txt = f"{_sec_rank}/{_sec_total}" if isinstance(_sec_rank, (int, float)) and isinstance(_sec_total, (int, float)) else "—"
    st.markdown(
        "<div class='sf-grid-4'>"
        "<div class='sf-perspective-card'>"
        f"<div class='title'>舆情热度（近 {len(news_rows)} 条）</div>"
        "<div class='body'>"
        f"<span style='color:var(--buy);font-weight:700;'>正面 {pos_pct:.0f}%</span> / "
        f"<span style='color:var(--sell);font-weight:700;'>负面 {neg_pct:.0f}%</span>"
        "<div style='margin-top:8px;height:8px;border-radius:4px;background:var(--sell);overflow:hidden;'>"
        f"<div style='height:100%;width:{pos_pct:.0f}%;background:var(--buy);'></div></div>"
        "</div></div>"
        "<div class='sf-perspective-card'>"
        "<div class='title'>综合评分</div>"
        "<div class='body' style='display:flex;align-items:baseline;gap:8px;'>"
        f"<span style='font-size:30px;font-weight:800;color:{verdict_color};'>{composite}</span>"
        f"<span class='sf-tag {verdict_cls}'>{verdict}</span>"
        "</div></div>"
        "<div class='sf-perspective-card'>"
        "<div class='title'>五维评分拆解</div>"
        "<div class='body'>"
        f"<span class='sf-pill {_tp_cls(tech_score)}'>技术 {tech_score}</span>"
        f"<span class='sf-pill {_tp_cls(news_score)}'>舆情 {news_score}</span>"
        f"<span class='sf-pill {_tp_cls(vol_score)}'>量能 {vol_score}</span>"
        f"<span class='sf-pill {_tp_cls(macro_score)}'>宏观 {macro_score}</span>"
        f"<span class='sf-pill {_tp_cls(sector_score)}'>板块 {sector_score}</span>"
        "</div></div>"
        "<div class='sf-perspective-card'>"
        f"<div class='title'>关联板块 · {board or '—'}</div>"
        "<div class='body'>"
        f"{industry or '—'} · {_sec_name}<br>"
        f"板块涨跌 {_sec_chg_txt} · 排名 {_sec_rank_txt}"
        "</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='margin-top:12px;font-size:13px;color:var(--txt2);line-height:1.7;'>"
        f"<b style='color:var(--txt);'>📝 股评：</b>技术面 {tech_score} 分、舆情 {news_score} 分、"
        f"量能 {vol_score} 分、宏观 {macro_score} 分、板块 {sector_score} 分，"
        f"综合研判 <b>{verdict}</b>，建议{'分批建仓' if verdict=='看多' else ('逢高减仓' if verdict=='看空' else '区间波段')}。"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════ 模块3：数据透视 ════════════
    st.markdown('<div class="sf-card">' + _section_header("数据透视", "量价 / 筹码 / 位置 / 乖离", "📊"), unsafe_allow_html=True)
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

    # ── #78 K线周期切换：日K / 周K / 月K ──
    _period_opts = ["daily", "weekly", "monthly"]
    kline_period = st.radio(
        "K线周期",
        options=_period_opts,
        index=_period_opts.index(st.session_state.get(f"kline_period_{ticker}", "daily")),
        format_func=lambda p: {"daily": "日 K", "weekly": "周 K", "monthly": "月 K"}[p],
        horizontal=True,
        key=f"kline_period_radio_{ticker}",
        help="切换 K 线周期：日线 / 周线 / 月线",
    )
    st.session_state[f"kline_period_{ticker}"] = kline_period

    # ── K线标题：代码 + 名称 + 周期（如「000504 南华生物 日K线」）──
    period_label = {"daily": "日K线", "weekly": "周K线", "monthly": "月K线"}[kline_period]
    kline_title = f"{ticker} {display_name} {period_label}"

    # ── #393 日期范围选择器：自定义 K 线起止日期（开始 / 结束）──
    _dr_key = f"kline_daterange_{ticker}"
    if _dr_key not in st.session_state:
        st.session_state[_dr_key] = (datetime(2020, 1, 1), datetime.now())
    _dr = st.date_input(
        "K线日期范围（开始 / 结束）",
        value=st.session_state[_dr_key],
        max_value=datetime.now(),
        key=f"kline_daterange_input_{ticker}",
        help="选定开始与结束日期，按自定义区间查看 K 线（日线直接筛选；周/月线按区间重新拉取）",
    )
    _kstart, _kend = "2020-01-01", datetime.now().strftime("%Y-%m-%d")
    if isinstance(_dr, (tuple, list)) and len(_dr) == 2:
        st.session_state[_dr_key] = _dr
        try:
            _kstart = _dr[0].strftime("%Y-%m-%d")
            _kend = _dr[1].strftime("%Y-%m-%d")
        except Exception:
            pass

    # 选定周期的 K 线数据：日线直接用分析结果 df（按日期范围筛选）；周/月线重新拉取并归一化列名
    if kline_period == "daily":
        period_df = df
        try:
            _dmask = (pd.to_datetime(period_df["date"]) >= _kstart) & (pd.to_datetime(period_df["date"]) <= _kend)
            _filtered = period_df[_dmask]
            if not _filtered.empty:
                period_df = _filtered
        except Exception:
            pass
    else:
        _kdf = _cached_period_kline(ticker, _kstart, _kend, kline_period)
        if _kdf is None or _kdf.empty:
            period_df = df
        else:
            period_df = DataCleaner.full_pipeline(_kdf.copy())

    try:
        # 参考文档 002947：绿涨红跌、MA5橙/MA10靛/MA20绿、
        # 标注 MA20压制(红虚) / MA10(靛虚) / 前低支撑(绿虚) / 套牢区(琥珀点)
        # 仅日线视图展示基于日线计算的价位标注；周/月线不再套用日线价位
        kline_annotations = [
            {"price": ma20v, "label": "MA20压制", "color": GREEN, "dash": "dash"},
            {"price": ma10v, "label": "MA10", "color": "#667eea", "dash": "dash"},
            {"price": support, "label": "前低支撑", "color": RED, "dash": "dash"},
            {"price": trapped, "label": "套牢区", "color": AMBER, "dash": "dot"},
        ] if kline_period == "daily" else None
        fig = Visualizer.candlestick(
            period_df,
            title=kline_title,
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
        _date_min = pd.to_datetime(period_df['date']).min().strftime('%Y-%m-%d')
        _date_max = pd.to_datetime(period_df['date']).max().strftime('%Y-%m-%d')
        _cap = (
            "<div style='font-size:12px;color:#64748b;margin-top:4px;'>"
            "绿柱为上涨、红柱为下跌（参考文档配色）。"
            "均线 MA5(橙)/MA10(靛)/MA20(绿)；"
        )
        if kline_period == "daily":
            _cap += (
                f"标注线：MA20压制 ¥{ma20v:.2f} / MA10 ¥{ma10v:.2f} / "
                f"前低支撑 ¥{support:.2f} / 套牢区 ¥{trapped:.2f}。"
            )
        else:
            _cap += f"当前为{'周线' if kline_period == 'weekly' else '月线'}视图，均线为对应周期数值。"
        _cap += f"数据区间 {_date_min} ~ {_date_max}。</div>"
        st.markdown(_cap, unsafe_allow_html=True)
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
        _empty_info("暂无新闻数据（网络不可用或该标的无公开新闻）")

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

    # ════════════ 新增模块：利好/利空清单（按强度）════════════
    rise_factors, fall_factors = _build_rise_fall_factors(R)
    col_rise, col_fall = st.columns(2)
    with col_rise:
        st.markdown(_factor_list_html("利好清单（全集）", rise_factors), unsafe_allow_html=True)
    with col_fall:
        st.markdown(_factor_list_html("利空清单（全集）", fall_factors), unsafe_allow_html=True)

    # ════════════ 新增模块：多空逻辑与致命风险 ════════════
    rise_logic, fall_logic, fatal_logic = _build_logic_lists(R)
    col_logic_r, col_logic_f = st.columns(2)
    with col_logic_r:
        st.markdown(_logic_list_html("利好逻辑", rise_logic, RED, "🐂"), unsafe_allow_html=True)
    with col_logic_f:
        st.markdown(_logic_list_html("利空逻辑", fall_logic, GREEN, "🐻"), unsafe_allow_html=True)
    if fatal_logic:
        st.markdown(_logic_list_html("致命风险（必须盯死）", fatal_logic, "#ef4444", "⚠️"), unsafe_allow_html=True)

    # ════════════ 模块6：信号归因（四维雷达）══════════
    # ══════════ 新增模块：板块分析 ══════════
    st.markdown('<div class="sf-card">' + _section_header("板块分析", "主板块定位 · 实时走势 · 同板块对比", "📊"), unsafe_allow_html=True)
    _sa_name = sector_analysis.get("name", "—")
    _sa_full = sector_analysis.get("full_name", _sa_name)
    _sa_chg = sector_analysis.get("change_pct")
    _sa_label = sector_analysis.get("label", "—")
    _sa_rank = sector_analysis.get("rank")
    _sa_total = sector_analysis.get("total")
    _sa_chg_txt = f"{_sa_chg:+.2f}%" if _sa_chg is not None else "—"
    _sa_chg_color = RED if (_sa_chg or 0) > 0 else (GREEN if (_sa_chg or 0) < 0 else AMBER)
    _sa_rank_txt = f"全市场第 {_sa_rank}/{_sa_total} 强" if (_sa_rank and _sa_total) else "—"

    # 板块行情判断
    if _sa_chg is None:
        _market_verdict = "暂无板块行情数据"
        _market_detail = (
            f"主板块「{_sa_name}」暂无实时涨跌数据，无法判断板块是否有行情。"
            "建议结合大盘与五维雷达综合判断。"
        )
    else:
        if _sa_chg >= 2.0:
            _market_strength, _has_boom = "强势上涨", "板块行情明确"
        elif _sa_chg >= 1.0:
            _market_strength, _has_boom = "偏强运行", "板块有温和行情"
        elif _sa_chg >= -1.0:
            _market_strength, _has_boom = "横盘震荡", "板块暂无单边行情"
        elif _sa_chg >= -2.0:
            _market_strength, _has_boom = "偏弱调整", "板块处于调整"
        else:
            _market_strength, _has_boom = "弱势下跌", "板块行情较差"
        if _sa_rank and _sa_total:
            _pct = _sa_rank / _sa_total * 100
            if _pct <= 10:
                _rank_desc = "板块热度处于全市场前 10%（头部）"
            elif _pct <= 30:
                _rank_desc = "板块热度处于全市场前 30%（中上）"
            elif _pct <= 70:
                _rank_desc = "板块热度处于全市场中游"
            else:
                _rank_desc = "板块热度处于全市场后 30%（落后）"
        else:
            _rank_desc = "暂无全市场排名"
        _market_verdict = f"{_has_boom}：{_sa_name} {_market_strength}（{_sa_chg_txt}），{_rank_desc}。"
        _market_detail = f"该主线属于「{_sa_full}」，实时涨跌幅 {_sa_chg_txt}，{_sa_rank_txt}。"

    # 个股在板块中的位置 + 相对强弱
    _peer_rank = sector_analysis.get("peer_rank")
    _peer_total = sector_analysis.get("peer_total")
    _peer_avg = sector_analysis.get("peer_avg_change")
    _peer_median = sector_analysis.get("peer_median_change")
    _is_leader = sector_analysis.get("is_leader", False)
    _top_peers = sector_analysis.get("top_peers", [])
    _better_peers = sector_analysis.get("better_peers", [])

    if _peer_rank and _peer_total:
        _peer_pct = _peer_rank / _peer_total * 100
        if _peer_pct <= 10:
            _position_desc = "板块龙头/前排"
        elif _peer_pct <= 30:
            _position_desc = "板块中上游"
        elif _peer_pct <= 70:
            _position_desc = "板块中游"
        else:
            _position_desc = "板块后排"
        _position_txt = f"{display_name} 在 {_sa_name} 板块 {_peer_total} 只个股中排名第 {_peer_rank}，处于{_position_desc}。"
        if _is_leader:
            _position_txt = f"{display_name} 是 {_sa_name} 板块涨幅龙头，板块内共 {_peer_total} 只个股。"
    else:
        _position_txt = f"暂无 {display_name} 在 {_sa_name} 板块内的排名数据。"

    if _peer_avg is not None:
        _rel = (change_pct or 0) - _peer_avg
        _rel_txt = f"{_rel:+.2f}%"
        if _rel >= 2.0:
            _rel_desc = "明显强于板块"
        elif _rel > 0:
            _rel_desc = "强于板块"
        elif _rel > -2.0:
            _rel_desc = "弱于板块"
        else:
            _rel_desc = "明显弱于板块"
        _position_txt += f" 相对板块平均涨跌幅（{_peer_avg:+.2f}%）{_rel_desc} {_rel_txt}。"
    if _peer_median is not None:
        _position_txt += f" 板块中位数涨跌幅 {_peer_median:+.2f}%。"

    def _fmt_cap(v):
        try:
            v = float(v)
            if v >= 1e8:
                return f"{v / 1e8:.1f}亿"
            return f"{v:.1f}亿"
        except Exception:
            return "—"

    def _peer_row(p, idx=None, show_rank=False):
        code = str(p.get("code", "")).zfill(6)
        name = p.get("name", "")
        chg = p.get("change_pct")
        cap = p.get("market_cap")
        chg_txt = f"{chg:+.2f}%" if chg is not None else "—"
        color = RED if (chg or 0) > 0 else (GREEN if (chg or 0) < 0 else AMBER)
        cap_txt = _fmt_cap(cap) if cap is not None else "—"
        rank_cell = f"<td style='padding:6px 8px;font-size:13px;color:var(--txt2);text-align:center;width:36px;'>{idx}</td>" if show_rank else ""
        return (
            f"<tr>{rank_cell}"
            f"<td style='padding:6px 8px;font-size:13px;color:var(--txt);'>{code}</td>"
            f"<td style='padding:6px 8px;font-size:13px;color:var(--txt);'>{name}</td>"
            f"<td style='padding:6px 8px;font-size:13px;font-weight:600;color:{color};'>{chg_txt}</td>"
            f"<td style='padding:6px 8px;font-size:12px;color:var(--txt2);text-align:right;'>{cap_txt}</td>"
            f"</tr>"
        )

    _html = (
        f'<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:12px;">'
        f'<div style="font-size:18px;font-weight:700;color:var(--txt);">{_sa_name}</div>'
        f'<span class="sf-pill {_tp_cls(sector_score)}">板块强度 {sector_score}</span>'
        f'<span style="font-size:14px;font-weight:600;color:{_sa_chg_color};">{_sa_chg_txt} {_sa_label}</span>'
        f'<span class="sf-pill mid">{_sa_rank_txt}</span>'
        f"</div>"
        f'<div style="font-size:13.5px;color:var(--txt2);line-height:1.7;margin-bottom:12px;">'
        f'<b style="color:var(--txt);">板块行情：</b>{_market_verdict}<br>{_market_detail}'
        f"</div>"
        f'<div style="font-size:13.5px;color:var(--txt2);line-height:1.7;margin-bottom:16px;">'
        f'<b style="color:var(--txt);">个股定位：</b>{_position_txt}'
        f"</div>"
    )

    if _top_peers:
        rows = "".join(_peer_row(p, i + 1) for i, p in enumerate(_top_peers[:5]))
        _html += (
            f'<div style="font-size:13px;font-weight:600;color:var(--txt);margin-bottom:8px;">🏆 板块领涨 TOP5</div>'
            f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">'
            f'<thead><tr style="border-bottom:1px solid var(--border);">'
            f'<th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">代码</th>'
            f'<th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">名称</th>'
            f'<th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">涨跌幅</th>'
            f'<th style="padding:6px 8px;text-align:right;font-size:12px;color:var(--txt2);font-weight:600;">总市值</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    if _better_peers:
        rows = "".join(_peer_row(p, i + 1, show_rank=True) for i, p in enumerate(_better_peers[:5]))
        _html += (
            f'<div style="font-size:13px;font-weight:600;color:var(--txt);margin-bottom:8px;">'
            f'⚡ 比 {display_name} 更强的同板块个股</div>'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr style="border-bottom:1px solid var(--border);">'
            f'<th style="padding:6px 8px;text-align:center;font-size:12px;color:var(--txt2);font-weight:600;width:36px;">排名</th>'
            f'<th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">代码</th>'
            f'<th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">名称</th>'
            f'<th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">涨跌幅</th>'
            f'<th style="padding:6px 8px;text-align:right;font-size:12px;color:var(--txt2);font-weight:600;">总市值</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    elif _peer_rank and _peer_rank == 1:
        _html += (
            f'<div style="font-size:13px;color:var(--txt2);margin-top:8px;">'
            f'✅ {display_name} 当前为该板块涨幅第一，暂无同板块个股比它更强。'
            f"</div>"
        )

    st.markdown(_html, unsafe_allow_html=True)
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
        # ★ 交付包 v4 · 功能 D：暗夜模式雷达坐标轴文字/网格可见性修复。
        # 复用 canonical 配色（暗夜 polar 轴 tickfont=#94a3b8，不再用 #1e293b 深字），
        # 套用后保留卡片透明底，与 .sf-card 深空背景一致。
        from modules.dark_text_fix import apply_plotly_theme
        dark = _theme_is_dark()
        apply_plotly_theme(radar_fig, dark=dark)
        radar_fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
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
    st.markdown('<div class="sf-card">' + _section_header("作战计划", "⚔️"), unsafe_allow_html=True)
    st.markdown(
        _battle_plan_scale(
            support, resistance, current_price, target_price, stop_price, entry_price, verdict,
        ),
        unsafe_allow_html=True,
    )

    plan_rows = _build_plan_rows(
        verdict, current_price, support, resistance, target_price, stop_price, entry_price, ma20v,
    )
    a_tag = "up" if verdict == "看多" else ("down" if verdict == "看空" else "mid")
    b_tag = "neu"
    rows_html = "".join(
        f"<tr><td><span class='sf-tag {a_tag if i==0 else b_tag}'>{r[0]}</span></td>"
        f"<td class='l'>{r[1]}</td><td>{r[2]}</td>"
        f"<td>{r[3]}</td><td class='l'>{r[4]}</td></tr>"
        for i, r in enumerate(plan_rows)
    )
    st.markdown(
        "<table class='sf-table'>"
        "<thead><tr><th>方案</th><th class='l'>触发条件</th><th>入场</th>"
        "<th>止损</th><th class='l'>目标</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='color:var(--txt);font-weight:600;margin:14px 0 4px;'>风控清单</div>",
        unsafe_allow_html=True,
    )
    col_risk, col_iron = st.columns(2)
    with col_risk:
        risk_items = [
            f"止损价：¥{stop_price:.2f}（破位无条件离场）",
            f"止盈价：¥{target_price:.2f}（到达分批兑现）",
            "失效条件：突发利空 / 放量跌穿支撑 / 宏观转弱（PMI<50）",
            "仓位纪律：单标的 ≤ 总仓位 30%，亏损单不补仓摊平",
        ]
        st.markdown(
            "<ul style='color:var(--txt2);font-size:13px;line-height:1.9;'>"
            + "".join(f"<li>{x}</li>" for x in risk_items) + "</ul>",
            unsafe_allow_html=True,
        )
    with col_iron:
        st.markdown(
            _risk_iron_html("风险铁律", _build_risk_iron_rules(R)),
            unsafe_allow_html=True,
        )
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
st.caption("💡 分析包含行情 / 新闻 / 技术 / 评分等模块，首次生成约需 10–30 秒，后台运行期间可浏览其它页面。")


@st.cache_data(ttl=1)
def _poll_analysis_once(task_id: str) -> dict | None:
    """缓存 1 秒：避免同一次 fragment 重跑中多次调用 poll_task 造成请求堆积。"""
    return poll_task(task_id, max_wait=0.5)


@safe_fragment
def fragment_analysis_result():
    """分析结果区：包含轮询、加载中反馈、完成后渲染，独立 fragment 不阻塞整页。"""
    analysis_task_id = st.session_state.get("analysis_task_id")
    if analysis_task_id:
        # 使用 1 秒缓存避免轮询时连续请求堆积
        task = _poll_analysis_once(analysis_task_id)
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
            st.warning(
                "⏳ 分析正在后台并行运行：行情数据 → 新闻舆情 → 技术信号 → 综合评分。"
                "完成后会自动显示下方结果，无需切换页面。",
                icon="⏳",
            )
            st.progress(0.0, text="等待分析结果...")
            st_autorefresh(interval=1000, limit=30, key="analysis_autorefresh")
            return

    if st.session_state.get("analysis_result") is not None:
        _render_analysis(st.session_state["analysis_result"])
    else:
        st.info("👈 在左侧选择股票后，点击「生成分析」查看完整的个股深度决策仪表盘。")
        st.caption("💡 也可以直接点击下方按钮生成分析；任务在后台并行运行，完成后自动显示，无需等待。")
        if st.button("🔍 生成深度分析", type="primary", key="gen_analysis_inline", use_container_width=True):
            if not ticker:
                st.warning("请先在上方「⚡ 快速选取」选择一只股票，再回到「🔬 深度分析」点击「生成分析」查看完整决策仪表盘。")
            else:
                tid, e = submit_task_with_error("analysis", {"ticker": ticker})
                if tid:
                    st.session_state["analysis_task_id"] = tid
                    st.session_state["analysis_result"] = None
                else:
                    st.error(f"❌ 后台任务提交失败：{e or '未知错误'}，请刷新重试。")


fragment_analysis_result()


# ══════════════════════════════════════════════════════════════
# #396 相关视频：把互联网上相关的股票视频「接到项目里」
# 方案：① 按股票名生成各大视频平台搜索直达链接；② 支持粘贴视频地址内联嵌入播放。
# ══════════════════════════════════════════════════════════════
def _video_embed_url(url: str):
    """把常见视频分享链接转换为可嵌入的 iframe src；不支持则返回 None。"""
    import re
    if not url:
        return None
    url = url.strip()
    # YouTube
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{6,})", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    # Bilibili
    m = re.search(r"bilibili\.com/video/(BV[\w]+)", url)
    if m:
        return f"https://player.bilibili.com/player.html?bvid={m.group(1)}&autoplay=0&high_quality=1"
    # 腾讯视频
    m = re.search(r"v\.qq\.com/x/cover/\w+/([\w]+)\.html", url)
    if m:
        return f"https://v.qq.com/txp/iframe/player.html?vid={m.group(1)}"
    return None


@safe_fragment
def fragment_stock_videos(ticker):
    with st.expander("📺 相关视频（把互联网上的股票视频接入项目 · 点击展开/收起）", expanded=False, key="stock_video_exp"):
        name = StockFetcher().get_stock_name(ticker) or ticker
    q = f"{name} 股票分析"
    from urllib.parse import quote
    links = [
        ("🅑️ B站", f"https://search.bilibili.com/all?keyword={quote(q)}"),
        ("🔍 百度视频", f"https://www.baidu.com/s?tn=baiduvi&wd={quote(q)}"),
        ("▶️ YouTube", f"https://www.youtube.com/results?search_query={quote(q)}"),
        ("🎵 抖音", f"https://www.douyin.com/search/{quote(q)}"),
    ]
    st.caption(f"「{name}」相关视频聚合（点击在浏览器新标签打开对应平台搜索结果）：")
    _lc = st.columns(len(links))
    for i, (label, href) in enumerate(links):
        with _lc[i]:
            st.markdown(f'<a href="{href}" target="_blank" style="display:block;text-align:center;'
                        f'padding:8px 4px;border:1px solid var(--border);border-radius:10px;'
                        f'text-decoration:none;color:var(--txt);font-weight:600;">{label}</a>',
                        unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**🔗 粘贴视频地址，内联嵌入播放**（支持 YouTube / B站 / 腾讯视频 分享链接）：")
    vk = f"video_embed_{ticker}"
    if vk not in st.session_state:
        st.session_state[vk] = []
    with st.form(key=f"video_form_{ticker}", clear_on_submit=True):
        video_url = st.text_input("视频链接（如 https://www.bilibili.com/video/BVxxxx 或 YouTube 链接）", "")
        submitted = st.form_submit_button("➕ 添加到本股视频", use_container_width=True)
        if submitted and video_url:
            emb = _video_embed_url(video_url)
            if emb:
                st.session_state[vk].append({"src": emb, "raw": video_url})
            else:
                st.warning("⚠️ 暂仅支持 YouTube / B站 / 腾讯视频 的嵌入；其它平台已为你保留原链接，可点击观看。")
                st.session_state[vk].append({"src": None, "raw": video_url})
    # 展示已嵌入视频
    if st.session_state[vk]:
        for idx, v in enumerate(st.session_state[vk]):
            col_player, col_del = st.columns([0.92, 0.08])
            with col_player:
                if v["src"]:
                    st.components.v1.html(
                        f'<iframe src="{v["src"]}" scrolling="no" border="0" frameborder="no" '
                        f'framespacing="0" allowfullscreen="true" '
                        f'style="width:100%;height:380px;border-radius:12px;"></iframe>',
                        height=400,
                    )
                else:
                    st.markdown(f'🔗 <a href="{v["raw"]}" target="_blank">{v["raw"]}</a>', unsafe_allow_html=True)
            with col_del:
                _ck = f"vdel_cfm_{ticker}_{idx}"
                if st.session_state.get(_ck):
                    if st.button("确认", key=f"vdel_cfm_btn_{ticker}_{idx}", type="primary", use_container_width=True):
                        st.session_state[vk].pop(idx)
                        st.session_state.pop(_ck, None)
                    if st.button("取消", key=f"vdel_cancel_{ticker}_{idx}", use_container_width=True):
                        st.session_state.pop(_ck, None)
                else:
                    if st.button("✕", key=f"vdel_{ticker}_{idx}", use_container_width=True, help="移除"):
                        st.session_state[_ck] = True
    else:
        _empty_info("尚未添加视频。粘贴上方链接即可把网络视频「接到」本股票分析页内联播放")
        st.caption("💡 也可以直接点击下方按钮展开「粘贴视频地址」输入框，把 YouTube / B站 / 腾讯视频 接入本页内联播放。")
        if st.button("➕ 展开添加视频", key="video_empty_add"):
            st.session_state["stock_video_exp"] = True


fragment_stock_videos(ticker)
