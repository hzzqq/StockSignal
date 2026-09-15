"""pages/85_龙虎榜.py — 席位级资金博弈（补空白）。

龙虎榜是 A 股最经典的席位级信号源：谁在上榜、净买还是净卖、机构还是游资席位。
StockSignal 此前只有板块/个股层面的资金流向，没有这一层。

红线：取不到就明说「取不到」，**不臆造明细**；净买额列匹配不到时
整个摘要返回 None（用错列编出资金方向，比缺失更危险）。
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from modules.page_utils import render_standard_page
from modules import lhb


def _fmt_yi(v) -> str:
    try:
        return f"{float(v) / 1e8:,.2f} 亿"
    except Exception:  # noqa: BLE001
        return "—"


@st.cache_data(ttl=1800, show_spinner="正在拉取龙虎榜…")
def _load(date: str):
    df = lhb.fetch_lhb(date)
    return df, (lhb.summarize(df) if df is not None else None)


def _show_table(df: pd.DataFrame, title: str) -> None:
    st.markdown(f"**{title}**")
    show = df.copy()
    if "净买额" in show.columns:
        show["净买额(亿元)"] = show["净买额"].map(
            lambda v: round(float(v) / 1e8, 2) if pd.notna(v) else None)
        show = show.drop(columns=["净买额"])
    st.dataframe(show, width="stretch", hide_index=True)


def main() -> None:
    render_standard_page(title="龙虎榜", icon="🐯", layout="wide")
    st.caption("数据源：akshare（东方财富龙虎榜）。取不到就显示「取不到」，不臆造明细。")

    default_date = datetime.now().strftime("%Y%m%d")
    date = st.text_input("交易日期（YYYYMMDD）", value=default_date)

    if st.button("查询", type="primary"):
        st.cache_data.clear()

    df, summary = _load(date)

    if df is None:
        st.warning(
            f"{date} 未取到龙虎榜数据。可能原因：非交易日、akshare 不可用或网络受限。"
            "这里**不会**用示例数据填充。"
        )
        return

    if summary is None:
        st.warning(
            "取到了明细，但未能识别出「净买额」列（akshare 列名可能变更）。"
            "为避免用错列编出资金方向，这里不显示排名。"
        )
        with st.expander("查看原始明细（前 50 行）"):
            st.dataframe(df.head(50), width="stretch")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("上榜家数", summary["count"])
    c2.metric("净买额合计", _fmt_yi(summary["net_sum"]))
    c3.metric("识别到的净买列", summary["net_col"])

    st.divider()
    left, right = st.columns(2)
    with left:
        _show_table(summary["buy_top"], "🔥 净买入 Top")
    with right:
        _show_table(summary["sell_top"], "🧊 净卖出 Top")

    with st.expander("查看原始明细"):
        st.dataframe(df, width="stretch")


main()
