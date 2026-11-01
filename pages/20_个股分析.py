"""
页面2：个股分析
暗色模式「决策仪表盘 · 个股深度分析」（参考 002947 暗色版 .sf-* 组件类）。

严格遵循参考文档「绿涨红跌」配色：涨/利好/买入 = 绿(#009e60)，跌/利空/卖出 = 红(#dc2626)，
中性/持有 = 琥珀(#d97706)。所有外部数据获取均包在 try/except 中，失败时 st.warning。
仅做前端/UI，不改动 backend 或任何数据逻辑。
"""

from modules.stock_research import render_stock_analysis

render_stock_analysis()

# ── 方法学与来源注脚（B 类页五段式：收尾一段；页面主体由 modules.stock_research 渲染，页头无天然 KPI 带数据）──
import streamlit as st
from modules.ui_kit import xc_subheader
xc_subheader("口径与来源", icon="📌")
st.caption(
    "决策仪表盘数据=实时行情（东方财富/新浪）+日线缓存+技术面本地计算；"
    "五维雷达/作战计划=规则生成（modules/stock_research），非 AI 洞见。"
    "所有结论仅供参考，不构成投资建议。"
)
