"""
页面3：策略回测
事件驱动策略 / 均线交叉策略回测
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="策略回测", page_icon="⚙️", layout="wide")
st.title("⚙️ 策略回测")

from modules.backtest import Backtester
from modules.visualizer import Visualizer

bt = Backtester()

# ------------------------------------------------------------------
# 参数设置
# ------------------------------------------------------------------
st.subheader("回测参数")

with st.form("backtest_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        bt_ticker = st.text_input("股票代码", value="601088", key="bt_ticker")
    with col2:
        strategy = st.selectbox("策略", options=["event_driven", "ma_cross"],
                                format_func=lambda x: "事件驱动" if x == "event_driven" else "均线交叉")
    with col3:
        initial_capital = st.number_input("初始资金", value=100000, step=10000)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        bt_start = st.date_input("起始日期", value=datetime.now() - timedelta(days=365))
    with col_d2:
        bt_end = st.date_input("截止日期", value=datetime.now())

    keywords_input = ""
    if strategy == "event_driven":
        keywords_input = st.text_input(
            "事件关键词（逗号分隔）",
            value="煤炭,保供,电厂库存",
            key="bt_keywords"
        )

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        commission = st.slider("手续费率(%)", min_value=0.0, max_value=0.5, value=0.1, step=0.01) / 100
    with col_c2:
        show_benchmark = st.checkbox("显示基准（买入持有）", value=True)

    submitted = st.form_submit_button("开始回测")

if submitted:
    keywords = [k.strip() for k in keywords_input.split(",") if k.strip()] if keywords_input else []

    with st.spinner("正在回测，请稍候..."):
        try:
            result = bt.run(
                ticker=bt_ticker,
                start=bt_start.strftime("%Y-%m-%d"),
                end=bt_end.strftime("%Y-%m-%d"),
                strategy=strategy,
                keywords=keywords,
                initial_capital=initial_capital,
                commission=commission
            )

            # 摘要
            st.markdown("---")
            st.subheader("回测结果")

            s = result.summary()
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("累计收益", f"{s['total_return_pct']:+.2f}%")
            with col2:
                st.metric("最大回撤", f"{s['max_drawdown_pct']:.2f}%")
            with col3:
                st.metric("夏普比率", f"{s['sharpe_ratio']}")
            with col4:
                st.metric("交易次数", f"{s['trade_count']}")

            col5, col6 = st.columns(2)
            with col5:
                st.metric("初始资金", f"¥{s['initial_capital']:,.0f}")
            with col6:
                st.metric("最终资产", f"¥{s['final_value']:,.2f}")

            st.code(result.summary_text(), language="text")

            # 收益曲线
            st.markdown("---")
            st.subheader("收益曲线")

            benchmark = None
            if show_benchmark and not result.df.empty:
                # 买入持有基准
                first_close = result.df.iloc[0]["close"]
                benchmark = (result.df["close"] / first_close - 1) * 100

            fig = Visualizer.backtest_curve(result.df, benchmark=benchmark,
                                            title=f"{bt_ticker} {strategy} 策略收益曲线")
            st.plotly_chart(fig, use_container_width=True)

            # 回撤曲线
            st.markdown("---")
            st.subheader("回撤曲线")
            fig_dd = Visualizer.drawdown_curve(result.df)
            st.plotly_chart(fig_dd, use_container_width=True)

            # 交易明细
            st.markdown("---")
            st.subheader("交易明细")
            trades = result.df[result.df["signal"] != 0][["date", "close", "signal", "position", "total_asset"]]
            trades["操作"] = trades["signal"].map({1: "买入", -1: "卖出", 0: "持有"})
            st.dataframe(trades[["date", "close", "操作", "position", "total_asset"]], use_container_width=True)

        except Exception as e:
            st.error(f"回测失败: {e}")
            st.exception(e)
