"""
页面：仓位管理
持仓记录、卖出交易、盈亏统计、Excel导出
"""

import os

import streamlit as st
import pandas as pd
from datetime import datetime

from modules.ui_theme import apply_page_config
apply_page_config(page_title="仓位管理", page_icon="💰", layout="wide")
st.session_state["_active_page"] = __file__
st.title("💰 仓位管理")

from modules.portfolio import PortfolioManager
from modules.visualizer import Visualizer
from modules.search_ui import stock_search_input
from modules.fetcher import StockFetcher
from modules.session import require_auth, render_user_badge, api_quote, api_kline

# 鉴权门禁
require_auth()
render_user_badge(sidebar=True)

pm = PortfolioManager()
fetcher = StockFetcher()

# 初始化 session_state 默认值
if "default_shares" not in st.session_state:
    st.session_state.default_shares = 1000


def format_quote_table(quote):
    """把实时行情格式化成买卖盘 DataFrame。"""
    if not quote:
        return None
    rows = []
    for i in range(5):
        bid = quote["bid"][i]
        ask = quote["ask"][i]
        rows.append({
            "买盘": f"买{i+1}",
            "买价": f"¥{bid['price']:.2f}",
            "买量": f"{int(bid['volume']):,}",
            "卖盘": f"卖{i+1}",
            "卖价": f"¥{ask['price']:.2f}",
            "卖量": f"{int(ask['volume']):,}",
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# 顶部：当前持仓概览
# ------------------------------------------------------------------
st.subheader("当前持仓概览")
positions = pm.get_positions()
if positions.empty:
    st.info("暂无持仓记录。")
else:
    display_pos = positions.copy()
    if "name" in display_pos.columns:
        display_pos = display_pos.drop(columns=["name"])
    display_pos["股票"] = display_pos["ticker"].apply(lambda x: fetcher.get_stock_name(x))
    # 格式化显示
    if "shares" in display_pos.columns:
        display_pos["买入股数"] = display_pos["shares"].apply(lambda x: f"{int(x):,}")
    if "remaining_shares" in display_pos.columns:
        display_pos["剩余股数"] = display_pos["remaining_shares"].apply(lambda x: f"{int(x):,}")
    if "buy_price" in display_pos.columns:
        display_pos["买入价"] = display_pos["buy_price"].apply(lambda x: f"¥{x:.2f}")
    if "cost" in display_pos.columns:
        display_pos["成本"] = display_pos["cost"].apply(lambda x: f"¥{x:,.2f}")
    display_pos["买入日期"] = display_pos["buy_date"]
    display_pos["备注"] = display_pos["note"].fillna("")
    show_cols = ["股票", "ticker", "买入日期", "买入价", "买入股数", "剩余股数", "成本", "备注"]
    show_cols = [c for c in show_cols if c in display_pos.columns]
    st.dataframe(display_pos[show_cols], width="stretch", hide_index=True)

st.markdown("---")

# ------------------------------------------------------------------
# 买入股票
# ------------------------------------------------------------------
st.subheader("买入股票")

# 快捷股数选择
st.markdown("**⚡ 快捷选择股数：**")
quick_cols = st.columns(5)
for col, qv in zip(quick_cols, [100, 500, 1000, 2000, 5000]):
    if col.button(f"{qv:,} 股", width="stretch", key=f"buy_quick_{qv}"):
        st.session_state.default_shares = qv
        st.rerun()

buy_quote = None
with st.form("buy_position_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        buy_ticker = stock_search_input(
            label="股票搜索",
            key="buy_ticker",
            default="601088",
            placeholder="输入代码或名称搜索，如：601088 / 中国神华 / 神华",
        )
        buy_label = fetcher.get_stock_name(buy_ticker) or buy_ticker
        # 实时五档行情
        if buy_ticker:
            buy_quote = api_quote(buy_ticker)
            if buy_quote is None:
                buy_quote = fetcher.get_realtime_quote(buy_ticker)
            if buy_quote:
                st.caption(f"📈 最新价 ¥{buy_quote['current']:.2f}  {buy_quote['datetime']}")
                st.dataframe(format_quote_table(buy_quote), width="stretch", hide_index=True)
            else:
                st.caption("⚠️ 未能获取实时行情")
    with col2:
        buy_date = st.date_input("买入日期", value=datetime.now(), key="buy_date")
        # 默认成交价：卖一价（买入按卖方最低价成交）
        default_buy_price = 20.00
        if buy_quote and buy_quote.get("ask"):
            default_buy_price = buy_quote["ask"][0]["price"]
        else:
            try:
                _kline_start = (datetime.now() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
                _kline_end = datetime.now().strftime("%Y-%m-%d")
                _records = api_kline(buy_ticker, start=_kline_start, end=_kline_end)
                price_df = pd.DataFrame(_records) if _records is not None else fetcher.get_daily(
                    buy_ticker, start=_kline_start, end=_kline_end
                )
                default_buy_price = float(price_df.iloc[-1]["close"]) if price_df is not None and not price_df.empty else 20.00
            except Exception:
                default_buy_price = 20.00
        buy_price = st.number_input(
            "买入成交价", value=round(default_buy_price, 2), step=0.01,
            format="%.2f", min_value=0.01,
            help="默认按卖一价填充，可手动修改为卖二价或其他实际成交价"
        )
    with col3:
        buy_shares = st.number_input(
            "📊 买入股数",
            value=st.session_state.default_shares,
            min_value=1, step=100, format="%d",
            help="点击 ± 按钮步进调节，或直接输入数字"
        )
        buy_note = st.text_input("备注", value="", key="buy_note")

    buy_submitted = st.form_submit_button("✅ 添加持仓")

if buy_submitted:
    try:
        pm.add_position(
            ticker=buy_ticker,
            buy_date=buy_date.strftime("%Y-%m-%d"),
            buy_price=buy_price, shares=int(buy_shares), note=buy_note
        )
        st.success(
            f"买入成功: {buy_label} ({buy_ticker}) "
            f"{int(buy_shares):,}股 @¥{buy_price:.2f}"
        )
        st.rerun()
    except Exception as e:
        st.error(f"买入失败: {e}")

st.markdown("---")

# ------------------------------------------------------------------
# 卖出股票
# ------------------------------------------------------------------
st.subheader("卖出股票")

if not positions.empty:
    remaining = positions["remaining_shares"] if "remaining_shares" in positions.columns else positions["shares"]
    sellable_positions = positions[remaining > 0].copy()
else:
    sellable_positions = positions.copy()

if sellable_positions.empty:
    st.info("当前没有可卖出的持仓。")
else:
    sell_quote = None
    with st.form("sell_position_form"):
        # 构造选项：ticker + 名称 + 可卖股数
        sell_options = {}
        for _, row in sellable_positions.iterrows():
            ticker = row["ticker"]
            name = fetcher.get_stock_name(ticker) or ticker
            sellable = int(row.get("remaining_shares", row["shares"]))
            sell_options[f"{name} ({ticker}) — 可卖 {sellable:,} 股"] = ticker

        selected_label = st.selectbox("选择要卖出的持仓", options=list(sell_options.keys()), key="sell_select")
        sell_ticker = sell_options[selected_label]
        sellable_shares = pm.get_sellable_shares(sell_ticker)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("可卖股数", f"{sellable_shares:,} 股")
            # 实时五档行情
            sell_quote = api_quote(sell_ticker)
            if sell_quote is None:
                sell_quote = fetcher.get_realtime_quote(sell_ticker)
            if sell_quote:
                st.caption(f"📈 最新价 ¥{sell_quote['current']:.2f}  {sell_quote['datetime']}")
                st.dataframe(format_quote_table(sell_quote), width="stretch", hide_index=True)
            else:
                st.caption("⚠️ 未能获取实时行情")
        with col2:
            sell_date = st.date_input("卖出日期", value=datetime.now(), key="sell_date")
            # 默认成交价：买一价（卖出按买方最高价成交）
            default_sell_price = 20.00
        if sell_quote and sell_quote.get("bid"):
            default_sell_price = sell_quote["bid"][0]["price"]
        else:
            try:
                _kline_start = (datetime.now() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
                _kline_end = datetime.now().strftime("%Y-%m-%d")
                _records = api_kline(sell_ticker, start=_kline_start, end=_kline_end)
                price_df = pd.DataFrame(_records) if _records is not None else fetcher.get_daily(
                    sell_ticker, start=_kline_start, end=_kline_end
                )
                default_sell_price = float(price_df.iloc[-1]["close"]) if price_df is not None and not price_df.empty else 20.00
            except Exception:
                default_sell_price = 20.00
            sell_price = st.number_input(
                "卖出成交价", value=round(default_sell_price, 2), step=0.01,
                format="%.2f", min_value=0.01,
                help="默认按买一价填充，可手动修改为买二价或其他实际成交价"
            )
        with col3:
            sell_shares = st.number_input(
                "📊 卖出股数",
                value=min(1000, sellable_shares),
                min_value=1,
                max_value=int(sellable_shares),
                step=100, format="%d",
                help="最多可卖剩余股数"
            )
            sell_note = st.text_input("备注", value="", key="sell_note")

        sell_submitted = st.form_submit_button("✅ 记录卖出")

    if sell_submitted:
        try:
            result = pm.sell_position(
                ticker=sell_ticker,
                sell_date=sell_date.strftime("%Y-%m-%d"),
                sell_price=sell_price,
                sell_shares=int(sell_shares),
                note=sell_note
            )
            sell_label = fetcher.get_stock_name(sell_ticker) or sell_ticker
            st.success(
                f"卖出成功: {sell_label} ({sell_ticker}) "
                f"{int(sell_shares):,}股 @¥{sell_price:.2f}，"
                f"成交金额 ¥{result['proceeds']:,.2f}"
            )
            st.rerun()
        except Exception as e:
            st.error(f"卖出失败: {e}")

st.markdown("---")

# ------------------------------------------------------------------
# 删除持仓
# ------------------------------------------------------------------
with st.expander("🗑️ 删除持仓"):
    positions = pm.get_positions()  # 刷新
    if positions.empty:
        st.info("暂无持仓可删除。")
    else:
        del_index = st.number_input(
            "选择要删除的行号（从 0 开始）",
            min_value=0, max_value=len(positions) - 1,
            value=0, step=1
        )
        c_del, _ = st.columns([1, 4])
        if c_del.button("⚠️ 确认删除", type="primary"):
            removed = pm.remove_position(int(del_index))
            if removed is not None:
                st.success(f"已删除: {removed.get('ticker', '')}")
                st.rerun()

st.markdown("---")

# ------------------------------------------------------------------
# 卖出记录
# ------------------------------------------------------------------
st.subheader("卖出记录")
trades = pm.get_trades()
if trades.empty:
    st.info("暂无卖出记录。")
else:
    display_trades = trades.copy()
    if "name" in display_trades.columns:
        display_trades = display_trades.drop(columns=["name"])
    display_trades["股票"] = display_trades["ticker"].apply(lambda x: fetcher.get_stock_name(x))
    display_trades["卖出日期"] = display_trades["sell_date"]
    display_trades["卖出价"] = display_trades["sell_price"].apply(lambda x: f"¥{x:.2f}")
    display_trades["卖出股数"] = display_trades["sell_shares"].apply(lambda x: f"{int(x):,}")
    display_trades["成交金额"] = display_trades["proceeds"].apply(lambda x: f"¥{x:,.2f}")
    display_trades["备注"] = display_trades["note"].fillna("")
    show_cols = ["股票", "ticker", "卖出日期", "卖出价", "卖出股数", "成交金额", "备注"]
    st.dataframe(display_trades[show_cols], width="stretch", hide_index=True)

st.markdown("---")

# ------------------------------------------------------------------
# 盈亏统计
# ------------------------------------------------------------------
st.subheader("盈亏统计")
positions = pm.get_positions()  # 刷新
if not positions.empty:
    with st.spinner("正在获取行情并计算盈亏..."):
        try:
            pnl_df = pm.calc_pnl()
            summary = pm.summary()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("总成本", f"¥{summary['total_cost']:,.2f}")
            with col2:
                st.metric("总市值", f"¥{summary['total_market_value']:,.2f}")
            with col3:
                delta_pnl = summary.get("delta_pnl", 0)
                st.metric(
                    "总盈亏", f"¥{summary['total_pnl']:,.2f}",
                    delta=f"{summary.get('delta_pnl', 0):+.2f}" if abs(delta_pnl or 0) > 0.01 else None
                )
            with col4:
                st.metric("总收益率", f"{summary['total_pnl_pct']:+.2f}%")

            # 盈亏柱状图
            if not pnl_df.empty:
                st.markdown("---")
                fig = Visualizer.portfolio_pnl(pnl_df)
                st.plotly_chart(fig, width="stretch")

                st.markdown("#### 持仓明细")
                display_pnl = pnl_df.copy()
                if "name" in display_pnl.columns:
                    display_pnl = display_pnl.drop(columns=["name"])
                display_pnl["股票"] = display_pnl["ticker"].apply(lambda x: fetcher.get_stock_name(x))
                display_pnl["买入股数"] = display_pnl["shares"].apply(lambda x: f"{int(x):,}")
                display_pnl["剩余股数"] = display_pnl["remaining_shares"].apply(lambda x: f"{int(x):,}")
                display_pnl["买入价"] = display_pnl["buy_price"].apply(lambda x: f"¥{x:.2f}")
                display_pnl["现价"] = display_pnl["current_price"].apply(lambda x: f"¥{x:.2f}")
                display_pnl["市值"] = display_pnl["market_value"].apply(lambda x: f"¥{x:,.2f}")
                display_pnl["已实现盈亏"] = display_pnl["realized_pnl"].apply(lambda x: f"¥{x:,.2f}")
                display_pnl["浮动盈亏"] = display_pnl["pnl"].apply(lambda x: f"¥{x:,.2f}")
                display_pnl["收益率"] = display_pnl["pnl_pct"].apply(lambda x: f"{x:+.2f}%")
                pnl_cols = [
                    "股票", "ticker", "buy_date", "买入价", "买入股数", "剩余股数",
                    "现价", "市值", "已实现盈亏", "浮动盈亏", "收益率"
                ]
                pnl_cols = [c for c in pnl_cols if c in display_pnl.columns]
                st.dataframe(display_pnl[pnl_cols], width="stretch", hide_index=True)

            # 盈亏归因
            st.markdown("---")
            st.subheader("盈亏归因")
            attribution = pm.pnl_attribution()
            if not attribution.empty:
                attr_fetcher = StockFetcher()
                attribution["股票"] = attribution["ticker"].apply(
                    lambda x: attr_fetcher.get_stock_name(x)
                )
                display_attr = attribution[["股票", "ticker", "pnl", "pnl_pct", "contribution"]].copy()
                st.dataframe(display_attr, width="stretch", hide_index=True)
            else:
                st.info("暂无盈亏归因数据。")

            # 导出Excel
            st.markdown("---")
            exp_col1, exp_col2 = st.columns([1, 3])
            if exp_col1.button("📥 导出Excel报告"):
                output = pm.export_excel()
                with open(output, "rb") as f:
                    exp_col2.download_button(
                        label="⬇️ 下载报告",
                        data=f,
                        file_name=output.split(os.sep)[-1],
                        mime=(
                            "application/vnd.openxmlformats-"
                            "officedocument.spreadsheetml.sheet"
                        ),
                    )
                st.success(f"报告已生成: {output}")

        except Exception as e:
            st.error(f"计算盈亏失败: {e}")
else:
    st.info("请先添加持仓记录。")
