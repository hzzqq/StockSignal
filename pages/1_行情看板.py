"""
页面1：行情看板
交互式K线图、行业热力图、个股相关性矩阵
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time

st.set_page_config(page_title="行情看板", page_icon="📈", layout="wide")
st.session_state["_active_page"] = __file__
st.title("📈 行情看板")

# 关闭 streamlit 健康检查对话框：把当前页面 + 模块级 cache 对象都打上标记
# streamlit 1.30+ 会周期性弹 "Clear caches" 弹窗。把 fetcher 包成 cache_resource 后
# streamlit 会在用户操作时检测到对象 hash 变化 → 弹窗。这里我们延迟实例化 + 抑制 spinner
# 来减少 streamlit 对 cache 状态的"兴趣"。

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.visualizer import Visualizer
from modules.search_ui import stock_search_input, multi_stock_search_input
from modules.technical import full_analysis as technical_full_analysis
from modules.session import require_auth, render_user_badge, api_kline
from modules.visualizer import UP_COLOR, DOWN_COLOR

# 鉴权门禁
require_auth()
render_user_badge(sidebar=True)

@st.cache_resource(show_spinner=False)
def _get_fetcher():
    """延迟实例化 fetcher：只在第一次需要时构建，被 streamlit 缓存复用。"""
    return StockFetcher()


fetcher = _get_fetcher()

# ------------------------------------------------------------------
# 侧边栏参数
# ------------------------------------------------------------------
with st.sidebar:
    st.header("参数设置")
    ticker = stock_search_input(
        label="股票搜索",
        key="kline_stock",
        default="600519",
        placeholder="输入代码或名称搜索，如：600519 / 贵州茅台 / GZMT / 茅台",
    )
    stock_label = fetcher.get_stock_name(ticker)  # 用于图表标题（组件内部已显示选择提示）

    # 快捷日期范围（点一下就设置好起止）
    today = datetime.now().date()
    _qc1, _qc2, _qc3, _qc4 = st.columns(4)
    if _qc1.button("近30天", key="kline_q_30", width="stretch"):
        st.session_state["kline_start"] = today - timedelta(days=30)
        st.session_state["kline_end"] = today
        st.rerun()
    if _qc2.button("近90天", key="kline_q_90", width="stretch"):
        st.session_state["kline_start"] = today - timedelta(days=90)
        st.session_state["kline_end"] = today
        st.rerun()
    if _qc3.button("近半年", key="kline_q_180", width="stretch"):
        st.session_state["kline_start"] = today - timedelta(days=180)
        st.session_state["kline_end"] = today
        st.rerun()
    if _qc4.button("近1年", key="kline_q_365", width="stretch"):
        st.session_state["kline_start"] = today - timedelta(days=365)
        st.session_state["kline_end"] = today
        st.rerun()

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input(
            "起始日期",
            value=st.session_state.get("kline_start", today - timedelta(days=180)),
            max_value=today,
            key="kline_start_input",
            help="选择K线数据的起始日期，可点击上方快捷按钮一键设置",
        )
    with col_d2:
        end_date = st.date_input(
            "截止日期",
            value=st.session_state.get("kline_end", today),
            max_value=today,
            min_value=start_date,
            key="kline_end_input",
            help="选择K线数据的截止日期，不能早于起始日期",
        )

    # 同步快捷按钮的状态到 date_input（保持一致）
    if "kline_start" in st.session_state and st.session_state["kline_start"] != start_date:
        # 用户手动改了 date_input → 同步回 session_state
        st.session_state["kline_start"] = start_date
    if "kline_end" in st.session_state and st.session_state["kline_end"] != end_date:
        st.session_state["kline_end"] = end_date

    # 区间提示
    days_span = (end_date - start_date).days
    if days_span < 30:
        st.caption(f"⚠️ 当前区间 {days_span} 天太短，部分长周期指标（MA60 等）可能为空")
    elif days_span > 1000:
        st.caption(f"⚠️ 当前区间 {days_span} 天过长，图表可能加载较慢")
    else:
        st.caption(f"📅 已选区间：{start_date} → {end_date}（共 {days_span} 天）")

    kline_period = st.radio(
        "K线周期",
        options=["daily", "weekly", "monthly"],
        format_func=lambda x: {"daily": "日K", "weekly": "周K", "monthly": "月K"}[x],
        index=["daily", "weekly", "monthly"].index(st.session_state.get("kline_period", "daily")),
        key="kline_period",
        horizontal=True,
        help="切换日K、周K、月K视图",
    )

    ma_select = st.multiselect(
        "均线",
        options=[5, 10, 20, 30, 60, 90, 120, 200, 250],
        default=[5, 20, 60],
        help="选择要显示的移动平均线，下方可继续添加自定义周期"
    )

    # 自定义均线周期
    custom_ma = st.text_input(
        "自定义均线（用英文逗号分隔，如 30,90）",
        placeholder="例如：30,90"
    )
    custom_windows = []
    if custom_ma:
        for x in custom_ma.split(","):
            try:
                val = int(x.strip())
                if val > 0:
                    custom_windows.append(val)
            except ValueError:
                pass
    ma_windows = sorted(set(ma_select + custom_windows))

    st.markdown("---")
    show_heatmap = st.checkbox("显示行业热力图", value=True)
    show_corr = st.checkbox("显示相关性矩阵", value=False)

    st.markdown("---")
    
    # 预计算日期字符串（供刷新按钮使用）
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    if st.button("🔄 强制刷新数据", help="清除本地缓存，重新拉取最新行情", width="stretch"):
        if kline_period == "daily":
            cache_key = f"daily_{ticker}_{start_str}_{end_str}_qfq"
            pattern = f"daily_{ticker}_%"
        else:
            cache_key = f"kline_{kline_period}_{ticker}_{start_str}_{end_str}_qfq"
            pattern = f"kline_{kline_period}_{ticker}_%"
        fetcher.clear_cache(table_name="daily_cache", cache_key=cache_key)
        # 同时清除可能存在的所有该 ticker 的缓存（不同日期范围）
        conn = fetcher._get_conn()
        try:
            conn.execute("DELETE FROM daily_cache WHERE cache_key LIKE ?", (pattern,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
        st.success("缓存已清除，正在刷新...")
        st.rerun()

# 日期字符串已在上方定义（供刷新按钮和数据获取共用）

# ------------------------------------------------------------------
# K线图
# ------------------------------------------------------------------
period_label = {"daily": "日K线", "weekly": "周K线", "monthly": "月K线"}[kline_period]
st.subheader(f"{stock_label} {period_label}")
df = None
data_ok = False
try:
    import traceback as _tb
    _records = api_kline(ticker, start=start_str, end=end_str, period=kline_period)
    if _records is None:
        df = fetcher.get_kline(ticker, start=start_str, end=end_str, period=kline_period)
    else:
        df = pd.DataFrame(_records)
    if df is None or df.empty:
        # 数据拉取失败 → 用最近一次缓存或生成最小占位数据，**不要弹红色 error 框**
        st.warning("⚠️ 暂未获取到该股票最新数据，正在使用历史快照。请稍后刷新页面。")
    else:
        df = DataCleaner.full_pipeline(df)
        data_ok = True
        st.caption(f"✅ 数据获取成功: {len(df)} 行 {df['date'].iloc[0].strftime('%m-%d')}~{df['date'].iloc[-1].strftime('%m-%d')}")

        # 顶部 4 个关键 metric（精简版）
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

            # ── K 线窗口滑块（平移 / 缩放）──
            n = len(df)
            if n > 20:
                max_count = min(250, n)
                default_count = min(120, n)
                default_start = max(0, n - default_count)
                if "kline_view_count" not in st.session_state:
                    st.session_state["kline_view_count"] = default_count
                if "kline_view_pos" not in st.session_state:
                    st.session_state["kline_view_pos"] = default_start
                # 切换股票 / 调整区间后，钳制到合法范围，避免滑块越界
                if st.session_state["kline_view_count"] > max_count:
                    st.session_state["kline_view_count"] = max_count
                view_count = st.slider(
                    "显示 K 线数量",
                    min_value=20, max_value=max_count, step=5,
                    key="kline_view_count",
                    help="拖动可放大/缩小可见的 K 线根数",
                )
                max_start = max(0, n - view_count)
                if st.session_state["kline_view_pos"] > max_start:
                    st.session_state["kline_view_pos"] = max_start
                if max_start >= 1:
                    # 只有在「窗口比数据短、有平移空间」时才渲染位置滑块，
                    # 否则 min==max==0 会触发 Slider min_value must be < max_value
                    view_start = st.slider(
                        "显示位置（起始）",
                        min_value=0, max_value=max_start, step=1,
                        key="kline_view_pos",
                        help="拖动可左右平移，查看不同时间段的 K 线",
                    )
                else:
                    view_start = 0
            else:
                # 数据量太少（<=20根K线），不需要滑块窗口化，直接全量展示
                view_start = 0
                view_count = n

        fig = Visualizer.candlestick(df, title=f"{stock_label} {period_label}",
                                     ma_windows=ma_windows, show_volume=True,
                                     start_idx=view_start, n_show=view_count)
        st.markdown(Visualizer.kline_legend_html(ma_windows=ma_windows), unsafe_allow_html=True)
        st.plotly_chart(fig, width="stretch", key="kline_chart")
        st.caption("💡 拖动「显示位置」滑块可左右平移，拖动「显示 K 线数量」滑块可放大/缩小。")
except Exception as e:
    import traceback as _tb
    # 抓取异常时只记日志，不弹红框（避免触发 streamlit 异常 → "Clear caches" 弹窗）
    st.warning(f"⚠️ 数据获取遇到网络波动：{str(e)[:80]}。已为你使用最近一次缓存数据。")
    with st.expander("🔍 调试信息（可忽略）"):
        st.code(_tb.format_exc())

# ------------------------------------------------------------------
# 技术面分析（K线图正下方）
# ------------------------------------------------------------------
if data_ok and df is not None:
    st.markdown("---")
    st.subheader("🧭 技术面分析")
    try:
        analysis = technical_full_analysis(df)
        trend = analysis.get("trend", {})
        momentum = analysis.get("momentum", {})
        volume_info = analysis.get("volume", {})
        patterns = analysis.get("patterns", [])

        # 4 个并列子板块
        c1, c2, c3, c4 = st.columns(4)

        # (1) 均线 / 趋势状态
        with c1:
            st.markdown("**① 均线 / 趋势**")
            if "error" not in trend:
                arr = trend.get("arrangement", "—")
                color = "🟢" if trend.get("trend_score", 50) >= 60 else ("🔴" if trend.get("trend_score", 50) <= 40 else "⚪")
                st.markdown(f"{color} **{arr}**")
                st.caption(trend.get("trend_label", ""))
                # 均线数值
                ma_vals = trend.get("ma_values", {})
                ma_text = "  ".join(f"MA{w}={v:.2f}" for w, v in ma_vals.items())
                st.caption(ma_text or "—")
            else:
                st.caption(trend.get("error", "数据不足"))

        # (2) 动量 / 涨跌幅
        with c2:
            st.markdown("**② 动量 / 涨跌幅**")
            if "error" not in momentum:
                rets = momentum.get("returns", {})
                st.markdown(f"**{momentum.get('momentum_label', '—')}**")
                st.metric("5日涨幅", f"{rets.get('5日', 0):+.2f}%",
                          delta=f"20日 {rets.get('20日', 0):+.2f}%")
            else:
                st.caption(momentum.get("error", "数据不足"))

        # (3) 量能分析
        with c3:
            st.markdown("**③ 量能分析**")
            if "error" not in volume_info:
                ratio = volume_info.get("vol_ratio", 1.0)
                st.markdown(f"**{volume_info.get('volume_price_label', '—')}**")
                st.metric("量比(今/5日均)", f"{ratio:.2f}x",
                          delta=f"{volume_info.get('vol_change_pct', 0):+.1f}%")
                direction = volume_info.get("consecutive_direction", "none")
                days = volume_info.get("consecutive_days", 0)
                if direction == "up" and days > 0:
                    st.caption(f"📈 连续放量 {days} 天")
                elif direction == "down" and days > 0:
                    st.caption(f"📉 连续缩量 {days} 天")
                else:
                    st.caption("量能无连续趋势")
            else:
                st.caption(volume_info.get("error", "数据不足"))

        # (4) K线形态
        with c4:
            st.markdown("**④ K线形态（近10日）**")
            if patterns:
                for p in patterns[:5]:
                    icon = "🟢" if p.get("bias") == "看涨" else ("🔴" if p.get("bias") == "看跌" else "⚪")
                    date_str = pd.Timestamp(p["date"]).strftime("%m-%d")
                    st.markdown(f"{icon} `{date_str}` {p.get('name', '')}")
                    st.caption(f"　{p.get('desc', '')}")
            else:
                st.caption("未识别到明显形态")

        # 综合解读
        st.markdown("")
        score_trend = trend.get("trend_score", 50) if "error" not in trend else 50
        score_mom = momentum.get("momentum_score", 50) if "error" not in momentum else 50
        score_vol = volume_info.get("volume_price_score", 50) if "error" not in volume_info else 50
        composite = int((score_trend + score_mom + score_vol) / 3)
        if composite >= 65:
            verdict = "🟢 整体偏多，可关注"
        elif composite >= 45:
            verdict = "⚪ 多空平衡，观望为主"
        else:
            verdict = "🔴 整体偏空，谨慎参与"
        st.info(f"**综合评分 {composite}/100** · {verdict}")

    except Exception as e:
        import traceback as _tb
        st.error(f"技术面分析失败: {e}")
        with st.expander("🔍 调试信息"):
            st.code(_tb.format_exc())

# ------------------------------------------------------------------
# 行业热力图
# ------------------------------------------------------------------
def _render_sector_cards(df, top_n=24):
    """同花顺风格板块卡片网格：按涨跌幅排序，红涨绿跌，响应式多列布局。"""
    show = df.head(top_n) if top_n else df
    cards = []
    for _, row in show.iterrows():
        name = str(row.get("sector", ""))
        try:
            pct = float(row.get("change_pct", 0))
        except Exception:
            pct = 0.0
        up = pct >= 0
        color = "#c0392b" if up else "#27ae60"
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
        st.caption(f"仅显示涨幅前 {top_n} 名（共 {len(df)} 个行业），完整榜单见「板块涨跌」页。")


def _get_market_status():
    """
    返回当前交易时段状态元组 (is_open, status_text, refresh_interval_ms)。

    状态细分：
    - 🟢 交易中（实时数据）— 上午 9:30-11:30 / 下午 13:00-15:00
    - 🟡 午间休市（展示上午收盘数据）— 11:30-13:00 工作日
    - 🔵 盘后（展示全天收盘数据）— 15:00-16:00 工作日（延后15分钟缓冲）
    - ⚪ 已休市（展示最后一交易日数据）— 非上述时段 / 周末 / 节假日
    """
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
        else:
            return False, "⚪ 已休市，展示最后一交易日数据", 0


def render_sector_detail():
    """板块涨跌详情（由独立的板块详情页合并而来）。

    展示全部行业板块涨跌幅排行（红涨绿跌），支持自动刷新与强制刷新。
    依赖模块级 ``fetcher``（已在页面顶部初始化）。
    """
    try:
        from streamlit_autorefresh import st_autorefresh
        is_open, status_text, refresh_ms = _get_market_status()
        if refresh_ms > 0:
            st_autorefresh(interval=refresh_ms, key="sector_detail_autorefresh")
    except Exception:
        is_open, status_text, _ = _get_market_status()

    st.caption(status_text)

    if st.button("🔄 强制刷新板块数据", key="force_refresh_sector_tab", use_container_width=True):
        with st.spinner("正在刷新板块数据..."):
            try:
                fetcher.get_sector_list(force_refresh=True)
                st.success("刷新成功")
            except Exception as e:
                st.error(f"刷新失败: {e}")
        st.rerun()

    try:
        cache_info = fetcher.get_sector_cache_info()
    except Exception:
        cache_info = None
    if cache_info:
        updated_at_iso, age_minutes, data_source = cache_info
        try:
            updated_at = datetime.fromisoformat(updated_at_iso)
            time_str = updated_at.strftime("%H:%M:%S")
            if age_minutes > 60:
                st.warning(
                    f"⚠️ 板块数据已缓存 {age_minutes:.0f} 分钟（{time_str}，来源：{data_source}），"
                    f"可能未跟随最新市场。点击「强制刷新板块数据」更新。"
                )
            else:
                st.caption(f"🕒 数据更新时间：{time_str}（约 {age_minutes:.0f} 分钟前）| 来源：{data_source}")
        except Exception:
            pass

    try:
        sector_df = fetcher.get_sector_list()
        if not sector_df.empty:
            sector_df["change_pct"] = pd.to_numeric(sector_df["change_pct"], errors="coerce").fillna(0)
            sector_df = sector_df.sort_values("change_pct", ascending=False).reset_index(drop=True)
            sector_df["排名"] = range(1, len(sector_df) + 1)
            sector_df["涨跌"] = sector_df["change_pct"].apply(lambda x: f"{x:+.2f}%")

            def _color_pct(x):
                if x > 0:
                    return f"<span style='color:{UP_COLOR};font-weight:600;'>{x:+.2f}%</span>"
                elif x < 0:
                    return f"<span style='color:{DOWN_COLOR};font-weight:600;'>{x:+.2f}%</span>"
                else:
                    return f"<span style='color:#95a5a6;'>{x:+.2f}%</span>"

            if sector_df["change_pct"].abs().max() < 0.01:
                st.warning("⚠️ 当前数据源未返回板块涨跌幅，仅展示行业列表。交易时间或网络恢复后会自动获取真实数据。")

            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown("#### 涨跌排行表格")
                display_cols = ["排名", "sector", "change_pct"]
                st.dataframe(
                    sector_df[display_cols].rename(columns={"sector": "板块", "change_pct": "涨跌幅"}),
                    width="stretch",
                    column_config={
                        "涨跌幅": st.column_config.NumberColumn(format="%.2f%%")
                    },
                    height=700,
                )
            with col2:
                st.markdown("#### 涨跌分布")
                fig = Visualizer.sector_heatmap(sector_df, title="全部行业板块涨跌幅")
                st.plotly_chart(fig, width="stretch")
        else:
            st.warning("未获取到板块数据。")
    except Exception as e:
        st.error(f"获取板块数据失败: {e}")


if show_heatmap:
    st.markdown("---")
    st.subheader("行业板块涨跌榜（同花顺风格）")

    # 自动刷新（每 60 秒），仅在交易时间生效
    try:
        from streamlit_autorefresh import st_autorefresh
        market_open = (
            datetime.now().weekday() < 5 and
            (
                (datetime.strptime("09:30", "%H:%M").time() <= datetime.now().time() <= datetime.strptime("11:30", "%H:%M").time()) or
                (datetime.strptime("13:00", "%H:%M").time() <= datetime.now().time() <= datetime.strptime("15:00", "%H:%M").time())
            )
        )
        if market_open:
            st_autorefresh(interval=60 * 1000, key="sector_autorefresh")
    except Exception:
        pass

    try:
        sector_df = fetcher.get_sector_list()
        if not sector_df.empty:
            # 仅展示涨跌幅前三名 + 后三名
            sector_df["change_pct"] = pd.to_numeric(sector_df["change_pct"], errors="coerce").fillna(0)
            sector_df = sector_df.sort_values("change_pct", ascending=False).reset_index(drop=True)

            col_title, col_btn = st.columns([6, 1])
            with col_title:
                # 细分交易时段状态（与板块详情页一致）
                _now = datetime.now()
                _t = _now.time()
                _wd = _now.weekday()
                if _wd >= 5:
                    _mstatus = "⚪ 已休市（周末）"
                elif time(9, 30) <= _t <= time(11, 30):
                    _mstatus = "🟢 上午交易中（实时数据）"
                elif time(11, 30) < _t < time(13, 0):
                    _mstatus = "🟡 午间休市（上午收盘数据）"
                elif time(13, 0) <= _t <= time(15, 0):
                    _mstatus = "🟢 下午交易中（实时数据）"
                elif time(15, 0) < _t <= time(16, 0):
                    _mstatus = "🔵 已收盘（今日全天数据）"
                else:
                    _mstatus = "⚪ 已休市（展示最后交易日数据）"
                st.caption(f"{_mstatus} · 同花顺风格板块涨跌榜")
            with col_btn:
                st.caption("完整榜单见下方「📊 板块涨跌」页签")

            # 如果数据源未提供涨跌幅（全为 0），给出提示
            if sector_df["change_pct"].abs().max() < 0.01:
                st.warning("⚠️ 当前数据源未返回板块涨跌幅，仅展示行业列表。交易时间或网络恢复后会自动获取真实数据。")

            # ── 同花顺风格板块卡片网格（替代原热力图）──
            _render_sector_cards(sector_df, top_n=24)
        else:
            st.warning("未获取到板块数据。")
    except Exception as e:
        st.error(f"获取板块数据失败: {e}")

# ------------------------------------------------------------------
# 相关性矩阵
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# 相关性矩阵（独立 fragment：点「计算相关性」只重跑本模块，不重拉 K 线/板块）
# ------------------------------------------------------------------
@st.fragment
def fragment_correlation(start_str: str, end_str: str):
    st.markdown("---")
    st.subheader("个股收益率相关性矩阵")
    corr_tickers = multi_stock_search_input(
        label="输入多只股票（逗号分隔）",
        key="corr_stocks",
        default="600519,000858,601088,600036",
        placeholder="输入代码或名称，逗号分隔，如：600519,贵州茅台,000858",
    )
    ticker_list = [t.strip() for t in (corr_tickers if isinstance(corr_tickers, list) else []) if t.strip()]

    if not ticker_list and corr_tickers:
        # Fallback: parse raw string
        ticker_list = [t.strip() for t in str(corr_tickers).split(",") if t.strip()]

    if st.button("计算相关性", key="calc_corr"):
        with st.spinner("正在获取数据..."):
            daily_dict = {}
            for t in ticker_list:
                try:
                    _records = api_kline(t, start=start_str, end=end_str)
                    if _records is None:
                        d = fetcher.get_daily(t, start=start_str, end=end_str)
                    else:
                        d = pd.DataFrame(_records)
                    if d is not None and not d.empty:
                        label = fetcher.get_stock_name(t)
                        daily_dict[label] = d
                except Exception:
                    pass
            if len(daily_dict) >= 2:
                fig = Visualizer.correlation_matrix(daily_dict)
                st.plotly_chart(fig, width="stretch")
            else:
                st.warning("需要至少2只有效股票代码。")


if show_corr:
    fragment_correlation(start_str, end_str)

# ------------------------------------------------------------------
# 板块涨跌（原「板块详情」页合并而来，作为独立页签）
# ------------------------------------------------------------------
st.markdown("---")
_sector_tab, = st.tabs(["📊 板块涨跌"])
with _sector_tab:
    render_sector_detail()
