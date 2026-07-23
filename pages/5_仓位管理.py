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
from modules.page_widgets import _empty_info, _toast


# 加法式健壮性：统一安全数值格式化——None/NaN/非数值显示"—"而非"nan"，
# 行情或盈亏缺失时避免表格出现 nan 污染。保持原 `¥` + 千分位显示风格不变。
def _fmt_money(x, prefix="¥", nd=2):
    try:
        v = float(x)
    except Exception:
        return f"{prefix}—"
    if v != v:  # NaN
        return f"{prefix}—"
    return f"{prefix}{v:,.{nd}f}"


def _fmt_signed_pct(x, nd=2):
    try:
        v = float(x)
    except Exception:
        return "—"
    if v != v:
        return "—"
    return f"{v:+.{nd}f}%"


def _fmt_int(x):
    try:
        v = float(x)
    except Exception:
        return "—"
    if v != v:
        return "—"
    return f"{int(v):,}"

# 鉴权门禁
require_auth()
render_user_badge(sidebar=True)

pm = PortfolioManager()
fetcher = StockFetcher()

# 初始化 session_state 默认值
if "default_shares" not in st.session_state:
    st.session_state.default_shares = 1000


def format_quote_table(quote):
    """把实时行情格式化成买卖盘 DataFrame。

    加法式健壮性：行情接口（api_quote / get_realtime_quote）返回结构不稳定，
    可能缺 bid/ask 或档位不足 5 档、字段非数值。原实现直接下标访问会抛 KeyError/TypeError，
    导致整个买入/卖出表单崩溃。这里对缺失键、档位不足、字段类型异常做降级。
    """
    if not quote:
        return None
    bid = quote.get("bid") or []
    ask = quote.get("ask") or []
    if not bid or not ask:
        return None
    rows = []
    for i in range(min(5, len(bid), len(ask))):
        try:
            b = bid[i]
            a = ask[i]
            rows.append({
                "买盘": f"买{i+1}",
                "买价": f"¥{float(b['price']):.2f}",
                "买量": f"{int(b['volume']):,}",
                "卖盘": f"卖{i+1}",
                "卖价": f"¥{float(a['price']):.2f}",
                "卖量": f"{int(a['volume']):,}",
            })
        except (KeyError, TypeError, ValueError):
            continue
    return pd.DataFrame(rows) if rows else None


# ------------------------------------------------------------------
# 顶部：当前持仓概览
# ------------------------------------------------------------------
st.subheader("当前持仓概览")
positions = pm.get_positions()
if positions.empty:
    _empty_info("暂无持仓记录。在上方「添加持仓」表单录入代码、价格与股数后，即可开始跟踪。")
else:
    display_pos = positions.copy()
    if "name" in display_pos.columns:
        display_pos = display_pos.drop(columns=["name"])
    display_pos["股票"] = display_pos["ticker"].apply(lambda x: fetcher.get_name_only(x) or fetcher.get_stock_name(x))
    # 格式化显示
    if "shares" in display_pos.columns:
        display_pos["买入股数"] = display_pos["shares"].apply(_fmt_int)
    if "remaining_shares" in display_pos.columns:
        display_pos["剩余股数"] = display_pos["remaining_shares"].apply(_fmt_int)
    if "buy_price" in display_pos.columns:
        display_pos["买入价"] = display_pos["buy_price"].apply(_fmt_money)
    if "cost" in display_pos.columns:
        display_pos["成本"] = display_pos["cost"].apply(_fmt_money)
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
                try:
                    _cur = buy_quote.get("current")
                    _dt = buy_quote.get("datetime", "")
                    if _cur is not None:
                        st.caption(f"📈 最新价 ¥{float(_cur):.2f}  {_dt}")
                    _qdf = format_quote_table(buy_quote)
                    if _qdf is not None:
                        st.dataframe(_qdf, width="stretch", hide_index=True)
                    else:
                        st.caption("⚠️ 五档行情暂不可用")
                except Exception:
                    st.caption("⚠️ 行情数据解析失败，已跳过五档展示")
            else:
                st.caption("⚠️ 未能获取实时行情")
    with col2:
        buy_date = st.date_input("买入日期", value=datetime.now(), key="buy_date",
                                 help="该笔持仓的买入日期，用于计算持有天数与收益率。")
        # 默认成交价：卖一价（买入按卖方最低价成交）
        default_buy_price = 20.00
        _buy_price_from_quote = False
        if buy_quote and buy_quote.get("ask"):
            # 加法式健壮性：行情 schema 漂移时 ask[0] 可能缺 "price" 或元素非 dict，
            # 直接下标访问会抛 KeyError/TypeError，导致买入表单整段崩溃。先安全提取，
            # 失败则回退到下方日线收盘价兜底，保证表单始终可渲染。
            try:
                _a0 = buy_quote["ask"][0]
                if _a0 and "price" in _a0:
                    default_buy_price = float(_a0["price"])
                    _buy_price_from_quote = True
            except (KeyError, TypeError, ValueError, IndexError):
                _buy_price_from_quote = False
        if not _buy_price_from_quote:
            try:
                _kline_start = (datetime.now() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
                _kline_end = datetime.now().strftime("%Y-%m-%d")
                _records = api_kline(buy_ticker, start=_kline_start, end=_kline_end)
                price_df = pd.DataFrame(_records) if _records is not None else fetcher.get_daily(
                    buy_ticker, start=_kline_start, end=_kline_end
                )
                if price_df is not None and not price_df.empty:
                    # 加法式健壮性：日线记录可能缺 "close" 列（schema 漂移）→ 用 .get 降级。
                    _close = price_df.iloc[-1].get("close") if hasattr(price_df, "iloc") else None
                    if _close is not None:
                        default_buy_price = float(_close)
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
        buy_note = st.text_input("备注", value="", key="buy_note",
                                 help="为该笔持仓添加备注（如建仓理由、止盈目标），便于后续回顾。")

    buy_submitted = st.form_submit_button("✅ 添加持仓")

if buy_submitted:
    try:
        pm.add_position(
            ticker=buy_ticker,
            buy_date=buy_date.strftime("%Y-%m-%d"),
            buy_price=buy_price, shares=int(buy_shares), note=buy_note
        )
        _toast(
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
                try:
                    _cur = sell_quote.get("current")
                    _dt = sell_quote.get("datetime", "")
                    if _cur is not None:
                        st.caption(f"📈 最新价 ¥{float(_cur):.2f}  {_dt}")
                    _qdf = format_quote_table(sell_quote)
                    if _qdf is not None:
                        st.dataframe(_qdf, width="stretch", hide_index=True)
                    else:
                        st.caption("⚠️ 五档行情暂不可用")
                except Exception:
                    st.caption("⚠️ 行情数据解析失败，已跳过五档展示")
            else:
                st.caption("⚠️ 未能获取实时行情")
        with col2:
            sell_date = st.date_input("卖出日期", value=datetime.now(), key="sell_date")
            # 默认成交价：买一价（卖出按买方最高价成交）
            default_sell_price = 20.00
            _sell_price_from_quote = False
            if sell_quote and sell_quote.get("bid"):
                # 加法式健壮性：与买入同款防御，bid[0] 缺 "price" 时安全降级到日线兜底。
                try:
                    _b0 = sell_quote["bid"][0]
                    if _b0 and "price" in _b0:
                        default_sell_price = float(_b0["price"])
                        _sell_price_from_quote = True
                except (KeyError, TypeError, ValueError, IndexError):
                    _sell_price_from_quote = False
            if not _sell_price_from_quote:
                try:
                    _kline_start = (datetime.now() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
                    _kline_end = datetime.now().strftime("%Y-%m-%d")
                    _records = api_kline(sell_ticker, start=_kline_start, end=_kline_end)
                    price_df = pd.DataFrame(_records) if _records is not None else fetcher.get_daily(
                        sell_ticker, start=_kline_start, end=_kline_end
                    )
                    if price_df is not None and not price_df.empty:
                        _close = price_df.iloc[-1].get("close") if hasattr(price_df, "iloc") else None
                        if _close is not None:
                            default_sell_price = float(_close)
                except Exception:
                    default_sell_price = 20.00
        # ⚠️ 修复：sell_price 原缩进在 else 分支内，当实时行情存在买一价时走 if 分支，
        # sell_price 永不定义，点「记录卖出」抛 NameError 崩溃。移到 if/else 之外始终渲染。
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
        _empty_info("暂无持仓可删除。当前没有已记录的持仓，无需清理。")
    else:
        del_index = st.number_input(
            "选择要删除的行号（从 0 开始）",
            min_value=0, max_value=len(positions) - 1,
            value=0, step=1,
            help="行号对应上方持仓列表的序号（从 0 开始）。删除不可恢复，请确认后再点「确认删除」。",
        )
        # 行号 → 股票 映射提示，降低误删风险
        _idx_map = "；".join(
            f"{i}: {positions.iloc[i]['ticker']}" for i in range(len(positions))
        )
        st.caption(f"行号对照（从 0 起）：{_idx_map}")
        c_del, _ = st.columns([1, 4])
        _ck = "pm_del_cfm"
        if st.session_state.get(_ck):
            if c_del.button("⚠️ 确认删除", type="primary"):
                removed = pm.remove_position(int(del_index))
                st.session_state.pop(_ck, None)
                if removed is not None:
                    _toast(f"已删除: {removed.get('ticker', '')}")
                    st.rerun()
            if st.button("取消", key="pm_del_cancel"):
                st.session_state.pop(_ck, None)
        else:
            if c_del.button("🗑️ 删除持仓", type="secondary"):
                st.session_state[_ck] = True

st.markdown("---")

# ------------------------------------------------------------------
# 卖出记录
# ------------------------------------------------------------------
st.subheader("卖出记录")
trades = pm.get_trades()
if trades.empty:
    _empty_info("暂无卖出记录。")
else:
    display_trades = trades.copy()
    if "name" in display_trades.columns:
        display_trades = display_trades.drop(columns=["name"])
    display_trades["股票"] = display_trades["ticker"].apply(lambda x: fetcher.get_name_only(x) or fetcher.get_stock_name(x))
    display_trades["卖出日期"] = display_trades["sell_date"]
    display_trades["卖出价"] = display_trades["sell_price"].apply(_fmt_money)
    display_trades["卖出股数"] = display_trades["sell_shares"].apply(_fmt_int)
    display_trades["成交金额"] = display_trades["proceeds"].apply(_fmt_money)
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
                # 加法式健壮性：summary 字典字段用 .get 兜底，避免上游缺键抛 KeyError。
                st.metric("总成本", f"¥{summary.get('total_cost', 0):,.2f}")
            with col2:
                st.metric("总市值", f"¥{summary.get('total_market_value', 0):,.2f}")
            with col3:
                delta_pnl = summary.get("delta_pnl", 0)
                st.metric(
                    "总盈亏", f"¥{summary.get('total_pnl', 0):,.2f}",
                    delta=f"{summary.get('delta_pnl', 0):+.2f}" if abs(delta_pnl or 0) > 0.01 else None
                )
            with col4:
                st.metric("总收益率", f"{summary.get('total_pnl_pct', 0):+.2f}%")

            # 盈亏柱状图
            if not pnl_df.empty:
                st.markdown("---")
                fig = Visualizer.portfolio_pnl(pnl_df)
                st.plotly_chart(fig, width="stretch")

                st.markdown("#### 持仓明细")
                display_pnl = pnl_df.copy()
                if "name" in display_pnl.columns:
                    display_pnl = display_pnl.drop(columns=["name"])
                display_pnl["股票"] = display_pnl["ticker"].apply(lambda x: fetcher.get_name_only(x) or fetcher.get_stock_name(x))
                display_pnl["买入股数"] = display_pnl["shares"].apply(_fmt_int)
                display_pnl["剩余股数"] = display_pnl["remaining_shares"].apply(_fmt_int)
                display_pnl["买入价"] = display_pnl["buy_price"].apply(_fmt_money)
                display_pnl["现价"] = display_pnl["current_price"].apply(_fmt_money)
                display_pnl["市值"] = display_pnl["market_value"].apply(_fmt_money)
                display_pnl["已实现盈亏"] = display_pnl["realized_pnl"].apply(_fmt_money)
                display_pnl["浮动盈亏"] = display_pnl["pnl"].apply(_fmt_money)
                display_pnl["收益率"] = display_pnl["pnl_pct"].apply(_fmt_signed_pct)
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
                    lambda x: fetcher.get_name_only(x) or attr_fetcher.get_stock_name(x)
                )
                display_attr = attribution[["股票", "ticker", "pnl", "pnl_pct", "contribution"]].copy()
                st.dataframe(display_attr, width="stretch", hide_index=True)
            else:
                _empty_info("暂无盈亏归因数据。需要先有至少一笔卖出记录，系统才能按股票拆分盈亏贡献。")

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
