"""
模拟交易组合（Paper Trading）
--------------------------------
一个完全自包含的模拟交易模块：用虚拟资金买卖 A 股，跟踪持仓、盈亏与净值曲线。

  • 持仓 / 成交记录持久化到本地 data/paper_{user}.json（刷新不丢失，模块独立运行）
  • 现价取自实时行情，失败降级到日线收盘价
  • 支持买入 / 卖出 / 重置账户，展示总资产、累计盈亏、胜率与净值曲线

不接入真实券商，仅用于策略演练与学习。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
from datetime import datetime
import streamlit.components.v1 as components
from modules.page_utils import render_standard_page
from modules.ui_theme import sf_metric
import modules.scroll_nav as sn
from modules.session import get_user, trading_autorefresh
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, safe_fragment
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, _toast, UP, DOWN
from modules.ui_kit import xc_error_box, xc_kpi_grid, xc_success_box, xc_warn_box, xc_content_card
from modules.page_utils import fmt_rel as _fmt_rel
dark = render_standard_page(title='模拟交易组合', icon='🎮', caption='虚拟资金练习；持仓持久化到本地，模块独立运行，不影响真实账户。')

st.caption('⚠️ 模拟交易，仅供学习，不构成任何投资建议。')
