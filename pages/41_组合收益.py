"""
页面 H：自选股组合收益跟踪
基于仓位管理中的持仓，构建组合历史净值曲线（按剩余股数加权），与沪深300基准对比，
展示累计收益、个股贡献、最大回撤。数据层复用 modules/portfolio.PortfolioManager 与
modules/fetcher.StockFetcher.get_daily（已验证可用）。
"""

from modules.portfolio_views import render_portfolio_returns

render_portfolio_returns()

# ── 方法学与来源注脚（B 类页五段式：收尾一段；页面主体由 modules.portfolio_views 渲染，页头无天然 KPI 带数据）──
import streamlit as st  # noqa: I001
from modules.ui_kit import xc_subheader
xc_subheader("口径与来源", icon="📌")
st.caption(
    "净值曲线=持仓记录按剩余股数加权的日线估值（modules/portfolio + "
    "StockFetcher.get_daily）；基准=沪深300公开日线；收益贡献/最大回撤=本地计算。"
    "均为模拟或历史数据，仅供学习，不构成投资建议。"
)
