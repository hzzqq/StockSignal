"""
modules/widgets.py
------------------
跨页面复用的 Streamlit 小组件：
  - render_global_search  侧边栏全局股票搜索
  - render_theme_toggle   侧边栏深色/浅色快速切换
  - render_notifications  侧边栏通知中心
  - render_breadcrumb     页面面包屑
  - password_strength      密码强度评估（注册用）
"""

from __future__ import annotations

from typing import Any, Dict
from datetime import datetime
import time
import requests
import streamlit as st
import streamlit.components.v1 as components

from modules.session import API_BASE, get_token, safe_switch_page, persist_prefs


# ──────────────────────────────────────────────────────────────
# 星辰 AI 内联 SVG logo（科技感 + 金融感）
#   设计：金色四射星芒(星) + 上行股价折线(K线/价格) + 紫色数据轨道
#   配色：#667eea / #764ba2 品牌色，#f5c542 表现"星"
#   固定高对比色，深底(#0f0f23)/浅底(#ffffff)均清晰可读，无外部依赖
# ──────────────────────────────────────────────────────────────
def STAR_AI_LOGO(size: int = 20) -> str:
    """返回「星辰 AI」内联 SVG（可直接 unsafe_allow_html 渲染）。

    size 控制高/宽像素；vertical-align:middle 使其与同行文字基线对齐。
    """
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 32 32" fill="none" '
        f'style="vertical-align:middle;flex-shrink:0;display:inline-block" '
        f'role="img" aria-label="星辰 AI">'
        # 数据轨道（卫星环绕感）
        f'<ellipse cx="16" cy="16" rx="13" ry="5.5" transform="rotate(-32 16 16)" '
        f'stroke="#764ba2" stroke-width="1.4" opacity="0.65"/>'
        # 上行股价折线（K线/价格趋势）
        f'<polyline points="3,24 9,19 13,21 18,13 22,15 28,6" fill="none" '
        f'stroke="#667eea" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>'
        # 折线顶点的数据节点
        f'<circle cx="28" cy="6" r="2" fill="#667eea"/>'
        # 金色四射星芒（"星"）
        f'<path d="M16 6 C16.7 12.3 19.7 15.3 26 16 C19.7 16.7 16.7 19.7 16 26 '
        f'C15.3 19.7 12.3 16.7 6 16 C12.3 15.3 15.3 12.3 16 6 Z" fill="#f5c542"/>'
        f'</svg>'
    )


# ──────────────────────────────────────────────────────────────
# 三大指数迷你行情卡片（行情看板 / 每日晨报顶部）
# ──────────────────────────────────────────────────────────────
_INDEX_INFOS = [
    {"name": "上证指数", "code": "000001", "label": "指数"},
    {"name": "深证成指", "code": "399001", "label": "指数"},
    {"name": "创业板指", "code": "399006", "label": "指数"},
]


def _index_market_status():
    """返回指数是否需要自动刷新：(is_open, status_text, refresh_ms)。"""
    from datetime import datetime, time
    now = datetime.now()
    t = now.time()
    weekday = now.weekday()
    if weekday >= 5:
        return False, "⚪ 已休市（周末）", 0
    am_start, am_end = time(9, 25), time(11, 30)
    pm_start, pm_end = time(13, 0), time(15, 5)
    if am_start <= t <= am_end:
        return True, "🟢 交易中", 60 * 1000
    if pm_start <= t <= pm_end:
        return True, "🟢 交易中", 60 * 1000
    return False, "⚪ 已休市", 0


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Plotly 不接受 #RRGGBBAA，转 rgba。"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _index_cache_key() -> str:
    """生成指数缓存键，按分钟粒度，避免每秒 rerun 都重新请求。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _trend_label(open_: float, high: float, low: float, close: float, prev_close: float) -> str:
    """根据当日 OHLC 给出一句可读的走势定性（如高开低走/低开高走）。"""
    if not all([open_, high, low, close, prev_close]) or prev_close == 0:
        return "—"
    amplitude = (high - low) / prev_close * 100
    if amplitude < 0.15:
        return "窄幅震荡"
    if close >= open_:
        if high > close and (high - open_) / prev_close * 100 > 0.2:
            return "冲高回落"
        if open_ > prev_close:
            return "高开高走"
        if open_ < prev_close:
            return "低开高走"
        return "平开高走"
    else:
        if low < close and (open_ - low) / prev_close * 100 > 0.2:
            return "探底回升"
        if open_ > prev_close:
            return "高开低走"
        if open_ < prev_close:
            return "低开低走"
        return "平开低走"


def render_index_mini_cards(cols_per_row: int = 3) -> None:
    """在页面顶部渲染上证/深证/创业板的实时指数迷你趋势卡片（1:1 列表式）。

    每行包含：左侧指数名称+代码、中间当天/近期走势 sparkline、右侧最新点位+涨跌额+涨跌幅。
    数据源优先新浪财经实时接口（1 分钟级），历史走势由本地指数日线补齐；交易日自动刷新。
    折线颜色按当日涨跌红/绿显示，与 A 股习惯一致（红涨绿跌）。
    """
    import pandas as pd
    import plotly.graph_objects as go
    from datetime import datetime, timedelta
    from modules.fetcher import StockFetcher
    from modules.visualizer import UP_COLOR, DOWN_COLOR
    from modules.ui_theme import _theme_is_dark

    # 自动刷新：交易时间 60s 后台更新，不影响页面状态（st_autorefresh 保持 session_state）
    try:
        from streamlit_autorefresh import st_autorefresh
        is_open, _, refresh_ms = _index_market_status()
        if refresh_ms > 0:
            st_autorefresh(interval=refresh_ms, key="index_autorefresh")
    except Exception:
        pass

    fetcher = StockFetcher()
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime("%Y-%m-%d")
    today_str = end_date.strftime("%Y-%m-%d")

    # 分钟级缓存：同一分钟内不重复请求新浪/数据库，避免每个页面切换都拉数据
    cache_key = f"index_cards_{_index_cache_key()}"
    if cache_key in st.session_state:
        cards = st.session_state[cache_key]
    else:
        cards = []
        for info in _INDEX_INFOS:
            code = info["code"]

            # 1) 实时点位（新浪）
            rt = None
            try:
                rt = fetcher.get_realtime_quote(code)
            except Exception:
                rt = None

            if rt and rt.get("current"):
                current = float(rt["current"])
                prev_close = float(rt.get("prev_close") or current)
                change = current - prev_close
                change_pct = (change / prev_close) * 100 if prev_close else 0.0
                name = rt.get("name") or info["name"]
                high = float(rt.get("high") or current)
                low = float(rt.get("low") or current)
            else:
                # 新浪失败：用指数日线兜底
                try:
                    df = fetcher.get_index(code, start=start_str)
                    if df is None or df.empty or len(df) < 2:
                        cards.append({**info, "current": None, "change": None, "change_pct": None, "spark": None})
                        continue
                    current = float(df["close"].iloc[-1])
                    prev = float(df["close"].iloc[-2])
                    change = current - prev
                    change_pct = (change / prev) * 100 if prev else 0.0
                    name = info["name"]
                    high = current
                    low = current
                except Exception:
                    cards.append({**info, "current": None, "change": None, "change_pct": None, "spark": None})
                    continue

            # 2) 日内走势：优先当日 1 分钟 K 线，缺失时用 OHLC 关键点兜底
            today_df = None
            try:
                today_df = fetcher.get_index_minute(code, today_str.replace("-", ""))
            except Exception:
                pass

            if today_df is not None and not today_df.empty:
                # 分钟线：以今天 0 点开盘后第一根 open 为当日开盘，high/low 取极值
                open_ = float(today_df["open"].iloc[0])
                high = float(today_df["high"].max())
                low = float(today_df["low"].min())
                close = current
                spark_x = list(range(len(today_df)))
                spark_y = today_df["close"].tolist()
            else:
                # 分钟线拿不到：用实时报价的 open/high/low/current 合成关键点序列
                open_ = float(rt.get("open") or current) if rt else current
                high = float(rt.get("high") or current) if rt else current
                low = float(rt.get("low") or current) if rt else current
                close = current
                spark_x = [0, 1, 2, 3]
                spark_y = [open_, high, low, close]

            color = UP_COLOR if change_pct >= 0 else DOWN_COLOR

            fig = go.Figure()
            if spark_y:
                fig.add_trace(go.Scatter(
                    x=spark_x,
                    y=spark_y,
                    mode="lines",
                    line={"color": color, "width": 2},
                    fill="tozeroy",
                    fillcolor=_hex_to_rgba(color, 0.13),
                    hoverinfo="skip",
                    showlegend=False,
                ))
                # 实时位置标记
                fig.add_trace(go.Scatter(
                    x=[spark_x[-1]],
                    y=[spark_y[-1]],
                    mode="markers",
                    marker={"color": color, "size": 6, "symbol": "circle"},
                    hoverinfo="skip",
                    showlegend=False,
                ))
                # 开盘价水平参考线
                fig.add_hline(
                    y=open_,
                    line=dict(color=_hex_to_rgba(color, 0.5), width=1, dash="dot"),
                )

            # y 轴缩放到当天高低点，让哪怕 0.5% 的波动也肉眼可见
            y_min = min(low, open_, close) if low else min(spark_y)
            y_max = max(high, open_, close) if high else max(spark_y)
            padding = (y_max - y_min) * 0.08 if y_max > y_min else (y_max * 0.005 if y_max else 0.001)
            fig.update_layout(
                margin={"l": 0, "r": 0, "t": 0, "b": 0},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"visible": False},
                yaxis={
                    "visible": False,
                    "range": [y_min - padding, y_max + padding],
                    "fixedrange": True,
                },
                height=92,
                width=220,
            )

            cards.append({
                **info,
                "name": name,
                "current": current,
                "change": change,
                "change_pct": change_pct,
                "open": open_,
                "high": high,
                "low": low,
                "trend": _trend_label(open_, high, low, close, prev_close),
                "spark": fig,
                "color": color,
            })
        st.session_state[cache_key] = cards
        # 清理旧缓存键
        for k in list(st.session_state.keys()):
            if k.startswith("index_cards_") and k != cache_key:
                del st.session_state[k]

    dark = _theme_is_dark()
    card_bg = "rgba(26,26,46,0.55)" if dark else "#FFFFFF"
    border_color = "rgba(102,126,234,0.12)" if dark else "#E5E7EB"
    name_color = "#e2e8f0" if dark else "#111827"
    code_color = "#94a3b8" if dark else "#6B7280"

    for card in cards:
        # 用 div 包裹，允许内容自然撑开，避免被裁剪/出现滚动条
        st.markdown("<div style='overflow:visible;'>", unsafe_allow_html=True)
        with st.container(border=True):
            c_left, c_mid, c_right = st.columns([0.20, 0.46, 0.34])
            with c_left:
                st.markdown(
                    f"<div style='font-size:17px;font-weight:700;color:{name_color};'>{card['name']}</div>"
                    f"<div style='font-size:12px;color:{code_color};margin-top:3px;'>{card['label']} {card['code']}</div>",
                    unsafe_allow_html=True,
                )
            with c_mid:
                if card.get("spark"):
                    st.plotly_chart(card["spark"], use_container_width=True, config={"displayModeBar": False})
                else:
                    st.caption("暂无数据")
            with c_right:
                if card["current"] is not None:
                    sign = "+" if card["change_pct"] >= 0 else ""
                    trend_color = card["color"] if card["trend"] != "窄幅震荡" else code_color
                    st.markdown(
                        f"<div style='text-align:right;font-size:22px;font-weight:800;color:{card['color']};font-family:Fira Code,monospace;line-height:1.15;'>"
                        f"{card['current']:.2f}</div>"
                        f"<div style='text-align:right;font-size:13px;color:{card['color']};font-weight:600;margin-top:3px;'>"
                        f"{sign}{card['change']:.2f} ({sign}{card['change_pct']:.2f}%)</div>"
                        f"<div style='text-align:right;font-size:12px;color:{trend_color};font-weight:600;margin-top:3px;'>"
                        f"{card['trend']}</div>"
                        f"<div style='text-align:right;font-size:11px;color:{code_color};margin-top:4px;'>"
                        f"O {card['open']:.2f} &nbsp;H {card['high']:.2f} &nbsp;L {card['low']:.2f}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("—")
        st.markdown("</div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 全局股票搜索
# ──────────────────────────────────────────────────────────────
def render_global_search() -> None:
    """侧边栏全局搜索框：输入关键词实时搜索股票，回车/点击结果进入行情看板。"""
    st.markdown("### 🔍 股票搜索")
    q = st.text_input(
        "股票代码 / 名称 / 拼音",
        key="global_search_q",
        placeholder="如 600519 / 茅台 / mt",
        label_visibility="collapsed",
    )
    if q:
        try:
            resp = requests.get(
                f"{API_BASE}/api/stocks/search",
                params={"q": q, "limit": 8},
                headers={"Authorization": f"Bearer {get_token()}"},
                timeout=5,
            )
            if resp.status_code == 200:
                body = resp.json()
                results = body.get("data") or []
                if results:
                    for item in results:
                        label = f"{item.get('code', '')} {item.get('name', '')}"
                        if st.button(label, key=f"search_{item.get('code')}", use_container_width=True):
                            # 记录到「最近浏览」
                            _push_recent(item.get("code"), item.get("name"))
                            safe_switch_page("pages/1_股票选取.py")
                else:
                    st.caption("无匹配结果")
            else:
                st.caption("搜索失败")
        except Exception:
            st.caption("搜索服务不可用")


# ──────────────────────────────────────────────────────────────
# 主题快速切换
# ──────────────────────────────────────────────────────────────
def render_theme_toggle() -> None:
    """侧边栏深色 / 浅色快速切换（读/写 session_state['theme_mode']）。"""
    from modules.ui_theme import get_current_mode, apply_theme

    mode = st.session_state.get("theme_mode", get_current_mode())
    col_dark, col_light = st.columns(2)
    with col_dark:
        if st.button(
            "🌙 暗夜",
            use_container_width=True,
            type="primary" if mode == "dark" else "secondary",
            key="theme_toggle_dark",
        ):
            st.session_state["theme_mode"] = "dark"
            apply_theme()
            persist_prefs()
            st.rerun()
    with col_light:
        if st.button(
            "☀️ 白天",
            use_container_width=True,
            type="primary" if mode == "light" else "secondary",
            key="theme_toggle_light",
        ):
            st.session_state["theme_mode"] = "light"
            apply_theme()
            persist_prefs()
            st.rerun()


# ──────────────────────────────────────────────────────────────
# 右上角通用栏：★ 星辰 AI 弹层 + 主题切换（所有页面通用）
# ──────────────────────────────────────────────────────────────
def render_topright_bar() -> None:
    """主区右上角通用栏：[★ 星辰 AI 弹层] [🌙 暗夜] [☀️ 白天]。

    由 require_auth() 在每个业务页面顶部注入，保证「不管用户在哪个界面」
    都能唤起 AI 咨询与切换主题。AI 咨询收进 popover 弹层，不占侧栏空间。
    """
    from modules.ui_theme import get_current_mode, apply_theme

    mode = st.session_state.get("theme_mode", get_current_mode())
    left, right = st.columns([0.55, 0.45])
    with right:
        c_ai, c_set, c_d, c_l = st.columns([0.46, 0.18, 0.18, 0.18])
        with c_ai:
            # st.popover 原生弹层：任意页面右上角唤起 AI 咨询
            # 触发按钮前的 ★ 字符改为星辰 AI 内联 SVG logo（约 18px，与按钮同行）
            _logo_c, _pop_c = st.columns([0.2, 0.8])
            with _logo_c:
                st.markdown(STAR_AI_LOGO(18), unsafe_allow_html=True)
            with _pop_c:
                try:
                    with st.popover("星辰 AI", use_container_width=True):
                        render_ai_consultant()
                except Exception:
                    # 极老版本 Streamlit 无 popover 时兜底：退回侧边栏
                    with st.sidebar:
                        render_ai_consultant()
        with c_set:
            # ⚙️ 设置：与 AI / 主题图标同一横轴，点击进入「我的」设置页
            if st.button("⚙️", key="top_settings", use_container_width=True, help="设置（进入「我的」偏好设置）"):
                safe_switch_page("pages/👤_我的.py")
        with c_d:
            if st.button(
                "🌙", key="top_theme_dark", use_container_width=True,
                type="primary" if mode == "dark" else "secondary",
                help="暗夜模式",
            ):
                st.session_state["theme_mode"] = "dark"
                apply_theme()
                persist_prefs()
                st.rerun()
        with c_l:
            if st.button(
                "☀️", key="top_theme_light", use_container_width=True,
                type="primary" if mode == "light" else "secondary",
                help="白天模式",
            ):
                st.session_state["theme_mode"] = "light"
                apply_theme()
                persist_prefs()
                st.rerun()


# 向后兼容别名（旧调用点仍可用）
def render_theme_toggle_topright() -> None:
    render_topright_bar()


# ──────────────────────────────────────────────────────────────
# 全局 AI 咨询（★ 星辰 · 多市场智能股票分析师）
# ──────────────────────────────────────────────────────────────
from modules.background_tasks import submit_task_with_error, poll_task


def _slim_context() -> Dict[str, Any]:
    """把当前页面上下文精简，只传 AI 需要的汇总字段，避免序列化 DataFrame。"""
    rows = st.session_state.get("_cmp_rows")
    slim_rows = None
    if rows:
        slim_rows = []
        for r in rows:
            slim_rows.append({
                "code": r.get("code"),
                "name": r.get("name"),
                "signal": r.get("signal"),
                "scores": r.get("scores"),
                "industry": r.get("industry"),
                "market_cap": r.get("market_cap"),
                "pe_ttm": r.get("pe_ttm"),
                "elasticity": r.get("elasticity"),
                "business_corr": r.get("business_corr"),
            })
    analysis = st.session_state.get("analysis_result")
    slim_analysis = None
    if analysis and isinstance(analysis, dict):
        slim_analysis = {k: v for k, v in analysis.items() if k != "df"}
    return {"_cmp_rows": slim_rows, "analysis_result": slim_analysis}


def _current_stock_context():
    """从个股分析页的 session 结果中提取当前股票上下文。"""
    ar = st.session_state.get("analysis_result")
    if isinstance(ar, dict):
        name = ar.get("name") or ar.get("stock_name") or ar.get("code")
        verdict = ar.get("verdict") or ar.get("signal")
        score = ar.get("score") or ar.get("composite") or ar.get("score_composite")
        if name:
            return str(name), verdict, score
    return None, None, None


def _ai_popover_theme_css() -> str:
    """Popover 内部主题适配：强制暗色下输入框/按钮/气泡可读。

    关键：Streamlit 中 st.markdown 包裹的 div 与后续 widget 是「兄弟节点」而非嵌套，
    故交互控件（textarea / button）的样式必须作用到 [data-testid="stPopoverBody"]
    才能命中（弹层内所有控件都是它的后代）；而对话气泡由单个 st.markdown 一次性输出、
    内部已正确嵌套，故 .ai-chat-box .ai-msg 可命中。
    """
    from modules.ui_theme import _theme_is_dark
    if _theme_is_dark():
        return """
        <style>
        /* Popover 弹层本体：暗夜深底 */
        [data-testid="stPopoverBody"] { background:#1a1a2e !important; border-color:#2d2d44 !important; }
        .ai-consult-wrap { color:#e2e8f0; }
        .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#e2e8f0 !important; }
        /* 输入框：常态/hover/focus/active 强制黑底（作用到弹层 body 才命中） */
        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea,
        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:hover,
        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:focus,
        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:active,
        [data-testid="stPopoverBody"] textarea {
            background:#15152a !important; color:#e2e8f0 !important;
            border:1px solid #2d2d44 !important; box-shadow:none !important;
            caret-color:#e2e8f0 !important;
        }
        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea::placeholder { color:#64748b !important; }
        [data-testid="stPopoverBody"] [data-testid="stTextArea"] > div { background:transparent !important; border:none !important; }
        [data-testid="stPopoverBody"] [data-testid="stTextArea"] { background:#15152a !important; border:1px solid #2d2d44 !important; border-radius:10px !important; }
        /* 发送/清空按钮：常态/hover/focus/active 深紫底+深字 */
        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button,
        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:hover,
        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:focus,
        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:active,
        [data-testid="stPopoverBody"] .stButton button,
        [data-testid="stPopoverBody"] .stButton button:hover,
        [data-testid="stPopoverBody"] .stButton button:focus,
        [data-testid="stPopoverBody"] .stButton button:active {
            background:linear-gradient(180deg,#667eea,#764ba2) !important; color:#0f0f23 !important;
            border:none !important; box-shadow:none !important; font-weight:600 !important;
        }
        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:disabled,
        [data-testid="stPopoverBody"] .stButton button:disabled { opacity:.55 !important; }
        /* 对话气泡（单个 st.markdown 块内已正确嵌套，.ai-chat-box .ai-msg 可命中） */
        .ai-chat-box { max-height:360px; overflow-y:auto; padding:8px 2px; display:flex; flex-direction:column; gap:10px; }
        .ai-chat-box .ai-msg { max-width:92%; padding:8px 12px; border-radius:14px; font-size:13px; line-height:1.6; word-break:break-word; box-shadow:0 1px 4px rgba(0,0,0,.25); }
        .ai-chat-box .ai-msg p { color:inherit !important; margin:4px 0; }
        .ai-chat-box .ai-msg ul, .ai-chat-box .ai-msg ol { margin:4px 0; padding-left:18px; }
        .ai-chat-box .ai-msg li { margin:2px 0; }
        /* 用户消息：右侧带边框方框，深灰底（明确区分用户问题 / AI 回答） */
        .ai-chat-box .ai-msg.user { align-self:flex-end; background:#252542; color:#e2e8f0; border:1px solid #4b4b7a; border-bottom-right-radius:4px; }
        .ai-chat-box .ai-msg.assistant { align-self:flex-start; background:#15152a; color:#e2e8f0; border:1px solid #2d2d44; border-bottom-left-radius:4px; }
        .ai-chat-box .ai-role { font-size:10px; opacity:.65; margin-bottom:2px; }
        .ai-chat-box .ai-msg.user .ai-role { text-align:right; color:#94a3b8; }
        .ai-typing { align-self:flex-start; font-size:12px; color:#94a3b8; padding:4px 2px; }
        /* 回到底部按钮改为弹层内嵌 .sf-scroll-bottom-inline（见 modules/scroll_nav.py） */
        </style>
        """
    return """
    <style>
    [data-testid="stPopoverBody"] { background:#ffffff !important; border-color:#e2e8f0 !important; }
    .ai-consult-wrap { color:#111827; }
    .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#111827 !important; }
    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea,
    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:hover,
    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:focus,
    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:active,
    [data-testid="stPopoverBody"] textarea {
        background:#ffffff !important; color:#111827 !important;
        border:1px solid #d1d5db !important; box-shadow:none !important;
        caret-color:#111827 !important;
    }
    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea::placeholder { color:#9ca3af !important; }
    [data-testid="stPopoverBody"] [data-testid="stTextArea"] > div { background:transparent !important; border:none !important; }
    [data-testid="stPopoverBody"] [data-testid="stTextArea"] { background:#ffffff !important; border:1px solid #d1d5db !important; border-radius:10px !important; }
    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button,
    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:hover,
    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:focus,
    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:active,
    [data-testid="stPopoverBody"] .stButton button,
    [data-testid="stPopoverBody"] .stButton button:hover,
    [data-testid="stPopoverBody"] .stButton button:focus,
    [data-testid="stPopoverBody"] .stButton button:active {
        background:linear-gradient(180deg,#D4A02A,#B8860B) !important; color:#111827 !important;
        border:none !important; box-shadow:none !important; font-weight:600 !important;
    }
    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:disabled,
    [data-testid="stPopoverBody"] .stButton button:disabled { opacity:.55 !important; }
    .ai-chat-box { max-height:360px; overflow-y:auto; padding:8px 2px; display:flex; flex-direction:column; gap:10px; }
    .ai-chat-box .ai-msg { max-width:92%; padding:8px 12px; border-radius:14px; font-size:13px; line-height:1.6; word-break:break-word; box-shadow:0 1px 3px rgba(0,0,0,.06); }
    .ai-chat-box .ai-msg p { color:inherit !important; margin:4px 0; }
    .ai-chat-box .ai-msg ul, .ai-chat-box .ai-msg ol { margin:4px 0; padding-left:18px; }
    .ai-chat-box .ai-msg li { margin:2px 0; }
    .ai-chat-box .ai-msg.user { align-self:flex-end; background:#fff7e6; color:#111827; border:1px solid #ffd591; border-bottom-right-radius:4px; }
    .ai-chat-box .ai-msg.assistant { align-self:flex-start; background:#f4f6fb; color:#111827; border:1px solid #e2e8f0; border-bottom-left-radius:4px; }
    .ai-chat-box .ai-role { font-size:10px; opacity:.55; margin-bottom:2px; }
    .ai-chat-box .ai-msg.user .ai-role { text-align:right; color:#6b7280; }
    .ai-typing { align-self:flex-start; font-size:12px; color:#6b7280; padding:4px 2px; }
    /* 回到底部按钮改为弹层内嵌 .sf-scroll-bottom-inline（见 modules/scroll_nav.py） */
    </style>
    """


def _chat_history_for_context(max_turns: int = 6) -> list:
    """取最近若干轮对话，给 AI 引擎做「可持续追问」的上下文。"""
    chat = st.session_state.get("ai_chat") or []
    return chat[-max_turns:]


def _ai_md(text: str) -> str:
    """极简 markdown → HTML：转义后支持 **粗体** / *斜体* / 换行 / 无序列表。"""
    import html as _h
    import re as _re
    t = _h.escape(str(text), quote=False)
    t = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = _re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    t = _re.sub(r"(?m)^- (.*?)(?=<br>|$)", r"• \1", t)
    t = t.replace("\n", "<br>")
    return t


def _render_ai_chat() -> None:
    """渲染对话气泡（用户右、助手左），一次性输出保证 .ai-chat-box .ai-msg 正确嵌套命中。"""
    chat = st.session_state.get("ai_chat") or []
    parts = ['<div class="ai-chat-box">']
    for msg in chat:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            parts.append(
                f'<div class="ai-msg user"><div class="ai-role">你</div>'
                f'{_ai_md(content)}</div>'
            )
        else:
            parts.append(
                f'<div class="ai-msg assistant"><div class="ai-role">★ 星辰 AI</div>'
                f'{_ai_md(content)}</div>'
            )
    # 正在思考的占位
    if st.session_state.get("ai_task_id"):
        parts.append('<div class="ai-typing">🤔 AI 正在思考…</div>')
    parts.append('</div>')
    st.markdown("\n".join(parts), unsafe_allow_html=True)


def _ai_scroll_to_bottom_component(dark: bool) -> None:
    """在 popover 内渲染一个「滚动到底部」按钮，并自动把对话区域滚到底。"""
    bg = "#667eea" if dark else "#D4A02A"
    color = "#ffffff" if dark else "#111827"
    hover_bg = "#764ba2" if dark else "#B8860B"
    js = f"""
    <div id="ai-scroll-bottom-btn" style="width:100%;display:flex;justify-content:center;padding:6px 0;cursor:pointer;"
         onclick="scrollAIChatToBottom()">
      <div style="width:34px;height:34px;border-radius:50%;background:{bg};color:{color};display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 6px rgba(0,0,0,.25);" onmouseover="this.style.background='{hover_bg}'" onmouseout="this.style.background='{bg}'">▼</div>
    </div>
    <script>
      function scrollAIChatToBottom() {{
        var doc = window.parent.document;
        var box = doc.querySelector('.ai-chat-box');
        if (box) box.scrollTop = box.scrollHeight;
      }}
      setTimeout(scrollAIChatToBottom, 60);
      setTimeout(scrollAIChatToBottom, 300);
    </script>
    """
    components.html(js, height=48)


def render_ai_consultant() -> None:
    """全局 AI 咨询模块（右上角弹层内）：任意页面可用，后台异步运行，对话可持续。

    设计目标（用户反馈）：
      - 结果必须「真正返回」，不再卡在后台不显示 → 用 streamlit_autorefresh 轮询，
        后台任务完成后自动把 AI 回复追加进对话流。
      - 对话做成「可持续」的，像聊天一样保留历史、可连续追问 → 历史存
        session_state["ai_chat"]，提交时把上下文 + 历史一起交给 AI 引擎。
      - 加载只在 AI 小框内感知，不污染页面主体 → 错误/状态全部放在 popover 内；
        autorefresh 只在任务运行且未超时前触发，并降低频率。
      - 聊天界面清晰区分用户/AI，清空按钮在标题右侧，可一键滚到底部输入框。
    """
    from modules.ui_theme import _theme_is_dark
    from modules.scroll_nav import scroll_bottom_inline_html

    dark = _theme_is_dark()
    st.markdown(_ai_popover_theme_css(), unsafe_allow_html=True)
    st.markdown('<div class="ai-consult-wrap">', unsafe_allow_html=True)

    # 初始化持久化对话状态
    if "ai_chat" not in st.session_state:
        st.session_state["ai_chat"] = []  # [{"role":"user"/"assistant", "content": str}]
    if "ai_task_id" not in st.session_state:
        st.session_state["ai_task_id"] = None
    if "ai_task_started_at" not in st.session_state:
        st.session_state["ai_task_started_at"] = None

    # 标题 + 清空对话按钮 同一行
    head_col1, head_col2 = st.columns([5, 1])
    with head_col1:
        st.markdown(f"#### {STAR_AI_LOGO(20)} 星辰 · 多市场智能股票分析师", unsafe_allow_html=True)
    with head_col2:
        if st.session_state["ai_chat"]:
            if st.button("🗑️", key="ai_clear_chat", help="清空对话"):
                st.session_state["ai_chat"] = []
                st.session_state["ai_task_id"] = None
                st.session_state["ai_task_started_at"] = None
                st.rerun()

    rows = st.session_state.get("_cmp_rows")
    name, verdict, score = _current_stock_context()
    if rows:
        st.caption(f"📊 当前对比 {len(rows)} 只标的，AI 会优先回答你提到的股票。")
    elif name:
        st.caption(f"🎯 当前个股：{name}，你直接问其他股票我也会独立分析。")
    else:
        st.caption("输入股票代码或名称，AI 会独立拉取数据并给出研判。")

    # 渲染历史对话
    _render_ai_chat()

    # 回到底部按钮：弹层内嵌居中 ▼，点击滚动聊天框到底
    st.markdown(scroll_bottom_inline_html(dark=dark), unsafe_allow_html=True)

    # 输入框 + 发送（只在没有任务进行时允许输入，避免并发）
    busy = bool(st.session_state.get("ai_task_id"))
    with st.form("ai_consult_global", clear_on_submit=True):
        q = st.text_area(
            "AI 咨询",
            placeholder="例如：深科技怎么样？ / 这组合里谁最值得买？风险在哪？",
            height=80,
            label_visibility="collapsed",
            key="ai_consult_q",
            disabled=busy,
        )
        submitted = st.form_submit_button(
            "🚀 发送" if not busy else "⏳ AI 思考中…",
            use_container_width=True,
            disabled=busy,
        )

    if submitted and q and not busy:
        # 追加用户消息
        st.session_state["ai_chat"].append({"role": "user", "content": q})
        # 提交后台任务（带上历史，让 AI 可持续追问）
        ctx = _slim_context()
        ctx["history"] = _chat_history_for_context()
        task_id, err = submit_task_with_error("ai_consult", {"question": q, "context": ctx})
        if task_id:
            st.session_state["ai_task_id"] = task_id
            st.session_state["ai_task_started_at"] = time.time()
            st.rerun()
        else:
            # 提交失败，回滚用户消息，避免只显示问题没有回答
            st.session_state["ai_chat"].pop()
            err = err or "未知错误"
            if "登录" in err or "过期" in err or "凭证" in err:
                st.error(f"❌ {err}")
                if st.button("重新登录", key="ai_relogin", use_container_width=True):
                    st.session_state.clear()
                    st.switch_page("pages/0_登录.py")
            else:
                st.error(f"❌ 后台任务提交失败：{err}，请刷新后重试。")
            st.session_state["ai_task_id"] = None

    # 轮询后台任务状态
    task_id = st.session_state.get("ai_task_id")
    if task_id:
        task = poll_task(task_id, max_wait=0.4)
        if task and task.get("status") == "success":
            result = task.get("result") or {}
            answer = result.get("answer") or "AI 暂未给出回答"
            st.session_state["ai_chat"].append({"role": "assistant", "content": answer})
            st.session_state["ai_task_id"] = None
            st.session_state["ai_task_started_at"] = None
            st.rerun()
        elif task and task.get("status") == "error":
            err = task.get("error") or "未知错误"
            st.session_state["ai_chat"].append(
                {"role": "assistant", "content": f"❌ AI 分析失败：{err}"}
            )
            st.session_state["ai_task_id"] = None
            st.session_state["ai_task_started_at"] = None
            st.rerun()

    # 只在任务运行且未超时时低频刷新，避免持续影响整个页面
    if st.session_state.get("ai_task_id"):
        started = st.session_state.get("ai_task_started_at") or time.time()
        elapsed = time.time() - started
        if elapsed > 240:
            # 超时：自动结束，避免永远刷新
            st.session_state["ai_chat"].append(
                {"role": "assistant", "content": "❌ AI 响应超时，请重新提问。"}
            )
            st.session_state["ai_task_id"] = None
            st.session_state["ai_task_started_at"] = None
            st.rerun()
        try:
            from streamlit_autorefresh import st_autorefresh

            st_autorefresh(interval=5000, limit=150, key="ai_chat_autorefresh")
        except Exception:
            pass

    st.markdown("</div>", unsafe_allow_html=True)


# 保留旧函数签名的占位（已被后台异步方案替代）
def _ai_summary_compare(rows: list, question: str) -> str:
    """旧版同步简报函数，保留仅做兼容。"""
    return ""


def _ai_answer(rows, question, name=None, verdict=None, score=None) -> str:
    """旧版同步回答函数，保留仅做兼容。"""
    return ""


def inject_global_widgets() -> None:
    """require_auth() 之后注入所有页面通用组件：右上角「★ 星辰 AI 弹层 + 主题开关」
    以及全局右下角「▲ 回到顶部」悬浮按钮。

    AI 咨询收进右上角 popover，任意页面唤起；不再占用左侧栏空间。
    """
    from modules.scroll_nav import inject_scroll_nav

    render_topright_bar()
    inject_scroll_nav()


# ──────────────────────────────────────────────────────────────
# 通知中心
# ──────────────────────────────────────────────────────────────
def render_notifications() -> None:
    """侧边栏通知中心：展示自选股数量、最近登录时间、使用提示。"""
    st.markdown("### 🔔 通知中心")
    try:
        resp = requests.get(
            f"{API_BASE}/api/watchlist",
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=5,
        )
        wl_count = 0
        if resp.status_code == 200:
            body = resp.json()
            wl_count = len(body.get("data") or [])
        st.info(f"⭐ 自选股：**{wl_count}** 只")
    except Exception:
        st.info("⭐ 自选股：—")

    # 最近登录记录
    try:
        resp = requests.get(
            f"{API_BASE}/api/auth/logins",
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=5,
        )
        if resp.status_code == 200:
            logs = resp.json().get("data") or []
            if logs:
                last = logs[0].get("created_at", "")[:19].replace("T", " ")
                st.caption(f"🕒 上次登录：{last}")
    except Exception:
        pass

    with st.expander("📌 使用提示", expanded=False):
        st.markdown("""
        - 行情看板支持 **日K / 周K / 月K** 切换
        - 个股分析提供趋势、情绪、事件与作战计划
        - 事件追踪综合三类信号评分
        """)


# ──────────────────────────────────────────────────────────────
# 面包屑
# ──────────────────────────────────────────────────────────────
def render_breadcrumb(items: list[str]) -> None:
    """页面顶部面包屑。items 形如 ['首页', '行情看板']。"""
    st.markdown(" › ".join(f"**{i}**" for i in items), help="当前位置")


# ──────────────────────────────────────────────────────────────
# 最近浏览（session_state 维护）
# ──────────────────────────────────────────────────────────────
def _push_recent(code: str, name: str) -> None:
    if "recent_stocks" not in st.session_state:
        st.session_state["recent_stocks"] = []
    recents = st.session_state["recent_stocks"]
    recents = [r for r in recents if r.get("code") != code]
    recents.insert(0, {"code": code, "name": name})
    st.session_state["recent_stocks"] = recents[:8]


def get_recent_stocks() -> list:
    return st.session_state.get("recent_stocks", [])


# ──────────────────────────────────────────────────────────────
# 密码强度
# ──────────────────────────────────────────────────────────────
def password_strength(pwd: str) -> tuple[int, str]:
    """返回 (分数 0-4, 等级文本)。"""
    if not pwd:
        return 0, "空"
    score = 0
    if len(pwd) >= 8:
        score += 1
    if len(pwd) >= 12:
        score += 1
    if any(c.isupper() for c in pwd) and any(c.islower() for c in pwd):
        score += 1
    if any(c.isdigit() for c in pwd) and any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/" for c in pwd):
        score += 1
    levels = ["弱", "弱", "中", "强", "很强"]
    return score, levels[score]


# ──────────────────────────────────────────────────────────────
# 会话剩余时间（自动登出倒计时）
# ──────────────────────────────────────────────────────────────
def get_session_remaining() -> int | None:
    """解码当前 JWT 的 exp，返回剩余秒数；无法解析时返回 None。"""
    import time as _time
    import jwt as _jwt
    token = get_token()
    if not token:
        return None
    try:
        payload = _jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        if not exp:
            return None
        return max(0, int(exp - _time.time()))
    except Exception:
        return None


def render_session_countdown() -> None:
    """显示当前登录会话剩余时间（自动登出倒计时）。"""
    remain = get_session_remaining()
    if remain is None:
        st.caption("⏱️ 会话状态：未知")
        return
    minutes = remain // 60
    seconds = remain % 60
    st.caption(f"⏱️ 会话剩余：{minutes}分{seconds}秒（超时将自动登出）")
