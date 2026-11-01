"""
股票选取模块
------------
位于「行情看板」与「个股分析」之间。
- 从行情看板迁入：参数设置、K 线图、技术面分析。
- 新增：加入自选股 / 加入垃圾股、用户打分、自选股/垃圾股折叠展示（可排序、可跳转）。
"""

from modules.stock_research import render_stock_picker

render_stock_picker()

# ── 方法学与来源注脚（B 类页五段式：收尾一段；页面主体由 modules.stock_research 渲染，页头无天然 KPI 带数据）──
import streamlit as st
st.markdown("---")
st.caption(
    "口径与来源：行情/K线=东方财富、新浪公开日线（modules/fetcher，daily_cache 缓存）；"
    "技术指标与选股打分=本地规则计算（modules/technical），非 AI 洞见。"
    "打分仅供参考，不构成投资建议。"
)
