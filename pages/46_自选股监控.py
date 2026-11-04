"""
页面C：自选股实时监控
────────────────────────
一览自选股实时现价与涨跌幅（A股红涨绿跌），并行拉取行情，异常自动回退本地源。
支持一键刷新、跳转「形态选股」对自选股做技术体检、跳转「个股分析」做深度诊断。
纯前端聚合，不改动任何主功能逻辑。
"""

from modules.portfolio_views import render_watchlist_monitor

render_watchlist_monitor()

# ── 方法学与来源注脚（B 类页五段式：收尾一段；页面主体由 modules.portfolio_views 渲染，页头无天然 KPI 带数据）──
import streamlit as st  # noqa: I001
from modules.ui_kit import xc_subheader
xc_subheader("口径与来源", icon="📌")
st.caption(
    "自选股实时行情=后端 API 并行拉取（东方财富/新浪，异常自动回退本地源）；"
    "现价与涨跌幅为页面访问时点快照，A股红涨绿跌。仅供参考，不构成投资建议。"
)
