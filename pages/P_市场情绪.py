"""
页面 P：市场广度 & 情绪温度计仪表盘

区别于 H_市场驱动力（五维归一化子图，看「指标 vs 大盘相关性」），
本页聚焦「市场现在冷/热到什么程度」：
  · 广度（ADL / ADR / 新高新低）
  · 情绪（VIX / PCR / 涨停占比 / 北向净流入 / 融资净买入）
  · 估值（PE 历史百分位 / 股息率）
以直观的「温度计卡 + 信号灯 + sparkline」呈现，并给出综合「市场温度」读数(0-100)。

数据层复用 modules.market_drivers.get_market_drivers —— 该层照同一份 21 指标表
（table_20260721.csv）实现，单源失败优雅降级（绝不抛红错）。
"""
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.page_utils import render_standard_page, import_autorefresh
from modules.session import get_token, fragment_market_alerts_panel
from modules.market_drivers import get_market_drivers, DIMS
from modules.shepherd import (get_shepherd_indicators, get_shepherd_indicators_range,
                              THRESHOLDS, shepherd_temperature)
from modules.page_guard import safe_fragment
from modules.page_widgets import _section_title, _in_trading_hours, _empty_info
from modules.colors import _hex_to_rgba
from modules.chart_cache import cached_fig

st_autorefresh = import_autorefresh()

dark = render_standard_page(
    title="市场情绪 · 广度与情绪温度计", icon="🌡️",
    caption="市场冷/热一眼看尽：广度(ADL/ADR/新高新低) + 情绪(VIX/涨停占比/PCR/北向/融资净买) + "
            "估值(PE 历史百分位/股息率) → 综合「市场温度」0-100。数据源同《市场驱动力》指标表，单源失败优雅降级。",
)
st.page_link("pages/H_市场驱动力.py", label="📊 看《市场驱动力》五维归一化相关性分析（互补视角）", icon="🔗")


# ───────────────────────── 辅助函数 ─────────────────────────
def _cache_banner(meta):
    """当数据来自 SQLite 缓存降级时，显示提示横幅。"""
    if not meta or not isinstance(meta, dict):
        return
    if meta.get("_cache_fallback"):
        msg = meta.get("_cache_message", "当前展示为最近一次成功缓存的数据（网络暂时不可用）")
        st.markdown(
            f'<div style="background:#fff3cd;border:1px solid #ffc107;'
            f'border-radius:8px;padding:8px 14px;font-size:13px;color:#856404">'
            f'📦 <b>缓存模式</b>：{msg}</div>',
            unsafe_allow_html=True,
        )
    # 显示缓存时间戳（如果有）
    cached_keys = meta.get("cached_keys", [])
    stale_keys = meta.get("stale_keys", [])
    if stale_keys:
        st.caption(f"⚠️ 部分指标数据陈旧：{', '.join(k[0] for k in stale_keys)}")


def _last(s):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.iloc[-1]) if len(s) else None


@cached_fig(ttl=120)
def _spark(series, color, dark_mode):
    s = pd.to_numeric(series, errors="coerce").dropna().tail(40)
    if s.empty:
        return None
    # 统一走 colors._hex_to_rgba，杜绝 8 位 hex fillcolor bug
    fill = _hex_to_rgba(color, 0.13)
    fig = go.Figure(go.Scatter(
        x=list(range(len(s))), y=s.values, mode="lines",
        line=dict(width=2, color=color),
        fill="tozeroy", fillcolor=fill,
        hovertemplate="%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(
        height=70, margin=dict(l=0, r=0, t=4, b=0),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def _temp_level(t):
    if t >= 75:
        return ("过热", "🚨", "#ee2a2a")
    if t >= 60:
        return ("偏热", "🔥", "#f59e0b")
    if t >= 40:
        return ("中性", "⚖️", "#2b8aef")
    if t >= 20:
        return ("偏冷", "🌡️", "#16c2c2")
    return ("冰点", "🥶", "#3b82f6")


def _temp_bar(t, color):
    return (
        f'<div style="background:linear-gradient(90deg,#3b82f6,#16c2c2,#10b981,#f59e0b,#ee2a2a);'
        f'height:14px;border-radius:7px;position:relative;margin:6px 0 2px">'
        f'<div style="position:absolute;left:{t:.1f}%;top:-4px;width:4px;height:22px;'
        f'background:#222;border-radius:2px;transform:translateX(-50%)"></div></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:11px;'
        f'color:#999;margin-top:2px"><span>冰点 0</span><span>中性 50</span><span>过热 100</span></div>'
    )


# 各指标对「市场温度」的方向贡献：+1 越高越热，-1 越高越冷，0 不参与
_DIR = {
    "adl": 1, "adr": 1, "nhnl": 1,
    "margin_balance": 1, "margin_net": 1, "north_net": 1,
    "vix": -1, "pcr": -1, "zt_ratio": 1,
    "pe_pct": 1, "div_yield": -1,
    "m2_yoy": 1, "shr_zgm": 1, "yield_spread": 1, "pmi": 1,
    "rsi": 1, "bias": 1, "boll": 0, "idx_ma5": 0, "idx_ma20": 0,
}


def _market_temp(df):
    subs = []
    for k, d in _DIR.items():
        if d == 0 or k not in df.columns:
            continue
        s = pd.to_numeric(df[k], errors="coerce").dropna()
        if len(s) < 3:
            continue
        pct = s.rank(pct=True).iloc[-1]  # 最新值在历史分布中的分位 0-1
        subs.append(pct * 100 if d > 0 else (1 - pct) * 100)
    return float(np.mean(subs)) if subs else None


def _render_status(meta):
    if not meta:
        return
    lines = []
    for d in DIMS:
        info = meta.get(d) or {}
        av = info.get("available") or []
        un = info.get("unavailable") or []
        if av and not un:
            lines.append(f"**{d}** {len(av)}项✅")
        elif av and un:
            lines.append(f"**{d}** {len(av)}项✅/暂缺{'、'.join(k for k, _ in un)}")
        else:
            lines.append(f"**{d}** 暂缺")
    st.caption("📌 维度接入：" + "　".join(lines))


# ───────────────────────── 信号灯（自定义温度计语义，非涨跌配色） ─────────────────────────
def _adl_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    s2 = pd.to_numeric(s, errors="coerce").dropna()
    if len(s2) >= 20:
        chg = s2.iloc[-1] - s2.iloc[-20]
        if chg > 0:
            return ("上行", "#10b981", f"ADL 近20日 +{chg:,.0f}，广度改善")
        return ("下行", "#ee2a2a", f"ADL 近20日 {chg:,.0f}，广度走弱")
    return ("—", "#888", "样本不足")


def _adr_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v > 1.2:
        return ("偏强", "#10b981", f"ADR {v:.2f}，普涨格局")
    if v < 0.8:
        return ("偏弱", "#ee2a2a", f"ADR {v:.2f}，普跌格局")
    return ("中性", "#f59e0b", f"ADR {v:.2f}，涨跌参半")


def _nhnl_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v > 0:
        return ("新高占优", "#10b981", f"新高-新低 {v:,.0f}，趋势强")
    return ("新低占优", "#ee2a2a", f"新高-新低 {v:,.0f}，趋势弱")


def _vix_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "数据源暂未接入")
    if v >= 30:
        return ("恐慌", "#ee2a2a", f"VIX {v:.1f} 高度恐慌，常对应短期底部")
    if v >= 20:
        return ("偏高", "#f59e0b", f"VIX {v:.1f} 偏高，避险升温")
    return ("平稳", "#10b981", f"VIX {v:.1f} 低位，情绪平稳")


def _pcr_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "数据源暂未接入")
    if v >= 1.0:
        return ("认沽占优", "#ee2a2a", f"PCR {v:.2f} 高位（恐慌）→ 常对应指数底部")
    if v <= 0.7:
        return ("认购占优", "#10b981", f"PCR {v:.2f} 低位（乐观）")
    return ("中性", "#f59e0b", f"PCR {v:.2f} 中性")


def _zt_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 5:
        return ("亢奋", "#ee2a2a", f"涨停占比 {v:.2f}%，赚钱效应爆棚")
    if v >= 2:
        return ("活跃", "#f59e0b", f"涨停占比 {v:.2f}%，情绪活跃")
    if v <= 1:
        return ("冰点", "#3b82f6", f"涨停占比 {v:.2f}%，情绪冰点")
    return ("中性", "#10b981", f"涨停占比 {v:.2f}%，中性")


def _north_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "数据源暂未接入/暂不可用")
    if v > 0:
        return ("净流入", "#10b981", f"北向净流入 {v:.1f} 亿，提振指数")
    return ("净流出", "#ee2a2a", f"北向净流出 {abs(v):.1f} 亿，施压指数")


def _margin_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "数据源暂未接入")
    if v > 0:
        return ("净买入", "#10b981", f"融资净买入 {v:.1f} 亿，加杠杆推动")
    return ("净偿还", "#ee2a2a", f"融资净偿还 {abs(v):.1f} 亿，降杠杆")


def _pe_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 80:
        return ("高估", "#ee2a2a", f"PE 历史百分位 {v:.0f}%，恐高")
    if v <= 20:
        return ("低估", "#10b981", f"PE 历史百分位 {v:.0f}%，配置价值凸显")
    return ("中性", "#f59e0b", f"PE 历史百分位 {v:.0f}%")


def _div_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 2.5:
        return ("高股息", "#10b981", f"股息率 {v:.2f}%，指数低位配置价值高")
    if v <= 1.5:
        return ("偏低", "#ee2a2a", f"股息率 {v:.2f}%，指数高位")
    return ("中性", "#f59e0b", f"股息率 {v:.2f}%")


# ───────────────────────── 指标配置（分组） ─────────────────────────
_BREADTH = [
    dict(key="adl", name="腾落指数(ADL)", color="#ee2a2a", fmt=lambda v: f"{v:,.0f}", signal=_adl_sig),
    dict(key="adr", name="涨跌比率(ADR)", color="#ee2a2a", fmt=lambda v: f"{v:.2f}", signal=_adr_sig),
    dict(key="nhnl", name="新高新低指标", color="#ee2a2a", fmt=lambda v: f"{v:,.0f}", signal=_nhnl_sig),
]
_SENTIMENT = [
    dict(key="vix", name="VIX恐慌指数", color="#7c5cff", fmt=lambda v: f"{v:.1f}", signal=_vix_sig),
    dict(key="pcr", name="PCR(认沽/认购比)", color="#7c5cff", fmt=lambda v: f"{v:.2f}", signal=_pcr_sig),
    dict(key="zt_ratio", name="涨停家数占比", color="#7c5cff", fmt=lambda v: f"{v:.2f}%", signal=_zt_sig),
    dict(key="north_net", name="北向资金净流入", color="#7c5cff", fmt=lambda v: f"{v:+.1f}亿", signal=_north_sig),
    dict(key="margin_net", name="融资净买入额", color="#7c5cff", fmt=lambda v: f"{v:+.1f}亿", signal=_margin_sig),
]
_VALUATION = [
    dict(key="pe_pct", name="PE历史百分位", color="#2b8aef", fmt=lambda v: f"{v:.0f}%", signal=_pe_sig),
    dict(key="div_yield", name="股息率", color="#2b8aef", fmt=lambda v: f"{v:.2f}%", signal=_div_sig),
]


def _card(col, cfg, df, dark_mode):
    key = cfg["key"]
    with col:
        with st.container(border=True):
            st.markdown(f"**{cfg['name']}**")
            try:
                if key not in df.columns or df[key].dropna().empty:
                    st.caption("⚠️ 数据源暂未接入（需联网代理）")
                    return
                s = pd.to_numeric(df[key], errors="coerce").dropna()
                v = float(s.iloc[-1])
                st.markdown(f"<div style='font-size:26px;font-weight:700;color:{cfg['color']}'>"
                            f"{cfg['fmt'](v)}</div>", unsafe_allow_html=True)
                fig = _spark(s, cfg["color"], dark_mode)
                if fig:
                    st.plotly_chart(fig, use_container_width=True,
                                    config={"displaylogo": False, "responsive": True, "displayModeBar": False}, key=f"spark_{key}")
                badge, bcolor, text = cfg["signal"](s)
                st.markdown(
                    f"<span style='background:{bcolor}22;color:{bcolor};padding:2px 8px;"
                    f"border-radius:8px;font-size:12px;font-weight:600'>{badge}</span>"
                    f"　{text}", unsafe_allow_html=True)
            except Exception as e:
                st.caption(f"⚠️ 数据异常（{type(e).__name__}）")


@st.cache_data(ttl=120, show_spinner=False)
def _load_drivers(days: int = 180):
    """缓存市场驱动力取数，避免多个 fragment 重复拉取同一份数据。"""
    return get_market_drivers(days=days)


# ───────────────────────── 各区块（@safe_fragment 错误边界） ─────────────────────────
@safe_fragment("市场温度计")
def fragment_thermometer():
    _section_title("🌡️ 综合市场温度（广度+情绪+估值多空加权）", accent="#f59e0b")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="mt_auto")
    try:
        with st.spinner("加载市场驱动力数据…"):
            df, meta = _load_drivers(180)
    except Exception as e:
        st.error(f"市场驱动力数据加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无市场数据（网络/代理受限或数据源暂未接入）。")
        _render_status(meta)
        return
    _cache_banner(meta)  # 缓存降级提示
    t = _market_temp(df)
    if t is None:
        st.warning("可用指标不足，无法计算综合温度。")
        _render_status(meta)
        return
    level, emoji, color = _temp_level(t)
    st.markdown(f"### {emoji} 市场温度 {t:.0f} / 100　"
                f"<span style='color:{color};font-size:20px'>{level}</span>",
                unsafe_allow_html=True)
    st.markdown(_temp_bar(t, color), unsafe_allow_html=True)
    n = sum(1 for k, d in _DIR.items() if d != 0 and k in df.columns)
    st.caption(f"基于 {n} 项可用指标的近期分位多空加权（高=热：ADR/涨停/PE/北向/融资净买；"
               f"高=冷：VIX/PCR/股息率）。温度计为风险/健康语义，与价格涨跌红绿无关。")
    _render_status(meta)


@safe_fragment("市场广度")
def fragment_breadth():
    _section_title("📏 市场广度（涨跌家数透视）", accent="#ee2a2a")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="br_auto")
    try:
        with st.spinner("加载市场驱动力数据…"):
            df, meta = _load_drivers(180)
    except Exception as e:
        st.error(f"市场驱动力数据加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无市场广度数据（网络/代理受限或数据源暂未接入）。")
        _render_status(meta)
        return
    _cache_banner(meta)
    cols = st.columns(len(_BREADTH))
    for c, cfg in zip(cols, _BREADTH):
        _card(c, cfg, df, dark)


@safe_fragment("市场情绪")
def fragment_sentiment():
    _section_title("🔥 市场情绪（恐慌/贪婪信号）", accent="#7c5cff")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="se_auto")
    try:
        with st.spinner("加载市场驱动力数据…"):
            df, meta = _load_drivers(180)
    except Exception as e:
        st.error(f"市场驱动力数据加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无市场情绪数据（网络/代理受限或数据源暂未接入）。")
        _render_status(meta)
        return
    _cache_banner(meta)
    cols = st.columns(len(_SENTIMENT))
    for c, cfg in zip(cols, _SENTIMENT):
        _card(c, cfg, df, dark)


@safe_fragment("市场估值")
def fragment_valuation():
    _section_title("💎 估值温度计（PE 百分位 / 股息率）", accent="#2b8aef")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="va_auto")
    try:
        with st.spinner("加载市场驱动力数据…"):
            df, meta = _load_drivers(180)
    except Exception as e:
        st.error(f"市场驱动力数据加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无估值数据（网络/代理受限或数据源暂未接入）。")
        _render_status(meta)
        return
    _cache_banner(meta)
    cols = st.columns(len(_VALUATION))
    for c, cfg in zip(cols, _VALUATION):
        _card(c, cfg, df, dark)


# ───────────────────────── 牧羊人指标（股海牧羊人·情绪温度计） ─────────────────────────
def _shep_sig_impl(key, s):
    """按 THRESHOLDS 给单一牧羊人指标打信号灯（高=热 / 高=冷）。"""
    v = _last(s)
    th = THRESHOLDS.get(key)
    if v is None or th is None:
        return ("—", "#888", "暂无数据")
    if th["dir"] > 0:
        if v >= th["hot"]:
            return (th["hot_label"], "#ee2a2a", f"{th['name']} {v:.0f}{th['unit']}，情绪亢奋")
        if v >= th["warm"]:
            return ("常温", "#f59e0b", f"{th['name']} {v:.0f}{th['unit']}，中性")
        return (th["cold_label"], "#3b82f6", f"{th['name']} {v:.0f}{th['unit']}，偏冷")
    else:
        if v <= th["hot"]:
            return (th["hot_label"], "#10b981", f"{th['name']} {v:.0f}{th['unit']}，安全")
        if v <= th["warm"]:
            return ("常温", "#f59e0b", f"{th['name']} {v:.0f}{th['unit']}，中性")
        return (th["cold_label"], "#ee2a2a", f"{th['name']} {v:.0f}{th['unit']}，风险")


def _make_shep_sig(key):
    def _sig(s):
        return _shep_sig_impl(key, s)
    return _sig


_SHEPHERD = [
    dict(key="up_count", name="上涨家数", color="#ee2a2a", fmt=lambda v: f"{v:,.0f}",
         signal=_make_shep_sig("up_count")),
    dict(key="down_count", name="下跌家数", color="#3b82f6", fmt=lambda v: f"{v:,.0f}",
         signal=_make_shep_sig("down_count")),
    dict(key="limit_up", name="涨停家数", color="#ee2a2a", fmt=lambda v: f"{v:,.0f}",
         signal=_make_shep_sig("limit_up")),
    dict(key="limit_down", name="跌停家数", color="#3b82f6", fmt=lambda v: f"{v:,.0f}",
         signal=_make_shep_sig("limit_down")),
    dict(key="zt_prev_ret", name="昨日涨停表现", color="#7c5cff", fmt=lambda v: f"{v:+.2f}%",
         signal=_make_shep_sig("zt_prev_ret")),
    dict(key="red_ratio", name="红盘占比", color="#7c5cff", fmt=lambda v: f"{v:.1f}%",
         signal=_make_shep_sig("red_ratio")),
    dict(key="connect_hl", name="连板高度", color="#f59e0b", fmt=lambda v: f"{v:.0f}板",
         signal=_make_shep_sig("connect_hl")),
    dict(key="zt_fail_ratio", name="炸板率", color="#f59e0b", fmt=lambda v: f"{v:.1f}%",
         signal=_make_shep_sig("zt_fail_ratio")),
]


@st.cache_data(ttl=600, show_spinner=False)
def _load_shepherd(days: int = 60):
    """缓存牧羊人指标取数（历史回测 + 降级）。"""
    return get_shepherd_indicators(days=days)


@st.cache_data(ttl=600, show_spinner=False)
def _load_shepherd_range(start_date, end_date, backfill: bool = False):
    """缓存牧羊人指标自定义日期范围取数。"""
    return get_shepherd_indicators_range(start_date, end_date, backfill=backfill)


@cached_fig(ttl=120)
def _build_shepherd_chart(d, dark):
    """构建牧羊人指标双行折线图（重计算，按数据+主题缓存）。"""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=("涨跌 / 涨停 / 跌停家数", "昨日涨停表现(%) / 红盘占比(%)"),
        row_heights=[1, 1],
    )
    fam = dict(up_count=("#ee2a2a", "上涨家数"), down_count=("#3b82f6", "下跌家数"),
               limit_up=("#f59e0b", "涨停家数"), limit_down=("#16c2c2", "跌停家数"))
    for k, (col, name) in fam.items():
        if k in d.columns:
            s = pd.to_numeric(d[k], errors="coerce").dropna()
            if s.empty:
                continue
            is_pt = len(s) < 2  # 仅末日快照点（涨跌/跌停）→ 菱形标记
            tr = dict(x=d["date"], y=s.values, name=name + ("" if not is_pt else " (今)"),
                      mode="markers" if is_pt else "lines",
                      line=dict(width=1.8, color=col),
                      hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}：%{{y:.0f}}<extra></extra>")
            if is_pt:
                tr["marker"] = dict(size=11, symbol="diamond", color=col)
            fig.add_trace(go.Scatter(**tr), row=1, col=1)
    pct = dict(zt_prev_ret=("#7c5cff", "昨日涨停表现%"), red_ratio=("#ee2a2a", "红盘占比%"))
    for k, (col, name) in pct.items():
        if k in d.columns:
            s = pd.to_numeric(d[k], errors="coerce").dropna()
            if s.empty:
                continue
            is_pt = len(s) < 2
            tr = dict(x=d["date"], y=s.values, name=name + ("" if not is_pt else " (今)"),
                      mode="markers" if is_pt else "lines",
                      line=dict(width=1.8, color=col),
                      hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}：%{{y:.2f}}%<extra></extra>")
            if is_pt:
                tr["marker"] = dict(size=11, symbol="diamond", color=col)
            fig.add_trace(go.Scatter(**tr), row=2, col=1)
    if "limit_up" in d.columns:
        fig.add_hline(y=50, line_dash="dot", line_color="#888", row=1, col=1,
                      annotation_text="涨停50(亢奋)", annotation_font_size=9)
    if "zt_prev_ret" in d.columns:
        fig.add_hline(y=0, line_dash="dot", line_color="#888", row=2, col=1)
        fig.add_hline(y=3, line_dash="dot", line_color="#888", row=2, col=1,
                      annotation_text="昨板3%(炸裂)", annotation_font_size=9)
    theme = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6e6e6" if dark else "#1a1a1a"),
        xaxis=dict(gridcolor="#2a2a3a" if dark else "#ececec"),
        yaxis=dict(gridcolor="#2a2a3a" if dark else "#ececec"),
    )
    fig.update_layout(
        height=560, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center", font=dict(size=10)),
        margin=dict(l=55, r=25, t=60, b=40), hovermode="x unified", **theme)
    fig.update_xaxes(tickangle=-30)
    return fig


@safe_fragment("牧羊人指标卡")
def fragment_shepherd():
    _section_title("🐑 牧羊人指标（股海牧羊人·情绪温度计）", accent="#f59e0b")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=120000, limit=120, key="shep_auto")
    try:
        with st.spinner("加载牧羊人指标…"):
            df, meta = _load_shepherd(60)
    except Exception as e:
        st.error(f"牧羊人指标加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无牧羊人指标数据（网络/代理受限）。")
        return
    # 牧羊人温度（最新一行快照 + 近期分位）
    latest = {k: float(df[k].iloc[-1]) for k in THRESHOLDS
              if k in df.columns and pd.notna(df[k].iloc[-1])}
    if latest:
        t = shepherd_temperature(latest)
        level, emoji, color = _temp_level(t)
        st.markdown(f"### {emoji} 牧羊人温度 {t:.0f} / 100　"
                    f"<span style='color:{color};font-size:20px'>{level}</span>",
                    unsafe_allow_html=True)
        st.markdown(_temp_bar(t, color), unsafe_allow_html=True)
        st.caption("综合「上涨/涨停/昨日涨停表现/红盘占比/连板高度」近期分位（高=热），"
                   "与价格涨跌红绿无关。数据源：akshare 涨停池/昨日涨停池/全A快照。")
    cols = st.columns(len(_SHEPHERD))
    for c, cfg in zip(cols, _SHEPHERD):
        _card(c, cfg, df, dark)


@safe_fragment("牧羊人折线图")
def fragment_shepherd_chart():
    _section_title("📈 牧羊人指标折线图（真实历史序列）", accent="#7c5cff")
    range_opts = {
        "全部（2007 起）": 999999,
        "近 5 年（1250 交易日）": 1250,
        "近 1 年（250 交易日）": 250,
        "近 60 交易日": 60,
        "自定义日期范围…": "custom",
    }
    key = "shep_range"
    cur = st.session_state.get(key, "全部（2007 起）")
    try:
        sel = st.selectbox("历史范围", list(range_opts), index=list(range_opts).index(cur) if cur in range_opts else 0,
                           key=key)
    except Exception:  # noqa: BLE001
        sel = "全部（2007 起）"
    custom_mode = range_opts[sel] == "custom"
    start_date = end_date = None
    backfill = False
    if custom_mode:
        today = pd.Timestamp.now().date()
        default_start = today - pd.Timedelta(days=365)
        try:
            start_date = st.date_input("开始日期", value=default_start, max_value=today, key="shep_start")
            end_date = st.date_input("结束日期", value=today, max_value=today, key="shep_end")
        except Exception:  # noqa: BLE001
            start_date, end_date = default_start, today
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        backfill = st.checkbox("自动补算近期缺失数据（涨停/连板/炸板/昨板，东财仅支持最近约12个交易日）",
                               value=False, key="shep_backfill")
    try:
        with st.spinner("加载历史序列…"):
            if custom_mode:
                df, meta = _load_shepherd_range(start_date, end_date, backfill)
            else:
                df, meta = _load_shepherd(range_opts[sel])
    except Exception as e:
        st.error(f"牧羊人历史加载失败：{e}")
        return
    if df is None or df.empty or "date" not in df.columns:
        _empty_info("暂无牧羊人历史数据（网络/代理受限或所选日期范围未开始统计）。")
        return
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")
    if len(d) < 2:
        _empty_info("历史样本不足。")
        return
    # ── 大数据渲染优化（前端性能#A）：范围过大时降采样 ──
    # 牧羊人「全部(2007起)」约 4772 点，6 条折线共 ~28k 数据点，Plotly JSON 体积 273KB；
    # 均匀降采样到 ~800 点（强制保留首末点，末点=最新数据最关键）后体积 ~43KB（实测 -84%），
    # 浏览器端渲染流畅且趋势不变。近 1 年/60 日本就不大，不降采样。
    MAX_POINTS = 800
    if len(d) > MAX_POINTS:
        step = len(d) / MAX_POINTS
        idx = sorted(set([0] + [int(i * step) for i in range(1, MAX_POINTS)] + [len(d) - 1]))
        d = d.iloc[idx].reset_index(drop=True)
    fig = _build_shepherd_chart(d, dark)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "responsive": True, "displayModeBar": False}, key="shep_lines")
    caption = ("🐑 牧羊人指标源自抖音博主「股海牧羊人」《炒股绕不开的第一步》情绪温度计方法论："
               "不盯指数红绿，先看大盘脸色（涨跌家数/涨停跌停/昨日涨停表现）。"
               "近 60 日为 akshare 实时回测；长区间读取 2007 起全 A 重构序列"
               "（新浪日线聚合，涨跌/红盘为真实重构，涨停/跌停为板块规则近似，近期为东财真实）。")
    if custom_mode:
        dr = meta.get("date_range", (str(start_date), str(end_date)))
        caption += f" 当前区间：{dr[0]} 至 {dr[1]}。"
    missing = meta.get("missing_columns", {})
    if missing:
        names = [THRESHOLDS.get(k, {}).get("name", k) for k in missing.keys()]
        caption += f" ⚠️ 以下指标在所选时段内缺失（未开始统计或数据源未覆盖）：{', '.join(names)}。"
    st.caption(caption)


# 市场异动面板已抽取到 modules.session.fragment_market_alerts_panel（全局共享，风格统一）。

fragment_thermometer()
fragment_breadth()
fragment_sentiment()
fragment_valuation()
fragment_shepherd()
fragment_shepherd_chart()
fragment_market_alerts_panel()

st.caption("🌡️ 《市场广度 & 情绪温度计》：与《市场驱动力》（五维归一化子图）互补——"
           "本页用温度计卡 + 信号灯直观呈现「市场冷/热到什么程度」，"
           "指标口径同 21 指标参考表（ADL/ADR/新高新低/VIX/PCR/涨停占比/北向/融资/PE/股息率）。"
           "单源失败优雅降级，绝不抛红错。")
