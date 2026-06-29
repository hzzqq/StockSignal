"""
页面1：行情看板
交互式K线图、行业热力图、个股相关性矩阵
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="行情看板", page_icon="📈", layout="wide")
st.title("📈 行情看板")

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.visualizer import Visualizer

fetcher = StockFetcher()

# ------------------------------------------------------------------
# 侧边栏参数
# ------------------------------------------------------------------
with st.sidebar:
    st.header("参数设置")
    ticker = st.text_input("股票代码", value="600519", help="如 600519(贵州茅台) / 000858(五粮液)")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("起始日期", value=datetime.now() - timedelta(days=180))
    with col_d2:
        end_date = st.date_input("截止日期", value=datetime.now())

    ma_select = st.multiselect("均线", options=[5, 10, 20, 60, 120], default=[5, 20, 60])

    st.markdown("---")
    show_heatmap = st.checkbox("显示行业热力图", value=True)
    show_corr = st.checkbox("显示相关性矩阵", value=False)

    st.markdown("---")
    if st.button("🔄 强制刷新数据", help="清除本地缓存，重新从 AKShare 拉取最新行情", use_container_width=True):
        fetcher.clear_cache(table_name="daily_cache",
                            cache_key=f"daily_{ticker}_{start_str}_{end_str}_qfq")
        # 同时清除可能存在的所有该 ticker 的缓存（不同日期范围）
        import sqlite3 as _sqlite3
        conn = fetcher._get_conn()
        try:
            conn.execute("DELETE FROM daily_cache WHERE cache_key LIKE ?", (f"daily_{ticker}_%",))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
        st.success("缓存已清除，正在刷新...")
        st.rerun()

start_str = start_date.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")

# ------------------------------------------------------------------
# K线图
# ------------------------------------------------------------------
st.subheader(f"{ticker} K线图")
try:
    df = fetcher.get_daily(ticker, start=start_str, end=end_str)
    df = DataCleaner.full_pipeline(df)

    if df.empty:
        st.warning("未获取到数据，请检查股票代码或日期范围。")
    else:
        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
        latest = df.iloc[-1]
        with col_info1:
            st.metric("最新收盘价", f"¥{latest['close']:.2f}",
                      delta=f"{latest.get('change_pct', 0):.2f}%")
        with col_info2:
            st.metric("区间最高", f"¥{df['high'].max():.2f}")
        with col_info3:
            st.metric("区间最低", f"¥{df['low'].min():.2f}")
        with col_info4:
            total_vol = df['volume'].sum()
            st.metric("区间总成交量", f"{total_vol/1e6:.0f}M")

        fig = Visualizer.candlestick(df, title=f"{ticker} 日K线",
                                     ma_windows=ma_select, show_volume=True)
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"获取数据失败: {e}")

# ------------------------------------------------------------------
# 行业热力图
# ------------------------------------------------------------------
if show_heatmap:
    st.markdown("---")
    st.subheader("行业板块涨跌热力图")
    try:
        sector_df = fetcher.get_sector_list()
        if not sector_df.empty:
            fig = Visualizer.sector_heatmap(sector_df)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("未获取到板块数据。")
    except Exception as e:
        st.error(f"获取板块数据失败: {e}")

# ------------------------------------------------------------------
# 相关性矩阵
# ------------------------------------------------------------------
if show_corr:
    st.markdown("---")
    st.subheader("个股收益率相关性矩阵")
    corr_tickers = st.text_input(
        "输入多只股票代码（逗号分隔）",
        value="600519,000858,601088,600036",
        key="corr_tickers"
    )
    ticker_list = [t.strip() for t in corr_tickers.split(",") if t.strip()]

    if st.button("计算相关性", key="calc_corr"):
        with st.spinner("正在获取数据..."):
            daily_dict = {}
            for t in ticker_list:
                try:
                    d = fetcher.get_daily(t, start=start_str, end=end_str)
                    if not d.empty:
                        daily_dict[t] = d
                except Exception:
                    pass
            if len(daily_dict) >= 2:
                fig = Visualizer.correlation_matrix(daily_dict)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("需要至少2只有效股票代码。")
