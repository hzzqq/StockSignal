"""
股票选取模块
------------
位于「行情看板」与「个股分析」之间。
- 从行情看板迁入：参数设置、K 线图、技术面分析。
- 新增：加入自选股 / 加入垃圾股、用户打分、自选股/垃圾股折叠展示（可排序、可跳转）。
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, _theme_is_dark
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.visualizer import Visualizer
from modules.search_ui import stock_search_input
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.linear_trends import plot_normalized_multi
from modules.session import (
    require_auth, render_user_badge, api_kline,
    api_post, api_add_junk_stock, api_user_score, api_save_user_score,
    get_user, trading_autorefresh,
)

from modules.page_guard import safe_fragment
from modules.page_widgets import UP

apply_page_config(page_title="股票选取", page_icon="🎯", layout="wide")
st.session_state["_active_page"] = __file__

# 支持从龙虎榜/股票池点击跳转：URL ?pick_stock=600519
_qp_code = st.query_params.get("pick_stock")
if _qp_code:
    st.session_state["pick_stock_confirmed"] = str(_qp_code)
    st.session_state["pick_stock_query"] = str(_qp_code)
    try:
        del st.query_params["pick_stock"]
    except Exception:
        pass

require_auth()
trading_autorefresh(key="pick_autorefresh")
render_user_badge(sidebar=True)


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()
user = get_user() or {}


def _fmt_md(d) -> str:
    try:
        return pd.Timestamp(d).strftime("%m-%d")
    except Exception:
        s = str(d)
        if len(s) >= 10:
            return s[:10][5:]
        return s


def _norm_code(c: str) -> str:
    if not c:
        return ""
    c = str(c).strip().lower()
    for p in ("sh", "sz", "bj"):
        if c.startswith(p):
            c = c[len(p):]
    return c[-6:] if len(c) > 6 else c


# ── 用户打分组件（Batch8 #271：独立 fragment，交互只重跑本块，提升响应速度）──
@safe_fragment
def _render_user_score(ticker: str, stock_label: str) -> None:
    st.markdown("---")
    st.subheader("⭐ 用户打分")
    # 已有分数缓存到 session_state，避免每次交互都回源后端
    _ss_key = f"_score_{ticker}"
    if _ss_key not in st.session_state:
        st.session_state[_ss_key] = api_user_score(ticker)
    existing_score = st.session_state[_ss_key]

    st.caption("评分范围 **0–100**，越高代表越看好。拖动滑块直接选择，无法输入越界值。")

    # 用 slider 做输入：用户只能选 0–100 之间的整数，彻底解决越界输入问题
    with st.form(key=f"score_form_{ticker}"):
        sc1, sc2 = st.columns([0.55, 0.45])
        with sc1:
            score_val = st.slider(
                "您对该股票的评分（0–100）",
                min_value=0, max_value=100,
                value=existing_score if existing_score is not None else 50,
                step=1,
                key=f"pick_user_score_{ticker}",
                help="拖动选择 0–100 之间的整数。",
            )
        with sc2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("💾 保存评分", use_container_width=True)

        if submitted:
            # slider 返回值已强制在 [0, 100] 内
            score_val = int(score_val)
            res = api_save_user_score(ticker, score_val, stock_label)
            # ⚠️ 兜底：后端异常时 api_save_user_score 可能返回 None，res.get 会抛 AttributeError
            if isinstance(res, dict) and res.get("status") == "ok":
                st.session_state[_ss_key] = score_val
                # 清除旧 slider key，确保下次渲染从已保存值重新初始化（避免残留 50）
                st.session_state.pop(f"pick_user_score_{ticker}", None)
                st.success(f"✅ 评分已保存：{score_val} 分")
            else:
                _msg = res.get("message", "未知错误") if isinstance(res, dict) else "未知错误"
                st.error(f"保存失败：{_msg}")


# ═══════════════════════════════════════════════════════════════
# 参数设置（原行情看板迁入；嵌入合并页时自动改写入主区域，避免覆盖导航）
# ═══════════════════════════════════════════════════════════════
from modules.widgets import sidebar_target
with sidebar_target():
    st.header("参数设置")
    ticker = stock_search_input(
        label="股票搜索",
        key="pick_stock",
        default="600519",
        placeholder="输入代码或名称搜索，如：600519 / 贵州茅台 / GZMT / 茅台",
    )
    _nm = fetcher.get_name_only(ticker)
    if not _nm:
        try:
            _nm = fetcher.get_stock_name(ticker)
        except Exception:
            _nm = None
    stock_label = f"{ticker} {_nm}" if _nm else ticker

    today = datetime.now().date()
    _qc1, _qc2, _qc3, _qc4 = st.columns(4)
    if _qc1.button("近30天", key="pick_q_30", use_container_width=True):
        st.session_state["pick_start"] = today - timedelta(days=30)
        st.session_state["pick_end"] = today
        st.rerun()
    if _qc2.button("近90天", key="pick_q_90", use_container_width=True):
        st.session_state["pick_start"] = today - timedelta(days=90)
        st.session_state["pick_end"] = today
        st.rerun()
    if _qc3.button("近半年", key="pick_q_180", use_container_width=True):
        st.session_state["pick_start"] = today - timedelta(days=180)
        st.session_state["pick_end"] = today
        st.rerun()
    if _qc4.button("近1年", key="pick_q_365", use_container_width=True):
        st.session_state["pick_start"] = today - timedelta(days=365)
        st.session_state["pick_end"] = today
        st.rerun()

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input(
            "起始日期",
            value=st.session_state.get("pick_start", today - timedelta(days=180)),
            max_value=today,
            key="pick_start_input",
            help="K 线回测的起始日期，最长可回溯约 1 年；区间越短，长周期指标可能为空。",
        )
    with col_d2:
        end_date = st.date_input(
            "截止日期",
            value=st.session_state.get("pick_end", today),
            max_value=today,
            min_value=start_date,
            key="pick_end_input",
            help="K 线回测的结束日期，默认今天；与起始日期共同决定分析区间。",
        )
    if "pick_start" in st.session_state and st.session_state["pick_start"] != start_date:
        st.session_state["pick_start"] = start_date
    if "pick_end" in st.session_state and st.session_state["pick_end"] != end_date:
        st.session_state["pick_end"] = end_date

    days_span = (end_date - start_date).days
    if days_span < 30:
        st.caption(f"⚠️ 当前区间 {days_span} 天太短，部分长周期指标可能为空")
    elif days_span > 1000:
        st.caption(f"⚠️ 当前区间 {days_span} 天过长，图表可能加载较慢")
    else:
        st.caption(f"📅 已选区间：{start_date} → {end_date}（共 {days_span} 天）")

    kline_period = st.radio(
        "K线周期",
        options=["daily", "weekly", "monthly"],
        format_func=lambda x: {"daily": "日K", "weekly": "周K", "monthly": "月K"}[x],
        index=["daily", "weekly", "monthly"].index(st.session_state.get("pick_period", "daily")),
        key="pick_period",
        horizontal=True,
        help="日K 适合短线研判，周K/月K 更适合观察中长期趋势。",
    )

    ma_select = st.multiselect(
        "均线",
        options=[5, 10, 20, 30, 60, 90, 120, 200, 250],
        default=[5, 20, 60],
        key="pick_ma_select",
        help="勾选需要在 K 线图上叠加显示的移动平均线周期（如 5/20/60 日）。",
    )
    custom_ma = st.text_input("自定义均线（用英文逗号分隔，如 30,90）", placeholder="例如：30,90", key="pick_custom_ma",
                             help="输入自定义均线周期，逗号分隔，例如 13,34,55；与上方勾选合并生效。")
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
    if st.button("🔄 强制刷新数据", help="清除本地缓存，重新拉取最新行情", use_container_width=True):
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        if kline_period == "daily":
            cache_key = f"daily_{ticker}_{start_str}_{end_str}_qfq"
            pattern = f"daily_{ticker}_%"
        else:
            cache_key = f"kline_{kline_period}_{ticker}_{start_str}_{end_str}_qfq"
            pattern = f"kline_{kline_period}_{ticker}_%"
        fetcher.clear_cache(table_name="daily_cache", cache_key=cache_key)
        conn = fetcher._get_conn()
        try:
            conn.execute("DELETE FROM daily_cache WHERE cache_key LIKE ?", (pattern,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
        st.success("缓存已清除，正在刷新...")
        # 击穿 @st.cache_data 内的 _cached_kline（参数变化强制重算并重新取数）
        st.session_state["_pick_kline_nonce"] = int(st.session_state.get("_pick_kline_nonce", 0)) + 1
        st.rerun()

start_str = start_date.strftime("%Y-%m-%d")
end_str = end_date.strftime("%Y-%m-%d")
period_label = {"daily": "日K线", "weekly": "周K线", "monthly": "月K线"}[kline_period]


# ═══════════════════════════════════════════════════════════════
# 标题栏 + 同轴操作按钮
# ═══════════════════════════════════════════════════════════════
hc1, hc2, hc3 = st.columns([0.4, 0.3, 0.3])
with hc1:
    st.subheader("🎯 股票选取")
with hc2:
    _ticker_ok = bool(ticker and str(ticker).strip())
    if st.button("➕ 加入自选股", use_container_width=True, key="pick_add_watch",
                 disabled=not _ticker_ok, help="请先在左侧选择一只股票" if not _ticker_ok else "将当前股票加入自选池"):
        sc, body = api_post("/api/watchlist", {"stock_code": ticker})
        # ⚠️ 兜底：api_post 网络失败时 body 可能为 None，原 else 分支 body.get 会抛 AttributeError
        _msg = body.get("message") if isinstance(body, dict) else ""
        if sc in (200, 201) or "已在" in _msg:
            st.success("✅ 已加入自选股")
        else:
            st.error(f"加入失败：{_msg or '未知错误'}")
with hc3:
    if st.button("🗑️ 加入垃圾股", use_container_width=True, key="pick_add_junk",
                 disabled=not _ticker_ok, help="请先在左侧选择一只股票" if not _ticker_ok else "将当前股票标记为垃圾股"):
        body = api_add_junk_stock(ticker)
        # ⚠️ 兜底：api_add_junk_stock 失败时 body 可能为 None，直接 body.get 会抛 AttributeError
        msg = body.get("message", "") if isinstance(body, dict) else ""
        if "成功" in msg or "已在" in msg:
            st.success("✅ 已加入垃圾股")
        else:
            st.error(f"加入失败：{msg or '未知错误'}")


# ═══════════════════════════════════════════════════════════════
# K 线图
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
@st.cache_data(show_spinner=False, ttl=300)
def _cached_kline(ticker, start, end, period, nonce: int = 0):
    # nonce 仅用于「强制刷新」时击穿 @st.cache_data 缓存（参数变化即重算重取数）
    # 1) 优先后端聚合接口（含复权）
    try:
        recs = api_kline(ticker, start=start, end=end, period=period)
    except Exception:
        recs = None
    if recs is not None:
        return pd.DataFrame(recs)
    # 2) 回退本地 fetcher 直连数据源
    try:
        df = fetcher.get_kline(ticker, start=start, end=end, period=period)
    except Exception:
        df = None
    # 统一返回 DataFrame（空则用空表，交由上层「空数据」兜底），绝不在区块内抛未捕获异常
    return df if df is not None else pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=600)
def _load_stock_events(ticker):
    """加载该股票的事件库（本地 SignalEngine 事件表，按代码过滤）。失败返回空表。"""
    try:
        engine = SignalEngine()
        ev = engine._load_events()
        if ev is None or ev.empty:
            return pd.DataFrame()
        code = str(ticker).zfill(6)
        if "ticker" in ev.columns:
            ev = ev[ev["ticker"].astype(str).str.zfill(6) == code]
        keep = [c for c in ("date", "title", "type") if c in ev.columns]
        return ev[keep] if keep else ev
    except Exception:
        return pd.DataFrame()


st.subheader(f"{stock_label} {period_label}")
df = None
data_ok = False

try:
    df = _cached_kline(ticker, start_str, end_str, kline_period,
                       nonce=int(st.session_state.get("_pick_kline_nonce", 0)))
    if df is None or df.empty:
        st.warning("⚠️ 暂未获取到该股票最新数据，正在使用历史快照。请稍后刷新页面。")
    else:
        df = DataCleaner.full_pipeline(df)
        data_ok = True
        st.caption(f"✅ 数据获取成功: {len(df)} 行 {_fmt_md(df['date'].iloc[0])}~{_fmt_md(df['date'].iloc[-1])}")

        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
        latest = df.iloc[-1]
        with col_info1:
            latest_close = float(latest.get('close') or 0.0)
            # ⚠️ 兜底：change_pct 可能为 None（数据不足），f"{None:.2f}" 会抛 TypeError 致整块 K 线渲染失败
            _chg_pct = latest.get('change_pct')
            _chg_pct = 0.0 if _chg_pct is None else float(_chg_pct)
            st.metric("最新收盘价", f"¥{latest_close:.2f}", delta=f"{_chg_pct:.2f}%")
        with col_info2:
            st.metric("区间最高", f"¥{df['high'].max():.2f}")
        with col_info3:
            st.metric("区间最低", f"¥{df['low'].min():.2f}")
        with col_info4:
            total_vol = df['volume'].sum()
            st.metric("区间总成交量", f"{total_vol/1e6:.0f}M")

        n = len(df)
        if n > 20:
            max_count = min(250, n)
            default_count = min(120, n)
            default_start = max(0, n - default_count)
            if "pick_view_count" not in st.session_state:
                st.session_state["pick_view_count"] = default_count
            if "pick_view_pos" not in st.session_state:
                st.session_state["pick_view_pos"] = default_start
            if st.session_state["pick_view_count"] > max_count:
                st.session_state["pick_view_count"] = max_count
            view_count = st.slider("显示 K 线数量", min_value=20, max_value=max_count, step=5,
                                   key="pick_view_count",
                                   help="控制图中展示的 K 线根数；数据量大时可聚焦近期行情。")
            max_start = max(0, n - view_count)
            if st.session_state["pick_view_pos"] > max_start:
                st.session_state["pick_view_pos"] = max_start
            if max_start >= 1:
                view_start = st.slider("显示位置（起始）", min_value=0, max_value=max_start, step=1,
                                       key="pick_view_pos")
            else:
                view_start = 0
        else:
            view_start = 0
            view_count = n

        # 鼠标拖拽：平移 / 区域缩放（控制 K 线图 dragmode）
        drag_mode = st.radio(
            "鼠标拖拽",
            options=["pan", "zoom"],
            format_func=lambda x: {"pan": "平移", "zoom": "区域缩放"}[x],
            index=0, key="pick_dragmode", horizontal=True,
            help="平移：拖动查看不同区间；区域缩放：框选放大某一段。",
        )

        # 事件标注开关（利好↑红 / 利空↓绿），默认开启
        show_events = st.checkbox("📌 标注事件（利好↑红 / 利空↓绿）", value=True, key="pick_show_events",
                                  help="在 K 线上叠加重大事件标注：利好标红、利空标绿。")
        events_df = None
        if show_events:
            with st.spinner("加载事件…"):
                events_df = _load_stock_events(ticker)

        # 当前可见区间统计
        vis = df.iloc[view_start:view_start + view_count]
        v_high = float(vis["high"].max())
        v_low = float(vis["low"].min())
        v_first = float(vis["close"].iloc[0])
        v_last = float(vis["close"].iloc[-1])
        v_chg = (v_last - v_first) / v_first * 100 if v_first else 0.0
        v_amp = (v_high - v_low) / v_first * 100 if v_first else 0.0
        v_avg = float(vis["close"].mean())
        st.caption(
            f"📊 当前显示区间：最高 ¥{v_high:.2f} / 最低 ¥{v_low:.2f} / "
            f"区间涨幅 {v_chg:+.2f}% / 振幅 {v_amp:.2f}% / 均价 ¥{v_avg:.2f}"
        )

        # 当前可见区间 K 线导出 CSV（新增功能：便于离线分析 / 二次加工）
        v_csv = vis.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "⬇️ 导出当前区间 K 线 CSV",
            data=v_csv,
            file_name=f"{ticker}_{kline_period}_{view_start + 1}-{view_start + view_count}.csv",
            mime="text/csv",
            key="pick_kline_csv",
            help="导出当前「显示位置 / 显示数量」框定区间的 K 线数据（含 OHLCV）",
        )

        fig = Visualizer.candlestick(df, title=f"{stock_label} {period_label}",
                                     ma_windows=ma_windows, show_volume=True,
                                     start_idx=view_start, n_show=view_count,
                                     dragmode=drag_mode,
                                     events=events_df if show_events else None)
        st.plotly_chart(fig, width="stretch", key="pick_kline_chart")

        # 事件面板（可折叠）：列出可见区间内事件，便于对照 K 线标注
        if show_events and events_df is not None and not events_df.empty:
            vis_dates = pd.to_datetime(df.iloc[view_start:view_start + view_count]["date"])
            if not vis_dates.empty:
                lo, hi = vis_dates.min(), vis_dates.max()
                ev_view = events_df.copy()
                ev_view["_dt"] = pd.to_datetime(ev_view["date"])
                ev_view = ev_view[(ev_view["_dt"] >= lo) & (ev_view["_dt"] <= hi)]
                if not ev_view.empty:
                    with st.expander(f"📌 本区间事件（{len(ev_view)} 条）", expanded=False):
                        disp = ev_view[["date", "title", "type"]].copy() if "type" in ev_view.columns else ev_view[["date", "title"]].copy()
                        disp = disp.sort_values("date")
                        st.dataframe(disp, use_container_width=True, hide_index=True)

        # 叠加上证基准对比（归一化多线，可选）
        if st.checkbox("📈 叠加上证基准对比（归一化）", value=False, key="pick_show_bench",
                       help="将个股与上证指数归一化到同一起点（100），直观对比个股相对大盘的强弱。"):
            with st.spinner("加载上证基准…"):
                idx_df = fetcher.get_index("000001", start=start_str, end=end_str)
            if idx_df is not None and not idx_df.empty:
                idx_df = idx_df.copy()
                idx_df["date"] = pd.to_datetime(idx_df["date"]).dt.strftime("%Y-%m-%d")
                stock_part = df[["date", "close"]].copy()
                stock_part["date"] = pd.to_datetime(stock_part["date"]).dt.strftime("%Y-%m-%d")
                merged = stock_part.merge(
                    idx_df[["date", "close"]], on="date", how="inner", suffixes=("_s", "_i"))
                if len(merged) >= 2:
                    merged = merged.rename(columns={"close_s": stock_label, "close_i": "上证指数"})
                    bfig = plot_normalized_multi(
                        merged, names_map={stock_label: stock_label, "上证指数": "上证指数"},
                        colors_map={stock_label: UP, "上证指数": "#7c5cff"},
                        title="个股 vs 上证基准（归一化起点=100）",
                        dark_mode=_theme_is_dark(), date_range=None, ma_periods=(),
                        selected=None, mode="normalized", show_baseline=True,
                        show_cross=False, show_drawdown=False, ma_type="sma")
                    st.plotly_chart(bfig, use_container_width=True, config={"displayModeBar": False},
                                    key="pick_bench")
                else:
                    st.info("区间内与上证基准无重合交易日，跳过对比。")
            else:
                st.info("上证基准数据获取失败，跳过对比。")
except Exception as e:
    st.error(f"⚠️ K 线加载异常：{str(e)[:80]}。请稍后刷新页面重试，或切换其它周期 / 区间。")


# ═══════════════════════════════════════════════════════════════
# 技术面分析 + 用户打分
# ═══════════════════════════════════════════════════════════════
if data_ok and df is not None:
    st.markdown("---")
    st.subheader("🧭 技术面分析")
    try:
        profile = SignalEngine().technical_profile(df)
        short, mid, long, composite = profile["short"], profile["mid"], profile["long"], profile["composite"]
        latest = df.iloc[-1]
        r5 = float(latest.get("return_5d", 0.0) or 0.0)
        r20 = float(latest.get("return_20d", 0.0) or 0.0)
        r60 = 0.0
        if len(df) >= 61:
            r60 = (float(df["close"].iloc[-1]) / float(df["close"].iloc[-61]) - 1) * 100

        analysis = technical_full_analysis(df)
        trend = analysis.get("trend", {})
        momentum = analysis.get("momentum", {})
        volume_info = analysis.get("volume", {})
        patterns = analysis.get("patterns", []) or []

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("**① 短期（5日）**")
            st.metric(f"{'+' if r5 >= 0 else ''}{r5:.2f}%", f"{short}分")
            st.caption("🟢 强势" if short >= 65 else ("🔴 偏弱" if short <= 40 else "⚪ 中性"))
        with c2:
            st.markdown("**② 中期（20日）**")
            st.metric(f"{'+' if r20 >= 0 else ''}{r20:.2f}%", f"{mid}分")
            st.caption("🟢 强势" if mid >= 65 else ("🔴 偏弱" if mid <= 40 else "⚪ 中性"))
        with c3:
            st.markdown("**③ 长期（60日）**")
            st.metric(f"{'+' if r60 >= 0 else ''}{r60:.2f}%", f"{long}分")
            st.caption("🟢 强势" if long >= 65 else ("🔴 偏弱" if long <= 40 else "⚪ 中性"))
        with c4:
            st.markdown("**④ 综合评分**")
            st.metric(f"{composite}/100", f"{'看多' if composite >= 65 else ('看空' if composite <= 40 else '观望')}")
            st.caption("短/中/长期加权")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("**均线 / 趋势**")
            if "error" not in trend:
                st.markdown(f"{'🟢' if trend.get('trend_score', 50) >= 60 else ('🔴' if trend.get('trend_score', 50) <= 40 else '⚪')} **{trend.get('arrangement', '—')}**")
                st.caption(trend.get("trend_label", ""))
            else:
                st.caption(trend.get("error", "数据不足"))
        with c2:
            st.markdown("**动量 / 涨跌幅**")
            if "error" not in momentum:
                rets = momentum.get("returns", {}) or {}
                # ⚠️ 兜底：returns 内 '5日'/'20日' 可能为 None，直接 f"{None:+.2f}" 抛 TypeError
                _r5 = rets.get("5日") or 0
                _r20 = rets.get("20日") or 0
                st.markdown(f"**{momentum.get('momentum_label', '—')}**")
                st.metric("5日涨幅", f"{_r5:+.2f}%", delta=f"20日 {_r20:+.2f}%")
            else:
                st.caption(momentum.get("error", "数据不足"))
        with c3:
            st.markdown("**量能分析**")
            if "error" not in volume_info:
                # ⚠️ 兜底：vol_ratio/vol_change_pct 可能为 None，避免 f-string 格式化崩溃
                ratio = volume_info.get("vol_ratio") or 1.0
                _vol_chg_pct = volume_info.get("vol_change_pct") or 0
                st.markdown(f"**{volume_info.get('volume_price_label', '—')}**")
                st.metric("量比(今/5日均)", f"{ratio:.2f}x", delta=f"{_vol_chg_pct:+.1f}%")
            else:
                st.caption(volume_info.get("error", "数据不足"))
        with c4:
            st.markdown("**K线形态（近10日）**")
            if patterns:
                for p in patterns[:5]:
                    icon = "🟢" if p.get("bias") == "看涨" else ("🔴" if p.get("bias") == "看跌" else "⚪")
                    # ⚠️ 兜底：pattern 的 date 可能为 None / 坏串，pd.Timestamp(None) 会抛 TypeError
                    _pdate = p.get("date")
                    try:
                        date_str = pd.Timestamp(_pdate).strftime("%m-%d") if _pdate is not None else "—"
                    except Exception:
                        date_str = "—"
                    st.markdown(f"{icon} `{date_str}` {p.get('name', '')}")
            else:
                st.caption("未识别到明显形态")

        if composite >= 65:
            verdict = "🟢 整体偏多，可关注"
        elif composite >= 40:
            verdict = "⚪ 多空平衡，观望为主"
        else:
            verdict = "🔴 整体偏空，谨慎参与"
        st.info(f"**综合评分 {composite}/100** · 短期 {short} / 中期 {mid} / 长期 {long} · {verdict}")

        # ── 📊 量化指标（RSI / MACD / KDJ / BOLL） ──
        st.markdown("---")
        st.subheader("📊 量化指标")

        def _calc_quant_indicators(d: pd.DataFrame) -> dict:
            close = pd.to_numeric(d["close"], errors="coerce")
            high = pd.to_numeric(d["high"], errors="coerce")
            low = pd.to_numeric(d["low"], errors="coerce")
            out = {}
            # RSI(14)
            try:
                delta = close.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, 1e-9)
                out["rsi"] = float((100 - 100 / (1 + rs)).iloc[-1])
            except Exception:
                out["rsi"] = None
            # MACD(12,26,9)
            try:
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                dif = ema12 - ema26
                dea = dif.ewm(span=9, adjust=False).mean()
                out["dif"] = float(dif.iloc[-1])
                out["dea"] = float(dea.iloc[-1])
                out["macd"] = float((dif.iloc[-1] - dea.iloc[-1]) * 2)
            except Exception:
                out["dif"] = out["dea"] = out["macd"] = None
            # KDJ(9,3,3)
            try:
                low9 = low.rolling(9).min()
                high9 = high.rolling(9).max()
                rsv = (close - low9) / (high9 - low9).replace(0, 1e-9) * 100
                k = rsv.ewm(com=2, adjust=False).mean()
                dd = k.ewm(com=2, adjust=False).mean()
                out["k"] = float(k.iloc[-1])
                out["d"] = float(dd.iloc[-1])
                out["j"] = float(3 * k.iloc[-1] - 2 * dd.iloc[-1])
            except Exception:
                out["k"] = out["d"] = out["j"] = None
            # BOLL(20,2) 位置
            try:
                mid_b = close.rolling(20).mean()
                std_b = close.rolling(20).std()
                upper_b = mid_b + 2 * std_b
                lower_b = mid_b - 2 * std_b
                rng = (upper_b.iloc[-1] - lower_b.iloc[-1]) or 1e-9
                out["boll_pct"] = float((close.iloc[-1] - lower_b.iloc[-1]) / rng * 100)
            except Exception:
                out["boll_pct"] = None
            return out

        qi = _calc_quant_indicators(df)
        qc1, qc2, qc3, qc4 = st.columns(4)
        with qc1:
            rsi = qi.get("rsi")
            if rsi is not None:
                rsi_tag = "超买" if rsi >= 70 else ("超卖" if rsi <= 30 else "中性")
                st.metric("RSI(14)", f"{rsi:.1f}", delta=rsi_tag, delta_color="off")
            else:
                st.metric("RSI(14)", "—")
        with qc2:
            macd = qi.get("macd")
            if macd is not None:
                st.metric("MACD 柱", f"{macd:+.3f}",
                          delta="金叉/多头" if macd >= 0 else "死叉/空头", delta_color="off")
                st.caption(f"DIF {qi['dif']:+.3f} / DEA {qi['dea']:+.3f}")
            else:
                st.metric("MACD 柱", "—")
        with qc3:
            k, d, j = qi.get("k"), qi.get("d"), qi.get("j")
            if k is not None:
                kdj_tag = "超买" if j >= 100 else ("超卖" if j <= 0 else "中性")
                st.metric("KDJ", f"K{k:.0f} D{d:.0f}", delta=f"J{j:.0f} · {kdj_tag}", delta_color="off")
            else:
                st.metric("KDJ", "—")
        with qc4:
            bp = qi.get("boll_pct")
            if bp is not None:
                pos = "近上轨" if bp >= 80 else ("近下轨" if bp <= 20 else "轨道中部")
                st.metric("BOLL 位置", f"{bp:.0f}%", delta=pos, delta_color="off")
            else:
                st.metric("BOLL 位置", "—")
        st.caption("RSI>70 超买 / <30 超卖；MACD 柱>0 多头动能；KDJ J>100 超买、<0 超卖；BOLL 位置=收盘价在布林带内的相对高度。")

        # 用户打分（独立 fragment，交互只重跑本块，提升响应速度）
        _render_user_score(ticker, stock_label)
    except Exception as e:
        st.error(f"技术面分析失败: {e}")
