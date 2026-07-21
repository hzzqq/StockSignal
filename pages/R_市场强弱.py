"""
页面 R：市场强弱一览（模仿五维归一化面板，做更轻量的「市场强弱一目了然」）

思路：把 上证/深证/创业板 三大指数 + 融资余额 + 北向累计净买额 + 大盘主力累计净流入
统一归一化到起点=100 叠加（复用 modules.linear_trends.plot_normalized_multi），
顶部用「市场强弱信号灯」把复杂多线压缩成一个直觉结论，让新手也能秒懂当前市场状态。

UI-only；fragment 内无整页 st.rerun；A股红涨绿跌（信号灯语义：强=红 / 震荡=黄 / 弱=绿，与价格色一致）；
与 H_市场驱动力（五维子图）互链，互为简化/详细视图。
"""
import requests

import pandas as pd
import streamlit as st

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, get_token, safe_switch_page, API_BASE
from modules.linear_trends import (
    get_index_series, get_northbound_history_series,
    get_market_cumulative_series, plot_normalized_multi, to_trend_csv,
    _slice_date_range, _IDX_NAMES, _IDX_COLORS,
)
from modules.margin_trading import get_margin_trading_data
from modules.page_widgets import (
    _section_title, _trend_controls, _in_trading_hours, _empty_info, UP, DOWN,
)
from modules.page_guard import safe_fragment

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

apply_page_config(page_title="市场强弱", page_icon="📊", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("📊 市场强弱一览（归一化多线 · 一眼看懂）")
st.caption("把指数与关键资金面统一归一化到起点=100 叠加，避免量纲差异；顶部信号灯把复杂多线压缩成一个直觉结论。"
           "想看更细的五维拆解，去《市场驱动力》。")
st.page_link("pages/H_市场驱动力.py", label="🧮 看《市场驱动力》五维归一化子图（详细版）", icon="🔗")


# 列名映射
_IDX_KEYS = ["sh000001", "sz399001", "sz399006"]
_FLOW_COLS = {
    "融资余额(亿)": "融资余额",
    "北向累计净买额(亿)": "北向累计净买额",
    "大盘主力累计净流入(亿)": "大盘主力累计净流入",
}


@st.cache_data(ttl=600, show_spinner=False)
def _build_strength_df(days=180):
    """组装市场强弱宽表：date + 三大指数 + 融资余额 + 北向累计 + 大盘主力累计。"""
    try:
        idx = get_index_series(days=days)
    except Exception:
        idx = pd.DataFrame()
    try:
        mg = get_margin_trading_data(days=days)
    except Exception:
        mg = pd.DataFrame()
    try:
        nb = get_northbound_history_series()
    except Exception:
        nb = pd.DataFrame()
    try:
        mc = get_market_cumulative_series(days=days)
    except Exception:
        mc = pd.DataFrame()

    frames = []
    if not idx.empty:
        frames.append(idx)
    if not mg.empty:
        m = mg.rename(columns={"日期": "date"}).copy()
        m["融资余额(亿)"] = pd.to_numeric(m.get("total_rzye"), errors="coerce") / 1e8
        frames.append(m[["date", "融资余额(亿)"]])
    if not nb.empty and "cumulative_yi" in nb.columns:
        frames.append(nb[["date", "cumulative_yi"]].rename(columns={"cumulative_yi": "北向累计净买额(亿)"}))
    if not mc.empty and "cumulative" in mc.columns:
        frames.append(mc[["date", "cumulative"]].rename(columns={"cumulative": "大盘主力累计净流入(亿)"}))
    if not frames:
        return pd.DataFrame()
    df = frames[0]
    for f in frames[1:]:
        df = df.merge(f, on="date", how="outer")
    return df.sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner=False)
def _watchlist_codes(token: str):
    try:
        resp = requests.get(f"{API_BASE}/api/watchlist",
                             headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get("data") or []
            return [d.get("stock_code") for d in data if d.get("stock_code")]
    except Exception:
        pass
    return []


def _watchlist_avg_normalized(codes, start, end, days):
    """计算自选股收盘价区间归一化均值（起点=100）。防御式：单股失败跳过。"""
    from modules.fetcher import StockFetcher
    try:
        if not codes:
            return None
        f = StockFetcher()
        s, e = start, end
        if s is None or e is None:
            import datetime
            e = datetime.date.today()
            s = (e - datetime.timedelta(days=days))
        normed = []
        for c in codes[:15]:
            try:
                d = f.get_daily(c, start=str(s), end=str(e))
            except Exception:
                continue
            if d is None or d.empty or len(d) < 2:
                continue
            col = None
            for cc in ("close", "收盘", "收盘价"):
                if cc in d.columns:
                    col = cc
                    break
            if col is None:
                continue
            ser = pd.to_numeric(d[col], errors="coerce").dropna()
            if ser.empty:
                continue
            first = ser.iloc[0]
            if not first or pd.isna(first):
                continue
            normed.append((ser / first * 100.0).round(2))
        if not normed:
            return None
        out = pd.concat(normed, axis=1).mean(axis=1)
        return out.tolist()
    except Exception:
        return None


def _strength_signal(d, keys):
    """计算各序列归一化最新值（区间内起点=100）与综合强弱评级。"""
    devs = []
    details = []
    for k in keys:
        if k not in d.columns:
            continue
        s = pd.to_numeric(d[k], errors="coerce").dropna()
        if len(s) < 2:
            continue
        first, last = s.iloc[0], s.iloc[-1]
        if not first or pd.isna(first):
            continue
        norm = last / first * 100.0
        dev = norm - 100.0
        devs.append(dev)
        details.append((k, norm, dev))
    if not devs:
        return None, [], 0.0
    avg = sum(devs) / len(devs)
    if avg > 2:
        level = ("🔴 强势", UP)
    elif avg < -2:
        level = ("🟢 弱势", DOWN)
    else:
        level = ("🟡 震荡", "#e0a800")
    return level, details, avg


def _strength_percentile(d, keys):
    """当前市场强弱综合偏离在所选区间内的历史百分位(0-100)。

    与 _strength_signal 同口径（以区间内首值为基线），对每条序列算归一化偏离，
    逐日取均值得到综合偏离时间序列，再求最新值在历史中的相对位置。
    数值越高代表比区间内多数时候更强。
    """
    try:
        comp = []
        for k in keys:
            if k not in d.columns:
                continue
            s = pd.to_numeric(d[k], errors="coerce").dropna()
            if len(s) < 2:
                continue
            first = s.iloc[0]
            if not first or pd.isna(first):
                continue
            comp.append(s / first * 100.0 - 100.0)
        if len(comp) < 2:
            return None
        comp = pd.concat(comp, axis=1).mean(axis=1).dropna()
        if comp.empty:
            return None
        cur = comp.iloc[-1]
        below = (comp < cur).sum()
        return round(below / len(comp) * 100.0, 1)
    except Exception:
        return None


@safe_fragment
def fragment_strength():
    _section_title("📈 市场强弱信号 + 归一化多线", accent="#2b8aef")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="str_auto")

    with st.spinner("加载市场强弱数据…"):
        df = _build_strength_df(days=180)
    if df is None or df.empty or "date" not in df.columns:
        _empty_info("暂无市场强弱数据（网络/代理受限或数据源暂未接入）。")
        return

    # 序列定义
    all_keys = _IDX_KEYS + list(_FLOW_COLS.keys())
    present = [k for k in all_keys if k in df.columns]
    names_map = {**_IDX_NAMES, **_FLOW_COLS}
    colors_map = dict(_IDX_COLORS)
    colors_map.update({
        "融资余额(亿)": "#f59e0b",
        "北向累计净买额(亿)": "#22c55e",
        "大盘主力累计净流入(亿)": "#06b6d4",
    })

    # 交互控件：区间 + 均线 + 序列多选 + 数值模式
    series_options = [(k, names_map.get(k, k)) for k in present]
    dr, ma, sel, mode, ma_type = _trend_controls(
        "str", days_default=180, preset_default="近180天",
        series_options=series_options, show_ma=True, mode_toggle=True,
    )
    keys = sel if sel else present

    # 信号计算（按当前区间/序列）
    d_view = _slice_date_range(df, dr)
    level, details, avg = _strength_signal(d_view, keys)

    # 顶部信号卡 + 各序列 chips
    if level:
        label, color = level
        pct = _strength_percentile(d_view, keys)
        pct_line = ""
        if pct is not None:
            pct_line = (
                f'<div style="font-size:12px;color:#9aa0a6;margin-top:4px;">'
                f'历史分位 <b style="color:{color}">{pct:.0f}%</b>'
                f' <span title="在当前所选区间内，当前市场强弱综合偏离处于第 {pct:.0f} 百分位——'
                f'数值越高代表比区间内多数时候更强，越低代表越弱。">ⓘ</span></div>'
            )
        c1, c2 = st.columns([0.32, 0.68])
        with c1:
            st.markdown(
                f'<div style="text-align:center;padding:14px 8px;border-radius:14px;'
                f'background:rgba(255,255,255,0.03);border:1px solid {color}55;">'
                f'<div style="font-size:30px;line-height:1.1;">{label.split()[0]}</div>'
                f'<div style="font-size:18px;font-weight:700;color:{color};">{label.split(" ",1)[1]}</div>'
                f'<div style="font-size:12px;color:#9aa0a6;margin-top:4px;">综合偏离 {avg:+.1f}</div>'
                f'{pct_line}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            chips = []
            for k, norm, dev in details:
                c = UP if dev >= 0 else DOWN
                chips.append(
                    f'<span style="display:inline-block;margin:3px 4px;padding:3px 9px;'
                    f'border-radius:999px;background:rgba(255,255,255,0.04);'
                    f'border:1px solid {c}55;font-size:12px;">'
                    f'{names_map.get(k,k)}：<b style="color:{c}">{norm:.1f}</b>'
                    f'{" ▲" if dev>=0 else " ▼"}</span>'
                )
            st.markdown("".join(chips), unsafe_allow_html=True)
            st.caption("数值=区间归一化（起点100）。>100 走强(红) / <100 走弱(绿)；信号灯语义与价格色一致：强=红、弱=绿。")

    # 可选：叠加自选股均值
    with st.expander("➕ 叠加自选股均值（可选）", expanded=False):
        if st.checkbox("把我的自选股区间归一化均值叠到图里", key="str_wl_on", value=False):
            codes = _watchlist_codes(get_token() or "")
            if not codes:
                st.info("暂无自选股，先去《持仓中心》加几只再叠加。")
            else:
                with st.spinner(f"计算 {len(codes[:15])} 只自选股均值…"):
                    avg_series = _watchlist_avg_normalized(codes, dr[0] if dr else None, dr[1] if dr else None, 180)
                if avg_series is None:
                    st.warning("自选股行情获取失败，已跳过叠加。")
                else:
                    d2 = d_view.copy()
                    d2["自选股均值"] = avg_series[: len(d2)]
                    df = d2
                    names_map = {**names_map, "自选股均值": "自选股均值"}
                    colors_map = {**colors_map, "自选股均值": "#ffffff"}
                    keys = keys + ["自选股均值"]

    fig = plot_normalized_multi(
        df, names_map=names_map, colors_map=colors_map,
        title="市场强弱归一化多线（起点=100）", dark_mode=dark,
        date_range=None, ma_periods=ma, selected=keys,
        mode=mode, show_baseline=True, show_cross=(len(ma) >= 2), show_drawdown=False, ma_type=ma_type,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="str_panel")

    # 数据表 + 导出
    with st.expander("📋 数据表（随区间 / 序列联动）"):
        tbl = _slice_date_range(df, dr)
        keep = [k for k in keys if k in tbl.columns]
        tbl = tbl[["date"] + keep] if keep else tbl[["date"]]
        st.dataframe(tbl, use_container_width=True, hide_index=True)
    csv = to_trend_csv(df, names_map=names_map, selected=keys, date_range=dr)
    st.download_button("⬇️ 导出 CSV", data=csv, file_name="市场强弱一览.csv", mime="text/csv")

    st.caption("💡 本页是《市场驱动力》的简化版：用更少、更关键的线 + 顶部信号灯，"
               "帮你秒懂「现在市场强还是弱」。需要五维（资金/情绪/估值/宏观/技术）逐项拆解时再去那页。")


# ───────────────────────── 页面主体 ─────────────────────────
fragment_strength()
