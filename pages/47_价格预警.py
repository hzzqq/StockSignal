"""
页面9：自选股多维预警
支持四类预警：
  - 价格（price）：涨破/跌破目标价（实时比价）
  - 技术形态（pattern）：个股出现指定技术形态时触发
  - 成交量异动（volume）：当日量比 ≥ 阈值时触发
  - 公告（announcement）：近期新闻/公告含指定关键词时触发
触发检查在页面访问时于前端执行（与原有价格预警一致）；数据不足时标记为「待验证」。
"""
import json
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time as _time
from threading import Lock as _Lock
from concurrent.futures import ThreadPoolExecutor
import logging
from modules.ui_kit import info_banner
from modules.page_utils import fmt_rel as _fmt_rel
logger = logging.getLogger(__name__)
from modules.page_utils import render_standard_page, get_fetcher
import modules.scroll_nav as sn
from modules.session import api_get, api_post, api_put, api_delete, api_quote, api_kline, trading_autorefresh, safe_switch_page
from modules.cleaner import DataCleaner
from modules.technical import full_analysis
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, _toast
from modules.page_guard import safe_fragment
from modules.format_helpers import safe_float, to_float
import streamlit.components.v1 as components
from modules.fundflow import _ensure_proxy_and_ssl
_ensure_proxy_and_ssl()
