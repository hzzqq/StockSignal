"""
页面4：仓位管理
持仓记录、盈亏统计、Excel导出
"""

import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="仓位管理", page_icon="💰", layout="wide")
st.title("💰 仓位管理")

from modules.portfolio import PortfolioManager
from modules.visualizer import Visualizer

pm = PortfolioManager()

# ------------------------------------------------------------------
# 添加持仓
# ------------------------------------------------------------------
st.subheader("添加持仓")

with st.form("add_position_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        pos_ticker = st.text_input("股票代码", value="601088", key="pos_ticker")
        pos_name = st.text_input("股票名称", value="中国神华", key="pos_name")
    with col2:
        pos_date = st.date_input("买入日期", value=datetime.now(), key="pos_date")
        pos_price = st.number_input("买入价格", value=20.00, step=0.01, format="%.2f")
    with col3:
        pos_shares = st.number_input("买入股数", value=1000, step=100)
        pos_note = st.text_input("备注", value="", key="pos_note")

    add_submitted = st.form_submit_button("添加持仓")

if add_submitted:
    try:
        pm.add_position(
            ticker=pos_ticker, name=pos_name,
            buy_date=pos_date.strftime("%Y-%m-%d"),
            buy_price=pos_price, shares=pos_shares, note=pos_note
        )
        st.success(f"持仓添加成功: {pos_name}({pos_ticker}) {pos_shares}股 @¥{pos_price}")
    except Exception as e:
        st.error(f"添加失败: {e}")

# ------------------------------------------------------------------
# 当前持仓
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("当前持仓")

positions = pm.get_positions()
if positions.empty:
    st.info("暂无持仓记录，请在上方添加。")
else:
    st.dataframe(positions, use_container_width=True)

    # 删除持仓
    with st.expander("删除持仓"):
        del_index = st.number_input("输入要删除的行号(从0开始)", min_value=0,
                                    max_value=len(positions)-1, value=0, step=1)
        if st.button("删除该持仓"):
            removed = pm.remove_position(int(del_index))
            if removed is not None:
                st.success(f"已删除: {removed.get('name', '')}")
                st.rerun()

# ------------------------------------------------------------------
# 盈亏统计
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("盈亏统计")

if not positions.empty:
    with st.spinner("正在计算盈亏..."):
        try:
            pnl_df = pm.calc_pnl()
            summary = pm.summary()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("总成本", f"¥{summary['total_cost']:,.2f}")
            with col2:
                st.metric("总市值", f"¥{summary['total_market_value']:,.2f}")
            with col3:
                st.metric("总盈亏", f"¥{summary['total_pnl']:,.2f}")
            with col4:
                st.metric("总收益率", f"{summary['total_pnl_pct']:+.2f}%")

            # 盈亏柱状图
            if not pnl_df.empty:
                st.markdown("---")
                fig = Visualizer.portfolio_pnl(pnl_df)
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("#### 持仓明细")
                st.dataframe(pnl_df, use_container_width=True)

            # 盈亏归因
            st.markdown("---")
            st.subheader("盈亏归因")
            attribution = pm.pnl_attribution()
            if not attribution.empty:
                st.dataframe(attribution[["ticker", "name", "pnl", "pnl_pct", "contribution"]],
                             use_container_width=True)

            # 导出Excel
            st.markdown("---")
            if st.button("📥 导出Excel报告"):
                output = pm.export_excel()
                with open(output, "rb") as f:
                    st.download_button(
                        label="下载报告",
                        data=f, file_name=output.split(os.sep)[-1],
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                st.success(f"报告已生成: {output}")

        except Exception as e:
            st.error(f"计算盈亏失败: {e}")
else:
    st.info("请先添加持仓记录。")
