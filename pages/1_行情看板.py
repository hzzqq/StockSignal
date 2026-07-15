"""
页面1：行情看板
指数迷你卡、行业板块涨跌榜（含涨跌排行/分布折叠区）、龙虎榜、个股相关性矩阵。
K 线、参数设置、技术面分析已迁移至「股票选取」模块。
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time

from modules.ui_theme import apply_page_config
from modules.fetcher import StockFetcher
from modules.visualizer import Visualizer
from modules.search_ui import multi_stock_search_input
from modules.session import require_auth, render_user_badge, api_kline
from modules.visualizer import UP_COLOR, DOWN_COLOR
from modules.widgets import render_index_mini_cards

apply_page_config(page_title="行情看板", page_icon="📈", layout="wide")
st.session_state["_active_page"] = __file__

require_auth()
render_user_badge(sidebar=True)

st.title("📈 行情看板")

# 顶部三大指数迷你卡片
render_index_mini_cards(cols_per_row=3)


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


# ------------------------------------------------------------------
# 板块卡片网格
# ------------------------------------------------------------------
def _render_sector_cards(df, top_n=24):
    show = df.head(top_n) if top_n else df
    cards = []
    for _, row in show.iterrows():
        name = str(row.get("sector", ""))
        try:
            pct = float(row.get("change_pct", 0))
        except Exception:
            pct = 0.0
        up = pct >= 0
        color = UP_COLOR if up else DOWN_COLOR
        bg = "#fde8e6" if up else "#e8f9ef"
        arrow = "▲" if up else "▼"
        cards.append(
            f'<div style="background:{bg};border-left:3px solid {color};'
            f'border-radius:8px;padding:10px 12px;min-height:64px;'
            f'box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.05);">'
            f'<div style="color:#1f2937;font-size:12px;font-weight:700;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</div>'
            f'<div style="color:{color};font-size:18px;font-weight:700;margin-top:2px;">'
            f'{arrow} {pct:+.2f}%</div></div>'
        )
    grid = "".join(cards)
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));'
        f'gap:8px;">{grid}</div>',
        unsafe_allow_html=True,
    )
    if top_n and len(df) > top_n:
        st.caption(f"仅显示涨幅前 {top_n} 名（共 {len(df)} 个行业）。")


def _get_market_status():
    now = datetime.now()
    t = now.time()
    weekday = now.weekday()
    if weekday >= 5:
        return False, "⚪ 已休市（周末），展示最后一交易日数据", 0
    am_start, am_end = time(9, 30), time(11, 30)
    pm_start, pm_end = time(13, 0), time(15, 0)
    after_close = time(16, 0)
    if am_start <= t <= am_end:
        return True, "🟢 上午交易中（实时数据）", 60 * 1000
    elif am_end < t < pm_start:
        return False, "🟡 午间休市，展示上午收盘数据", 60 * 1000
    elif pm_start <= t <= pm_end:
        return True, "🟢 下午交易中（实时数据）", 60 * 1000
    elif pm_end < t <= after_close:
        return False, "🔵 已收盘，展示今日全天数据", 0
    else:
        if t < am_start:
            return False, "⚪ 尚未开盘，展示上一交易日数据", 0
        return False, "⚪ 已休市，展示最后一交易日数据", 0


# ------------------------------------------------------------------
# 行业板块涨跌榜（卡片 + 折叠详情）
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("🏭 行业板块涨跌榜")

try:
    from streamlit_autorefresh import st_autorefresh
    is_open, status_text, refresh_ms = _get_market_status()
    if refresh_ms > 0:
        st_autorefresh(interval=refresh_ms, key="sector_autorefresh")
except Exception:
    is_open, status_text, _ = _get_market_status()

st.caption(status_text)

try:
    sector_df = fetcher.get_sector_list()
    if not sector_df.empty:
        sector_df["change_pct"] = pd.to_numeric(sector_df["change_pct"], errors="coerce").fillna(0)
        sector_df = sector_df.sort_values("change_pct", ascending=False).reset_index(drop=True)
        if sector_df["change_pct"].abs().max() < 0.01:
            st.warning("⚠️ 当前数据源未返回板块涨跌幅，仅展示行业列表。交易时间或网络恢复后会自动获取真实数据。")
        _render_sector_cards(sector_df, top_n=24)
    else:
        st.warning("未获取到板块数据。")
except Exception as e:
    st.error(f"获取板块数据失败: {e}")

# 折叠区：涨跌排行表格 + 涨跌分布
with st.expander("📊 板块涨跌详情（点击展开）", expanded=False):
    try:
        sector_df = fetcher.get_sector_list()
        if not sector_df.empty:
            sector_df["change_pct"] = pd.to_numeric(sector_df["change_pct"], errors="coerce").fillna(0)
            sector_df = sector_df.sort_values("change_pct", ascending=False).reset_index(drop=True)
            sector_df["排名"] = range(1, len(sector_df) + 1)

            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown("#### 涨跌排行表格")
                display_cols = ["排名", "sector", "change_pct"]
                st.dataframe(
                    sector_df[display_cols].rename(columns={"sector": "板块", "change_pct": "涨跌幅"}),
                    use_container_width=True,
                    column_config={"涨跌幅": st.column_config.NumberColumn(format="%.2f%%")},
                    height=700,
                )
            with col2:
                st.markdown("#### 涨跌分布")
                fig = Visualizer.sector_heatmap(sector_df, title="全部行业板块涨跌幅")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("未获取到板块数据。")
    except Exception as e:
        st.error(f"获取板块详情失败: {e}")


# ------------------------------------------------------------------
# 龙虎榜
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("🐉 龙虎榜")
st.caption("当日机构/游资活跃个股（数据来源：东方财富龙虎榜）")


@st.cache_data(ttl=300, show_spinner=False)
def _load_lhb(date_str: str):
    try:
        import requests
        import urllib3
        urllib3.disable_warnings()
        _orig_get = requests.get
        def _get(url, **kwargs):
            kwargs.setdefault("verify", False)
            return _orig_get(url, **kwargs)
        requests.get = _get

        import akshare as ak
        df = ak.stock_lhb_detail_daily_sina(date=date_str)
        if df is None or df.empty:
            return None
        df = df.rename(columns=lambda x: str(x).strip())
        return df
    except Exception:
        return None


lhb_date = (datetime.now().date() - timedelta(days=0 if datetime.now().weekday() < 5 else 1)).strftime("%Y%m%d")
lhb_df = _load_lhb(lhb_date)

if lhb_df is not None and not lhb_df.empty:
    # 统一列名：尽量兼容不同 akshare 版本
    name_col = next((c for c in lhb_df.columns if "名称" in c), None) or lhb_df.columns[1]
    code_col = next((c for c in lhb_df.columns if "代码" in c), None) or lhb_df.columns[0]
    reason_col = next((c for c in lhb_df.columns if "原因" in c or "上榜" in c), None)
    buy_col = next((c for c in lhb_df.columns if "买入" in c and "额" in c), None)
    sell_col = next((c for c in lhb_df.columns if "卖出" in c and "额" in c), None)

    lhb_df["股票代码"] = lhb_df[code_col].astype(str).str.replace(r"[^0-9]", "", regex=True).str[-6:]
    lhb_df["股票名称"] = lhb_df[name_col].astype(str)
    display_cols = ["股票代码", "股票名称"]
    if reason_col:
        display_cols.append(reason_col)
    if buy_col:
        display_cols.append(buy_col)
    if sell_col:
        display_cols.append(sell_col)

    st.dataframe(lhb_df[display_cols], use_container_width=True, height=420)

    # 点击跳转股票选取
    opts = [f"{row['股票代码']} {row['股票名称']}" for _, row in lhb_df.iterrows() if len(str(row['股票代码'])) == 6]
    sel = st.selectbox("选择龙虎榜股票查看 K 线", ["— 请选择 —"] + opts, key="lhb_jump")
    if sel and sel != "— 请选择 —":
        code = sel.split()[0]
        st.query_params["pick_stock"] = code
        safe_switch_page("pages/1_股票选取.py")
else:
    st.info("暂无龙虎榜数据（非交易日晚间或数据源暂不可用）。")


# ------------------------------------------------------------------
# 相关性矩阵
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("个股收益率相关性矩阵")


def _today_str():
    return datetime.now().date().strftime("%Y-%m-%d")


_corr_tickers = multi_stock_search_input(
    label="输入多只股票（逗号分隔）",
    key="corr_stocks",
    default="600519,000858,601088,600036",
    placeholder="输入代码或名称，逗号分隔",
)
_ticker_list = [t.strip() for t in (_corr_tickers if isinstance(_corr_tickers, list) else []) if t.strip()]
if not _ticker_list and _corr_tickers:
    _ticker_list = [t.strip() for t in str(_corr_tickers).split(",") if t.strip()]

if st.button("计算相关性", key="calc_corr"):
    with st.spinner("正在获取数据..."):
        _end = _today_str()
        _start = (datetime.now().date() - timedelta(days=180)).strftime("%Y-%m-%d")
        daily_dict = {}
        for t in _ticker_list:
            try:
                _records = api_kline(t, start=_start, end=_end)
                if _records is None:
                    d = fetcher.get_daily(t, start=_start, end=_end)
                else:
                    d = pd.DataFrame(_records)
                if d is not None and not d.empty:
                    label = fetcher.get_stock_name(t)
                    daily_dict[label] = d
            except Exception:
                pass
        if len(daily_dict) >= 2:
            fig = Visualizer.correlation_matrix(daily_dict)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("需要至少2只有效股票代码。")
