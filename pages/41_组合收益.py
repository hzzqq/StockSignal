"""
页面 H：自选股组合收益跟踪
基于仓位管理中的持仓，构建组合历史净值曲线（按剩余股数加权），与沪深300基准对比，
展示累计收益、个股贡献、最大回撤。数据层复用 modules/portfolio.PortfolioManager 与
modules/fetcher.StockFetcher.get_daily（已验证可用）。
"""

from modules.portfolio_views import render_portfolio_returns

render_portfolio_returns()
