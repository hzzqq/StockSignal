"""
页面A：每日晨报 / 复盘笔记
- 每日晨报：聚合板块涨跌概览、自选股快照、相关新闻，生成开盘前速览。
- 复盘笔记：当日复盘记录，本地按日期持久化（data/review_notes_<date>.md）。
"""
import os
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.session import api_get, safe_switch_page
import modules.scroll_nav as sn
from modules.news import NewsFetcher
from modules.page_guard import safe_fragment
from modules.page_utils import render_standard_page, get_fetcher
from modules.ui_theme import sf_metric
from modules.page_widgets import _empty_info, _section_title
from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, info_banner, xc_content_card
from modules.event_factor import event_driven_long_list  # 事件驱动看多榜（真实 P1 EV 信号选股池）
from modules.page_utils import fmt_rel as _fmt_rel
today = date.today().strftime('%Y-%m-%d')
dark = render_standard_page(title='每日晨报 / 复盘笔记', icon='🌅', caption=f'生成日期：{today}（数据来源：板块行情 + 自选股 + 新闻；开盘前速览，非投资建议）', layout='wide')
from modules.widgets import render_index_compact
render_index_compact(cols_per_row=5)
fetcher = get_fetcher()

@st.cache_data(ttl=600, show_spinner=False)
def _cached_news(keyword: str, limit: int=15):
    """缓存新闻 10 分钟 + 失败重试（最多 3 次），避免重复请求与瞬时失败。#542-10"""
    for _i in range(3):
        try:
            df = NewsFetcher().fetch(keyword=keyword, source='auto', limit=limit)
            if df is not None:
                return df
        except Exception:
            continue
    return None
from modules.ssl_helper import ssl_bypass as _ssl_bypass
from modules.fundamental_helpers import calc_alr, fund_one

def _calc_alr(code: str):
    """委托 fundamental_helpers.calc_alr（#545-16 消除与 C_自选股监控 的逐字重复）。"""
    return calc_alr(code, fetcher)

def _fund_one(code: str):
    """委托 fundamental_helpers.fund_one（#545-16 消除重复）。"""
    return fund_one(code, fetcher)

def _quote_one(code: str):
    """线程内取实时行情（本地 fetcher，规避线程内后端 token 调用）。"""
    try:
        return (code, fetcher.get_realtime_quote(code))
    except Exception:
        return (code, None)

@st.cache_data(show_spinner=False, ttl=300)
def _cached_sector():
    """板块列表跨重跑/跨页面会话级缓存，减少重复网络请求。"""
    try:
        return fetcher.get_sector_list()
    except Exception:
        return None

def _fmt_pct(v):
    """安全格式化涨跌幅：None/NaN 返回 —，避免 f-string 数值格式化崩溃。"""
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return '—'
        return f'{float(v):+.2f}%'
    except Exception:
        return '—'
