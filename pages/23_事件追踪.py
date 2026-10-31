"""
页面2：事件追踪
信号评分、事件时间轴、事件管理、新闻挖掘、情感报告

独立性优化（关键）：
- 每个耗时模块用 @safe_fragment 包裹，点击某模块按钮只重跑「该 fragment」，
  不会冻结整页，其它模块保持原样（真正的同页模块独立运行）。
- 各模块结果存入各自独立的 session_state key，fragment 内从 session_state 恢复展示。
- 事件时间轴表单的日期/滑块控件 key 与 session_state 变量同名双向绑定，
  去掉 st.rerun()，避免整页重跑；区间快捷按钮只改 session_state，fragment 自动跟随刷新。
"""
import streamlit as st
import pandas as pd
import html
from datetime import datetime, timedelta
from modules.page_guard import safe_fragment
from modules.page_utils import render_standard_page, get_fetcher
from modules.ui_theme import sf_metric
from modules.page_widgets import _empty_info
from modules.event_levels import STRENGTH_ORDER  # T-288：五档单一真理源
from modules.ui_kit import xc_error_box, xc_handle_error, xc_info_banner, xc_success_box, xc_warn_box, info_banner, xc_content_card
from modules.page_utils import fmt_rel as _fmt_rel
render_standard_page(title='事件追踪', icon='🔔', caption='⚠️ 数据仅供参考，不构成投资建议', layout='wide')

lk_p1, lk_p2 = st.columns([1, 1])
with lk_p1:
    if st.button('👁️ 智能盯盘', key='lk_go_k', width="stretch"):
        st.switch_page('pages/14_智能盯盘.py')
with lk_p2:
    if st.button('🔍 个股研究', key='lk_go_rs', width="stretch"):
        st.switch_page('pages/24_个股研究.py')
from modules.signal import SignalEngine
from modules.colors import UP_COLOR, DOWN_COLOR
from modules.search_ui import stock_search_input
from modules.session import api_kline, api_intraday, trading_autorefresh, api_post
trading_autorefresh(key='event_autorefresh')
_FOR_ALL_KEYS = ['sig_scores', 'sig_scores_error', 'live_kw_result', 'tl_existing_events', 'tl_realtime_events', 'tl_df', 'tl_chart_title', 'tl_start_idx', 'tl_n_show', 'tl_start_date', 'tl_end_date', 'mined_result', 'sentiment_report', 'sentiment_report_error', 'sig_ticker_last']
for _k in _FOR_ALL_KEYS:
    if _k not in st.session_state:
        st.session_state[_k] = None
if st.session_state.get('tl_start_idx') is None:
    st.session_state.tl_start_idx = 0
if st.session_state.get('tl_n_show') is None:
    st.session_state.tl_n_show = 60
if st.session_state.get('tl_start_date') is None:
    st.session_state.tl_start_date = (datetime.now() - timedelta(days=180)).date()
if st.session_state.get('tl_end_date') is None:
    st.session_state.tl_end_date = datetime.now().date()
if '_recent_viewed' not in st.session_state:
    st.session_state._recent_viewed = []
if '_fav_set' not in st.session_state:
    st.session_state._fav_set = []

@st.cache_resource
def get_engine():
    return SignalEngine()
engine = get_engine()
fetcher = get_fetcher()

@st.cache_data(show_spinner=False, ttl=60)
def _cached_intraday(ticker):
    """个股分时数据：优先后端 /api/intraday，回退本地 fetcher。返回 (df, prev_close, trade_date) 或 None。"""
    if not ticker:
        return None
    try:
        rec = api_intraday(ticker)
        if rec and isinstance(rec.get('records'), list) and rec['records']:
            return (pd.DataFrame(rec['records']), rec.get('prev_close'), rec.get('trade_date'))
    except Exception:
        pass
    try:
        _df, _pc, _dt = fetcher.get_stock_intraday_sina(ticker)
        if _df is not None and (not _df.empty):
            return (_df, _pc, _dt)
    except Exception:
        pass
    return None

def _news_fallback_url(title: str, source: str='') -> str:
    """原文链接缺失时的兜底：用搜索引擎按标题检索，保证标题始终可点击跳转。"""
    from urllib.parse import quote
    q = title
    return f'https://www.baidu.com/s?wd={quote(q)}'
