"""
页面：仓位管理
持仓记录、卖出交易、盈亏统计、Excel导出
"""

from modules.portfolio_views import render_position_manager

render_position_manager()

# ── 方法学与来源注脚（B 类页五段式：收尾一段；页面主体由 modules.portfolio_views 渲染，页头无天然 KPI 带数据）──
import streamlit as st
from modules.ui_kit import xc_subheader
xc_subheader("口径与来源", icon="📌")
st.caption(
    "持仓记录=本地导入/手工记录（模拟数据）；盈亏统计=持仓按日线估值"
    "（modules/portfolio + StockFetcher.get_daily，东方财富/新浪公开日线）。"
    "均为模拟或历史数据，仅供学习，不构成投资建议。"
)
