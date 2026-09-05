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
import logging
from modules.ui_kit import inject_kit_css, xc_handle_error
logger = logging.getLogger(__name__)
from typing import Any, Dict
from datetime import datetime
import html
import time
import requests

from modules.time_utils import now_cst_str, now_cst_naive
import streamlit as st
import streamlit.components.v1 as components
from modules.session import API_BASE, get_token, safe_switch_page, persist_prefs, is_admin, _rel_time
from modules._widgets_base import STAR_AI_LOGO, _INDEX_INFOS
from modules.colors import _hex_to_rgba

def _index_market_status():
    """返回指数是否需要自动刷新：(is_open, status_text, refresh_ms)。

    统一委托 page_widgets.current_trading_session（基于北京时间），避免与
    is_trading_now 各自算时区导致周末/盘中判定不一致（R3 DRY）。
    """
    from modules.page_widgets import current_trading_session
    sess = current_trading_session()
    if sess == 'weekend':
        return (False, '⚪ 已休市（周末）', 0)
    if sess in ('morning', 'afternoon'):
        return (True, '🟢 交易中', 60 * 1000)
    return (False, '⚪ 已休市', 0)

def _index_name_html(name, color: str='#111827', size_px: int=17) -> str:
    """纯函数：把数据派生的指数名称渲染为安全内联 HTML（转义防注入，R2）。

    None/空/非字符串一律降级为占位符「—」；名称文本经 html.escape 处理，
    杜绝来自行情接口的数据派生名称造成 HTML/JS 注入。
    """
    if not name:
        name = '—'
    safe = html.escape(str(name), quote=True)
    return f'<div style="font-size:{size_px}px;font-weight:700;color:{color};">{safe}</div>'

def _index_cache_key() -> str:
    """生成指数缓存键，按分钟粒度，避免每秒 rerun 都重新请求。"""
    return now_cst_str('%Y-%m-%d %H:%M')

def _trend_label(open_: float, high: float, low: float, close: float, prev_close: float, spark_y=None) -> str:
    """根据日内 sparkline 或 OHLC 给出可读的走势定性。

    核心思路：判断「冲高回落」还是「探底回升」不应只看高低点出现顺序，
    而要看日内是否形成了「从高点明显回落」或「从低点明显回升」的真实结构。
    """
    if not all([open_, high, low, close, prev_close]) or prev_close == 0:
        return '—'
    amplitude = (high - low) / prev_close * 100
    if amplitude < 0.15:
        return '窄幅震荡'

    def _pullback_from_high(h, o, c):
        up = (h - o) / prev_close * 100
        if up <= 0.15:
            return False
        return (h - c) / (h - o + 1e-09) > 0.35

    def _bounce_from_low(l, o, c):
        down = (o - l) / prev_close * 100
        if down <= 0.15:
            return False
        return (c - l) / (o - l + 1e-09) > 0.35
    if spark_y and len(spark_y) >= 4:
        y = []
        for v in spark_y:
            try:
                fv = float(v)
                if fv == fv:
                    y.append(fv)
            except (TypeError, ValueError):
                pass
        if len(y) >= 4:
            hi_i = max(range(len(y)), key=lambda i: y[i])
            lo_i = min(range(len(y)), key=lambda i: y[i])
            hi = y[hi_i]
            lo = y[lo_i]
            is_pullback = _pullback_from_high(hi, open_, close)
            is_bounce = _bounce_from_low(lo, open_, close)
            if is_pullback and (not is_bounce):
                return '冲高回落'
            if is_bounce and (not is_pullback):
                return '探底回升'
            if is_pullback and is_bounce:
                if hi_i < lo_i:
                    return '冲高回落'
                if lo_i < hi_i:
                    return '探底回升'
            if close > open_ * 1.001:
                return '震荡上行'
            if close < open_ * 0.999:
                return '震荡下行'
            return '窄幅震荡'
    if _pullback_from_high(high, open_, close):
        return '冲高回落'
    if _bounce_from_low(low, open_, close):
        return '探底回升'
    if close > open_:
        return '震荡上行'
    if close < open_:
        return '震荡下行'
    return '窄幅震荡'
    if close > open_:
        if open_ > prev_close:
            return '高开高走'
        if open_ < prev_close:
            return '低开高走'
        return '平开高走'
    elif close < open_:
        if open_ > prev_close:
            return '高开低走'
        if open_ < prev_close:
            return '低开低走'
        return '平开低走'
    else:
        return '平开平收'

def _build_index_card(info, fetcher, start_str):
    """取数 + 构建单张指数迷你卡（含 Plotly sparkline），可在独立线程中调用。

    返回卡片 dict；网络/解析失败返回最小 None 卡（current=None），由渲染层降级为「暂无数据/—」。
    不触碰 st.session_state 与任何 Streamlit 渲染，保证线程安全。
    """
    import plotly.graph_objects as go
    from modules.visualizer import UP_COLOR, DOWN_COLOR
    if info.get('global'):
        gq = None
        try:
            gq = fetcher.get_global_index_quote(info)
        except Exception as e:
            logger.warning(f"[widgets] 处理异常: {e}")
            gq = None
        if not gq or gq.get('current') is None:
            return {**info, 'current': None, 'change': None, 'change_pct': None, 'spark': None}
        current = gq['current']
        change = gq['change']
        change_pct = gq['change_pct']
        name = gq.get('name') or info['name']
        high = gq.get('high') if gq.get('high') is not None else current
        low = gq.get('low') if gq.get('low') is not None else current
        open_ = gq.get('open') if gq.get('open') is not None else current
        prev_close = gq.get('prev_close') or current
        close = current
        spark_x = gq.get('spark_x')
        spark_y = gq.get('spark_y')
        if not spark_y:
            sx, sy = fetcher.synth_us_index_intraday(open_, high, low, close, prev_close)
            if sx and sy:
                spark_x, spark_y = (sx, sy)
                info = {**info, 'approx': True}
            else:
                spark_x = None
    else:
        rt = None
        try:
            rt = fetcher.get_realtime_quote(info['code'])
        except Exception as e:
            logger.warning(f"[widgets] 处理异常: {e}")
            rt = None
        if rt and rt.get('current'):
            current = float(rt['current'])
            prev_close = float(rt.get('prev_close') or current)
            change = current - prev_close
            change_pct = change / prev_close * 100 if prev_close else 0.0
            name = rt.get('name') or info['name']
            high = float(rt.get('high') or current)
            low = float(rt.get('low') or current)
        else:
            try:
                df = fetcher.get_index(info['code'], start=start_str)
                if df is None or df.empty or len(df) < 2:
                    return {**info, 'current': None, 'change': None, 'change_pct': None, 'spark': None}
                current = float(df['close'].iloc[-1])
                prev = float(df['close'].iloc[-2])
                change = current - prev
                change_pct = change / prev * 100 if prev else 0.0
                name = info['name']
                high = current
                low = current
                prev_close = prev
            except Exception as e:
                logger.warning(f"[widgets] 处理异常: {e}")
                return {**info, 'current': None, 'change': None, 'change_pct': None, 'spark': None}
        today_df = None
        try:
            today_df = fetcher.get_index_kline_sina(info['code'], scale=5, datalen=48)
        except Exception as e:
            logger.warning(f"[widgets] 处理异常: {e}")
            pass
        if today_df is not None and (not today_df.empty):
            open_ = float(today_df['open'].iloc[0])
            high = float(today_df['high'].max())
            low = float(today_df['low'].min())
            close = float(today_df['close'].iloc[-1])
            spark_x = list(range(len(today_df)))
            spark_y = today_df['close'].tolist()
        else:
            open_ = float(rt.get('open') or current) if rt else current
            high = float(rt.get('high') or current) if rt else current
            low = float(rt.get('low') or current) if rt else current
            close = current
            spark_x = [0, 1, 2, 3]
            spark_y = [open_, high, low, close]
    _cp = change_pct if change_pct is not None else 0.0
    color = UP_COLOR if _cp >= 0 else DOWN_COLOR
    high_pct = (high - prev_close) / prev_close * 100 if prev_close else 0.0
    low_pct = (low - prev_close) / prev_close * 100 if prev_close else 0.0
    amplitude = (high - low) / prev_close * 100 if prev_close else 0.0
    fig = go.Figure()
    if spark_y:
        fig.add_trace(go.Scatter(x=spark_x, y=spark_y, mode='lines', line={'color': color, 'width': 2}, fill='tozeroy', fillcolor=_hex_to_rgba(color, 0.13), hoverinfo='skip', showlegend=False))
        fig.add_trace(go.Scatter(x=[spark_x[-1]], y=[spark_y[-1]], mode='markers', marker={'color': color, 'size': 6, 'symbol': 'circle'}, hoverinfo='skip', showlegend=False))
        fig.add_hline(y=open_, line=dict(color=_hex_to_rgba(color, 0.5), width=1, dash='dot'))
        if len(spark_y) > 1:
            hi_i = max(range(len(spark_y)), key=lambda i: spark_y[i])
            lo_i = min(range(len(spark_y)), key=lambda i: spark_y[i])
            fig.add_trace(go.Scatter(x=[spark_x[hi_i]], y=[spark_y[hi_i]], mode='markers', marker={'color': UP_COLOR, 'size': 8, 'symbol': 'triangle-up', 'line': {'color': '#ffffff', 'width': 0.5}}, hoverinfo='skip', showlegend=False))
            fig.add_trace(go.Scatter(x=[spark_x[lo_i]], y=[spark_y[lo_i]], mode='markers', marker={'color': DOWN_COLOR, 'size': 8, 'symbol': 'triangle-down', 'line': {'color': '#ffffff', 'width': 0.5}}, hoverinfo='skip', showlegend=False))
    y_min = min(low, open_, close) if low else min(spark_y)
    y_max = max(high, open_, close) if high else max(spark_y)
    padding = (y_max - y_min) * 0.08 if y_max > y_min else y_max * 0.005 if y_max else 0.001
    fig.update_layout(margin={'l': 0, 'r': 0, 't': 0, 'b': 0}, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis={'visible': False}, yaxis={'visible': False, 'range': [y_min - padding, y_max + padding], 'fixedrange': True}, height=92, width=220)
    return {**info, 'name': name, 'current': current, 'change': change, 'change_pct': change_pct, 'open': open_, 'high': high, 'low': low, 'trend': _trend_label(open_, high, low, close, prev_close, spark_y), 'high_pct': high_pct, 'low_pct': low_pct, 'amplitude': amplitude, 'spark': fig, 'color': color}

@st.fragment
def render_index_mini_cards(cols_per_row: int=3) -> None:
    """在页面顶部渲染上证/深证/创业板的实时指数迷你趋势卡片（1:1 列表式）。

    每行包含：左侧指数名称+代码、中间当天/近期走势 sparkline、右侧最新点位+涨跌额+涨跌幅。
    数据源优先新浪财经实时接口（1 分钟级），历史走势由本地指数日线补齐；交易日自动刷新。
    折线颜色按当日涨跌红/绿显示，与 A 股习惯一致（红涨绿跌）。
    """
    from datetime import datetime, timedelta
    from modules.fetcher import StockFetcher
    from modules.ui_theme import _theme_is_dark
    try:
        from modules.autorefresh import st_autorefresh
        is_open, _, refresh_ms = _index_market_status()
        if refresh_ms > 0:
            st_autorefresh(interval=refresh_ms, key='index_autorefresh')
    except Exception as e:
        logger.warning(f"[widgets] 处理异常: {e}")
        pass
    end_date = now_cst_naive().date()
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime('%Y-%m-%d')
    cache_key = f'index_cards_{_index_cache_key()}'
    if cache_key in st.session_state:
        cards = st.session_state[cache_key]
    else:
        from concurrent.futures import ThreadPoolExecutor

        def _worker(info):
            try:
                return _build_index_card(info, StockFetcher(), start_str)
            except Exception as e:
                logger.warning(f"[widgets] 处理异常: {e}")
                return {**info, 'current': None, 'change': None, 'change_pct': None, 'spark': None}
        with ThreadPoolExecutor(max_workers=min(len(_INDEX_INFOS), 8)) as _ex:
            cards = list(_ex.map(_worker, _INDEX_INFOS))
        st.session_state[cache_key] = cards
        for k in list(st.session_state.keys()):
            if k.startswith('index_cards_') and k != cache_key:
                del st.session_state[k]
    dark = _theme_is_dark()
    name_color = '#e2e8f0' if dark else '#111827'
    code_color = '#94a3b8' if dark else '#6B7280'
    _, _, status_text = _index_market_status()
    with st.expander('📈 全球指数行情', expanded=True):
        st.caption(f'红涨绿跌 · 实时点位与当日走势 · {status_text}')
        for card in cards:
            st.markdown("<div style='overflow:visible;'>", unsafe_allow_html=True)
            with st.container(border=True):
                c_left, c_mid, c_right = st.columns([0.2, 0.46, 0.34])
                with c_left:
                    st.markdown(f"{_index_name_html(card['name'], name_color, 17)}<div style='font-size:12px;color:{code_color};margin-top:3px;'>{card['label']} {card['code']}</div>", unsafe_allow_html=True)
                with c_mid:
                    if card.get('spark'):
                        st.plotly_chart(card['spark'], width="stretch", config={"displaylogo": False, "responsive": True, 'displayModeBar': False})
                    else:
                        st.caption('暂无数据')
                with c_right:
                    if card['current'] is not None:
                        # P0 fix 2026-08-28：数据源异常路径会返回 current 有值但 change_pct=None，
                        # 直接 `'>= 0'` 会抛 TypeError（'>=' not supported between 'NoneType' and 'int'）。
                        # 这里把 None 视作与 0 等价（不算涨也不算跌，sign 留空、颜色用中性）。
                        cp = card.get('change_pct')
                        if cp is None:
                            sign = ''
                            num_color = code_color
                        else:
                            sign = '+' if cp >= 0 else ''
                            num_color = UP_COLOR if cp >= 0 else DOWN_COLOR
                        trend_color = card['color'] if card.get('trend') and card['trend'] != '窄幅震荡' else code_color
                        st.markdown(f"<div style='text-align:right;font-size:22px;font-weight:800;color:{card['color']};font-family:Fira Code,monospace;line-height:1.15;'>{card['current']:.2f}</div><div style='text-align:right;font-size:13px;color:{num_color};font-weight:600;margin-top:3px;'>{sign}{card.get('change', 0):.2f} ({sign}{cp if cp is not None else 0:.2f}%)</div><div style='text-align:right;font-size:12px;color:{trend_color};font-weight:600;margin-top:3px;'>{card.get('trend', '')}</div><div style='text-align:right;font-size:11px;color:{code_color};margin-top:4px;line-height:1.5;'>O {card.get('open', 0):.2f}<br><span style='color:#ff4d4f;'>▲ 最高 {card.get('high', 0):.2f} (+{card.get('high_pct', 0):.2f}%)</span><br><span style='color:#00d486;'>▼ 最低 {card.get('low', 0):.2f} ({card.get('low_pct', 0):.2f}%)</span><br>振幅 {card.get('amplitude', 0):.2f}%</div>", unsafe_allow_html=True)
                    else:
                        st.caption('—')
            st.markdown('</div>', unsafe_allow_html=True)

@st.fragment
def render_index_compact(cols_per_row: int=5) -> None:
    """在页面顶部渲染主要指数收盘行情：轻量数字卡 + 涨跌幅柱状图。

    与 render_index_mini_cards 区别：
      - 去掉了 sparkline、O/H/L/振幅 等细节，只保留名称、点位、涨跌幅；
      - 卡片横向平铺，更紧凑；
      - 下方统一展示涨跌幅柱状图，便于一眼比较强弱。
    """
    from datetime import datetime, timedelta
    from concurrent.futures import ThreadPoolExecutor
    from modules.fetcher import StockFetcher
    from modules.ui_theme import _theme_is_dark
    from modules.visualizer import UP_COLOR, DOWN_COLOR
    try:
        from modules.autorefresh import st_autorefresh
        is_open, _, refresh_ms = _index_market_status()
        if refresh_ms > 0:
            st_autorefresh(interval=refresh_ms, key='index_compact_autorefresh')
    except Exception as e:
        logger.warning(f"[widgets] 处理异常: {e}")
        pass
    end_date = now_cst_naive().date()
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime('%Y-%m-%d')
    cache_key = f'index_compact_{_index_cache_key()}'
    if cache_key in st.session_state:
        cards = st.session_state[cache_key]
    else:

        def _worker(info):
            try:
                return _build_index_card(info, StockFetcher(), start_str)
            except Exception as e:
                logger.warning(f"[widgets] 处理异常: {e}")
                return {**info, 'current': None, 'change': None, 'change_pct': None, 'spark': None}
        with ThreadPoolExecutor(max_workers=min(len(_INDEX_INFOS), 8)) as _ex:
            cards = list(_ex.map(_worker, _INDEX_INFOS))
        st.session_state[cache_key] = cards
        for k in list(st.session_state.keys()):
            if k.startswith('index_compact_') and k != cache_key:
                del st.session_state[k]
    dark = _theme_is_dark()
    txt = '#e2e8f0' if dark else '#1e293b'
    txt2 = '#94a3b8' if dark else '#64748b'
    card_bg = 'rgba(26,26,46,0.55)' if dark else '#ffffff'
    border = 'rgba(102,126,234,0.12)' if dark else '#E5E7EB'
    grid = 'rgba(148,163,184,0.15)' if dark else 'rgba(148,163,184,0.25)'
    # 2026-08-28 接入"新城"风格（E:\project\app_dist\微应用大厅 视觉）
    # 用 ui_kit.xc_section_header 替代裸 h2；指数卡用 .xc-grid + .xc-card 一次性渲染。
    from modules.ui_kit import xc_section_header  # 函数内惰性导入：与下方 except 中的局部重赋值共存
    try:
        inject_kit_css()
    except Exception as e:
        logger.warning(f"[widgets] 处理异常: {e}")
        xc_section_header = None
    if xc_section_header is not None:
        try:
            _, _, status_text_local = _index_market_status()
        except Exception as e:
            logger.warning(f"[widgets] 处理异常: {e}")
            status_text_local = '实时'
        st.markdown(xc_section_header('📉 主要指数', f'收盘 · {status_text_local}'),
                     unsafe_allow_html=True)
    else:
        st.markdown(f'<h2 style="color:{txt};">📉 主要指数（收盘）</h2>', unsafe_allow_html=True)

    def _index_dir(cp):
        """A 股红涨绿跌：返回 ('up'|'down'|'flat', sign)"""
        if cp is None:
            return ('flat', '')
        if cp > 0:
            return ('up', '+')
        if cp < 0:
            return ('down', '')
        return ('flat', '+' if cp == 0 else '')

    def _esc(s):
        return html.escape(str(s) if s is not None else '', quote=True)

    cards_html = []
    for card in cards:
        cur = card.get('current')
        cp = card.get('change_pct')
        ch = card.get('change')
        if cur is None:
            cards_html.append(
                f'<div class="xc-card"><div class="ctop"><div class="ico">📊</div>'
                f'<div><div class="cname">{_esc(card.get("name"))}</div>'
                f'<div class="csub">{_esc(card.get("code"))}</div></div></div>'
                f'<div class="value" style="color:{txt2};">—</div>'
                f'<div class="delta flat">暂无数据</div></div>'
            )
            continue
        d, sign = _index_dir(cp)
        num_color = UP_COLOR if d == 'up' else (DOWN_COLOR if d == 'down' else txt2)
        ch_s = f'{sign}{ch:.2f}' if ch is not None else ''
        cp_s = f'{sign}{cp:.2f}' if cp is not None else ''
        cards_html.append(
            f'<div class="xc-card">'
            f'<div class="ctop"><div class="ico">📊</div>'
            f'<div><div class="cname">{_esc(card.get("name"))}</div>'
            f'<div class="csub">{_esc(card.get("label"))} {_esc(card.get("code"))}</div></div></div>'
            f'<div class="value" style="color:{num_color};">{cur:.2f}</div>'
            f'<div class="delta {d}">{ch_s} ({cp_s}%)</div>'
            f'</div>'
        )
    st.markdown(f'<div class="xc-grid">{"".join(cards_html)}</div>', unsafe_allow_html=True)
    try:
        import plotly.graph_objects as go
        labels = [c['name'] for c in cards]
        values = [c['change_pct'] if c.get('change_pct') is not None else 0.0 for c in cards]
        bar_colors = [UP_COLOR if v >= 0 else DOWN_COLOR for v in values]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=labels, y=values, marker_color=bar_colors, text=[f'{v:+.2f}%' for v in values], textposition='outside', textfont={'color': txt, 'size': 11}, hovertemplate='%{x}: %{y:.2f}%<extra></extra>'))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin={'l': 40, 'r': 20, 't': 10, 'b': 30}, height=220, yaxis_title='涨跌幅 %', xaxis={'tickfont': {'color': txt2, 'size': 11}, 'showgrid': False}, yaxis={'tickfont': {'color': txt2, 'size': 11}, 'gridcolor': grid, 'zerolinecolor': txt2, 'zerolinewidth': 1}, font={'color': txt}, showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True, 'displayModeBar': False})
    except Exception as e:
        logger.warning(f"[widgets] 处理异常: {e}")
        st.caption(f'指数图表渲染失败：{e}')

def render_global_search() -> None:
    """侧边栏全局搜索框：输入关键词实时搜索股票，回车/点击结果进入行情看板。"""
    st.markdown('### 🔍 股票搜索')
    q = st.text_input('股票代码 / 名称 / 拼音', key='global_search_q', placeholder='如 600519 / 茅台 / mt', label_visibility='collapsed')
    if q:
        try:
            resp = requests.get(f'{API_BASE}/api/stocks/search', params={'q': q, 'limit': 8}, headers={'Authorization': f'Bearer {get_token()}'}, timeout=5)
            if resp.status_code == 200:
                body = resp.json()
                results = body.get('data') or []
                if results:
                    st.caption(f'🔎 找到 {len(results)} 个匹配')
                    for item in results:
                        label = f"{item.get('code', '')} {item.get('name', '')}"
                        if st.button(label, key=f"search_{item.get('code')}", width="stretch"):
                            _push_recent(item.get('code'), item.get('name'))
                            try:
                                st.query_params['pick_stock'] = item.get('code')
                            except Exception as e:
                                logger.warning(f"[widgets] 处理异常: {e}")
                                pass
                            safe_switch_page('pages/24_个股研究.py')
                else:
                    st.caption(f'😕 未找到与「{q}」匹配的股票')
                    st.caption('可尝试：代码（600519）、简称（茅台）或拼音首字母（mt）')
            elif resp.status_code in (401, 403):
                st.caption('🔒 请先登录后搜索')
            else:
                st.caption('搜索服务暂时不可用，请稍后再试')
        except Exception as e:
            logger.warning(f"[widgets] 处理异常: {e}")
            st.caption('搜索服务不可用')

def render_theme_toggle() -> None:
    """侧边栏深色 / 浅色快速切换（读/写 session_state['theme_mode']）。"""
    from modules.ui_theme import get_current_mode, apply_theme
    mode = st.session_state.get('theme_mode', get_current_mode())
    col_dark, col_light = st.columns(2)
    with col_dark:
        if st.button('🌙 暗夜', width="stretch", type='primary' if mode == 'dark' else 'secondary', key='theme_toggle_dark'):
            st.session_state['theme_mode'] = 'dark'
            apply_theme()
            persist_prefs()
            st.rerun()
    with col_light:
        if st.button('☀️ 白天', width="stretch", type='primary' if mode == 'light' else 'secondary', key='theme_toggle_light'):
            st.session_state['theme_mode'] = 'light'
            apply_theme()
            persist_prefs()
            st.rerun()

def render_topright_bar() -> None:
    """主区右上角通用栏：[★ 星辰 AI 弹层] [🌙 暗夜] [☀️ 白天]。

    由 require_auth() 在每个业务页面顶部注入，保证「不管用户在哪个界面」
    都能唤起 AI 咨询与切换主题。AI 咨询收进 popover 弹层，不占侧栏空间。
    """
    from modules.ui_theme import get_current_mode, apply_theme
    mode = st.session_state.get('theme_mode', get_current_mode())
    left, right = st.columns([0.55, 0.45])
    with right:
        c_ai, c_set, c_d, c_l = st.columns([0.46, 0.18, 0.18, 0.18])
        with c_ai:
            _logo_c, _pop_c = st.columns([0.2, 0.8])
            with _logo_c:
                st.markdown(STAR_AI_LOGO(18), unsafe_allow_html=True)
            with _pop_c:
                if hasattr(st, 'popover'):
                    with st.popover('星辰 AI', width="stretch"):
                        render_ai_consultant()
                else:
                    with st.sidebar:
                        render_ai_consultant()
        with c_set:
            if st.button('⚙️', key='top_settings', width="stretch", help='设置（进入「我的」偏好设置）'):
                safe_switch_page('pages/91_我的.py')
        with c_d:
            if st.button('🌙', key='top_theme_dark', width="stretch", type='primary' if mode == 'dark' else 'secondary', help='暗夜模式'):
                st.session_state['theme_mode'] = 'dark'
                apply_theme()
                persist_prefs()
                st.rerun()
        with c_l:
            if st.button('☀️', key='top_theme_light', width="stretch", type='primary' if mode == 'light' else 'secondary', help='白天模式'):
                st.session_state['theme_mode'] = 'light'
                apply_theme()
                persist_prefs()
                st.rerun()

def render_theme_toggle_topright() -> None:
    render_topright_bar()
from modules.background_tasks import submit_task_with_error, poll_task

def inject_global_widgets() -> None:
    """require_auth() 之后注入所有页面通用组件：右上角「★ 星辰 AI 弹层 + 主题开关」
    以及全局右下角「▲ 回到顶部」悬浮按钮。

    AI 咨询收进右上角 popover，任意页面唤起；不再占用左侧栏空间。
    """
    from modules.scroll_nav import inject_scroll_nav
    render_topright_bar()
    inject_scroll_nav()
_NAV_GROUPS = [('📘 新手引导', [('pages/96_新手教程.py', '新手教程', '📘')]), ('📊 市场纵览', [('pages/51_每日晨报.py', '每日晨报', '🌅'), ('pages/10_行情看板.py', '行情看板', '📈'), ('pages/14_智能盯盘.py', '智能盯盘', '👁️'), ('pages/35_资金流向.py', '资金流向', '🌊'), ('pages/23_事件追踪.py', '事件追踪', '📡'), ('pages/16_财报日历.py', '财报日历', '📅'), ('pages/12_板块轮动.py', '板块轮动', '🌈'), ('pages/50_市场情绪.py', '市场情绪', '🌡️'), ('pages/13_市场强弱.py', '市场强弱', '📊')]), ('🔎 选股研究', [('pages/24_个股研究.py', '个股研究', '🎯'), ('pages/31_形态选股.py', '形态选股', '🧭'), ('pages/22_基本面分析.py', '基本面分析', '🏛️'), ('pages/21_多股对比.py', '多股对比', '📊'), ('pages/33_ETF筛选.py', 'ETF筛选', '🧰')]), ('💼 我的持仓', [('pages/45_持仓中心.py', '持仓中心', '💼'), ('pages/34_体检扫描.py', '体检扫描', '🩺'), ('pages/47_价格预警.py', '价格预警', '🚨'), ('pages/95_数据导出.py', '数据导出', '📤'), ('pages/42_模拟交易.py', '模拟交易', '🎮')]), ('🧪 策略工具', [('pages/30_策略回测.py', '策略回测', '⚙️')]), ('💰 实盘 & 条件单', [('pages/43_实盘交易.py', '实盘交易', '💰'), ('pages/44_智能条件单.py', '智能条件单', '🤖')]), ('💬 社区与 AI', [('pages/53_星辰AI.py', '星辰 AI', '🌟'), ('pages/52_股吧.py', '股吧', '💬'), ('pages/94_消息中心.py', '消息中心', '🔔')])]
_NAV_ADMIN = [('pages/92_用户管理.py', '用户管理', '👥'), ('pages/93_系统配置.py', '系统配置', '🛠️')]

def sidebar_target():
    """返回子页「侧边栏内容」应写入的目标容器。

    - 独立运行（非嵌入）：返回 st.sidebar，保持原有侧边栏布局。
    - 被合并页嵌入时（_embed_active=True）：返回主区域容器，
      避免子页的 st.sidebar 写入覆盖父页的导航，导致侧边栏功能模块消失。
    """
    if st.session_state.get('_embed_active'):
        return st.container()
    return st.sidebar

def render_sidebar_nav() -> None:
    """在侧边栏顶部渲染自定义分组导航，并隐藏 Streamlit 原生平铺页面列表。

    仅注入视觉/导航，不改任何业务逻辑；所有 page_link 指向真实页面文件，
    导航后由 init_session_state()/_sync_query_params() 自动补回登录态。

    ⚠️ 无论是否嵌入都渲染（不再因 _embed_active 跳过），确保侧边栏导航常驻。
    """
    st.markdown('<style>[data-testid="stSidebarNav"],[data-testid="stSidebarNavItems"]{display:none!important;}/* 紧凑侧边栏导航：减少分组标题与链接间距，降低长导航的视觉负担 */[data-testid="stSidebar"] .stMarkdown [data-testid="stCaptionContainer"] {margin-top:4px!important;margin-bottom:2px!important;font-size:12px!important;}[data-testid="stSidebar"] [data-testid="stPageLink"] a {padding:4px 8px!important;margin:1px 0!important;border-radius:8px!important;}[data-testid="stSidebar"] [data-testid="stButton"] button {padding:4px 8px!important;min-height:28px!important;}</style>', unsafe_allow_html=True)

    def _nav_link(path: str, label: str, icon: str) -> None:
        """渲染单个导航项；page_link 在无浏览器 URL 上下文（如 AppTest headless）
        会抛 KeyError('url_pathname')，降级为按钮，避免整页崩溃。"""
        try:
            st.page_link(path, label=label, icon=icon)
        except Exception as e:
            logger.warning(f"[widgets] 处理异常: {e}")
            if st.button(f'{icon} {label}', key=f'navbtn_{label}', width="stretch"):
                safe_switch_page(path)
    try:
        with st.sidebar:
            st.markdown('### 🧭 导航')
            for gname, items in _NAV_GROUPS:
                st.caption(gname)
                for path, label, icon in items:
                    _nav_link(path, label, icon)
            st.caption('👤 账户')
            _nav_link('pages/91_我的.py', '我的', '👤')
            if is_admin():
                for path, label, icon in _NAV_ADMIN:
                    _nav_link(path, label, icon)
            _recents = get_recent_stocks()
            if _recents:
                st.caption('🕘 最近浏览')
                for _r in _recents[:5]:
                    _rc = _r.get('code', '')
                    _rn = _r.get('name', '')
                    if not _rc:
                        continue
                    if st.button(f'{_rn} {_rc}', key=f'sb_recent_{_rc}', width="stretch"):
                        try:
                            st.query_params['pick_stock'] = _rc
                        except Exception as e:
                            logger.warning(f"[widgets] 处理异常: {e}")
                            pass
                        safe_switch_page('pages/11_股票选取.py')
            st.markdown('---')
            try:
                st.page_link('app.py', label='返回首页', icon='🏠')
            except Exception as e:
                logger.warning(f"[widgets] 处理异常: {e}")
                pass
    except Exception as e:
        with st.sidebar:
            xc_handle_error("导航渲染失败", e, hint="请稍后重试")

@st.cache_data(ttl=30, show_spinner=False)
def _cached_watchlist_count(token: str) -> int:
    """缓存自选股数量请求，避免每个页面加载都打一次后端（性能提速）。"""
    try:
        resp = requests.get(f'{API_BASE}/api/watchlist', headers={'Authorization': f'Bearer {token}'}, timeout=5)
        if resp.status_code == 200:
            return len(resp.json().get('data') or [])
    except Exception as e:
        logger.warning(f"[widgets] 处理异常: {e}")
        pass
    return 0

def render_notifications() -> None:
    """侧边栏通知中心：展示自选股数量、最近登录时间、使用提示。"""
    st.markdown('### 🔔 通知中心')
    wl_count = _cached_watchlist_count(get_token() or '')
    st.info(f'⭐ 自选股：**{wl_count}** 只')
    try:
        resp = requests.get(f'{API_BASE}/api/auth/logins', headers={'Authorization': f'Bearer {get_token()}'}, timeout=5)
        if resp.status_code == 200:
            logs = resp.json().get('data') or []
            if logs:
                last = logs[0].get('created_at', '')
                rel = _rel_time(last)
                st.caption(f"🕒 上次登录：{rel or last[:19].replace('T', ' ')}")
    except Exception as e:
        logger.warning(f"[widgets] 处理异常: {e}")
        pass
    with st.expander('📌 使用提示', expanded=False):
        st.markdown('\n        **K 线图（股票选取 / 个股分析）**\n        - 顶部可切换 **日K / 周K / 月K** 周期\n        - 均线支持多选 + 自定义（如 `30,90`）\n        - 「显示 K 线数量 / 显示位置」滑块定位任意区间\n        - **鼠标拖拽** 可切换「平移」与「区域缩放」（框选放大）\n        - 图中自动标注可见窗口的 **区间最高 / 区间最低**，下方显示区间涨幅、振幅、均价\n\n        **全局导航**\n        - 下滚超过一屏后，右侧浮现 **▲ 回到顶部** 悬浮按钮\n        - 星辰 AI 对话页右下角有 **▼ 回到底部** 按钮\n        - 浏览器弹出的「清除缓存」确认框已自动拦截，无需手动处理\n\n        **其他模块**\n        - 行情看板支持板块、龙虎榜、自选股监控\n        - 事件追踪综合三类信号评分；股吧可发帖 / 评论 / 点赞\n        - 右侧 **★ 星辰AI** 可随时咨询多市场分析\n        - 新手？先看 **📘 新手教程**：三步上手 + 模块导览 + 术语表 + 教学视频\n\n        **市场异动 & 容错**\n        - 侧边栏 **🔔 市场异动** 铃铛常驻，点开看未读摘要、相对时间、一键全部已读\n        - 任意页面底部可挂「近期异动提醒」面板，支持「仅看未读」过滤\n        - 单模块取数失败会被**隔离**为该区块错误卡，并带「🔄 重试本区块」按钮，不影响其它模块\n        - 退出登录前会弹**确认框**，避免误触\n        ')

def render_breadcrumb(items: list[str]) -> None:
    """页面顶部面包屑。items 形如 ['首页', '行情看板']。"""
    st.markdown(' › '.join((f'**{i}**' for i in items)), help='当前位置')

def _push_recent(code: str, name: str) -> None:
    if 'recent_stocks' not in st.session_state:
        st.session_state['recent_stocks'] = []
    recents = st.session_state['recent_stocks']
    recents = [r for r in recents if r.get('code') != code]
    recents.insert(0, {'code': code, 'name': name})
    st.session_state['recent_stocks'] = recents[:8]

def get_recent_stocks() -> list:
    return st.session_state.get('recent_stocks', [])

def password_strength(pwd: str) -> tuple[int, str]:
    """返回 (分数 0-4, 等级文本)。"""
    if not pwd:
        return (0, '空')
    score = 0
    if len(pwd) >= 8:
        score += 1
    if len(pwd) >= 12:
        score += 1
    if any((c.isupper() for c in pwd)) and any((c.islower() for c in pwd)):
        score += 1
    if any((c.isdigit() for c in pwd)) and any((c in '!@#$%^&*()_+-=[]{}|;:,.<>?/' for c in pwd)):
        score += 1
    levels = ['弱', '弱', '中', '强', '很强']
    return (score, levels[score])
_SYMBOLS = set('!@#$%^&*()_+-=[]{}|;:,.<>?/')

def password_checklist(pwd: str) -> dict:
    """返回密码各维度的达标情况（新能力，供注册/修改密码页结构化展示与校验）。

    与 password_strength 共用同一套判定维度，但给出「逐项是否达标」的明细，
    而非只给总分，便于前端逐条提示用户（如「至少 8 位」「需含大小写」）。
    空密码视为全部不达标，但单独标注 empty 便于 UI 区分「未输入」与「太弱」。
    """
    if not pwd:
        return {'empty': True, 'length8': False, 'length12': False, 'mixed_case': False, 'digit_and_symbol': False, 'score': 0, 'level': '空'}
    length8 = len(pwd) >= 8
    length12 = len(pwd) >= 12
    mixed_case = any((c.isupper() for c in pwd)) and any((c.islower() for c in pwd))
    digit_and_symbol = any((c.isdigit() for c in pwd)) and any((c in _SYMBOLS for c in pwd))
    score = int(length8) + int(length12) + int(mixed_case) + int(digit_and_symbol)
    levels = ['弱', '弱', '中', '强', '很强']
    return {'empty': False, 'length8': length8, 'length12': length12, 'mixed_case': mixed_case, 'digit_and_symbol': digit_and_symbol, 'score': score, 'level': levels[score]}

def get_session_remaining() -> int | None:
    """解码当前 JWT 的 exp，返回剩余秒数；无法解析时返回 None。"""
    import time as _time
    import jwt as _jwt
    token = get_token()
    if not token:
        return None
    try:
        payload = _jwt.decode(token, options={'verify_signature': False})
        exp = payload.get('exp')
        if not exp:
            return None
        return max(0, int(exp - _time.time()))
    except Exception as e:
        logger.warning(f"[widgets] 处理异常: {e}")
        return None

def render_session_countdown() -> None:
    """显示当前登录会话剩余时间（自动登出倒计时）。"""
    remain = get_session_remaining()
    if remain is None:
        st.caption('⏱️ 会话状态：未知')
        return
    minutes = remain // 60
    seconds = remain % 60
    st.caption(f'⏱️ 会话剩余：{minutes}分{seconds}秒（超时将自动登出）')
from modules._widgets_ai import _slim_context, _current_stock_context, _ai_popover_theme_css, _chat_history_for_context, _ai_md, _render_ai_chat, _ai_scroll_to_bottom_component, _poll_ai_consult_task, render_ai_consultant