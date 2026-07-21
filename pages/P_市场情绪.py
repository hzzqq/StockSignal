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

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.market_drivers import get_market_drivers, DIMS
from modules.page_guard import safe_fragment
from modules.page_widgets import _section_title, _in_trading_hours

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

apply_page_config(page_title="市场情绪", page_icon="🌡️", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🌡️ 市场情绪 · 广度与情绪温度计")
st.caption("市场冷/热一眼看尽：广度(ADL/ADR/新高新低) + 情绪(VIX/涨停占比/PCR/北向/融资净买) + "
           "估值(PE 历史百分位/股息率) → 综合「市场温度」0-100。数据源同《市场驱动力》指标表，单源失败优雅降级。")


# ───────────────────────── 辅助函数 ─────────────────────────
def _last(s):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.iloc[-1]) if len(s) else None


def _spark(series, color, dark_mode):
    s = pd.to_numeric(series, errors="coerce").dropna().tail(40)
    if s.empty:
        return None
    fig = go.Figure(go.Scatter(
        x=list(range(len(s))), y=s.values, mode="lines",
        line=dict(width=2, color=color),
        fill="tozeroy", fillcolor=color + "22",
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
                                config={"displayModeBar": False}, key=f"spark_{key}")
            badge, bcolor, text = cfg["signal"](s)
            st.markdown(
                f"<span style='background:{bcolor}22;color:{bcolor};padding:2px 8px;"
                f"border-radius:8px;font-size:12px;font-weight:600'>{badge}</span>"
                f"　{text}", unsafe_allow_html=True)


# ───────────────────────── 各区块（@safe_fragment 错误边界） ─────────────────────────
@safe_fragment("市场温度计")
def fragment_thermometer():
    _section_title("🌡️ 综合市场温度（广度+情绪+估值多空加权）", accent="#f59e0b")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="mt_auto")
    df, meta = get_market_drivers(days=180)
    if df is None or df.empty:
        st.info("暂无市场数据（网络/代理受限或数据源暂未接入）。")
        _render_status(meta)
        return
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
    df, meta = get_market_drivers(days=180)
    if df is None or df.empty:
        st.info("暂无市场广度数据（网络/代理受限或数据源暂未接入）。")
        return
    cols = st.columns(len(_BREADTH))
    for c, cfg in zip(cols, _BREADTH):
        _card(c, cfg, df, dark)


@safe_fragment("市场情绪")
def fragment_sentiment():
    _section_title("🔥 市场情绪（恐慌/贪婪信号）", accent="#7c5cff")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="se_auto")
    df, meta = get_market_drivers(days=180)
    if df is None or df.empty:
        st.info("暂无市场情绪数据（网络/代理受限或数据源暂未接入）。")
        return
    cols = st.columns(len(_SENTIMENT))
    for c, cfg in zip(cols, _SENTIMENT):
        _card(c, cfg, df, dark)


@safe_fragment("市场估值")
def fragment_valuation():
    _section_title("💎 估值温度计（PE 百分位 / 股息率）", accent="#2b8aef")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="va_auto")
    df, meta = get_market_drivers(days=180)
    if df is None or df.empty:
        st.info("暂无估值数据（网络/代理受限或数据源暂未接入）。")
        return
    cols = st.columns(len(_VALUATION))
    for c, cfg in zip(cols, _VALUATION):
        _card(c, cfg, df, dark)


fragment_thermometer()
fragment_breadth()
fragment_sentiment()
fragment_valuation()

st.caption("🌡️ 《市场广度 & 情绪温度计》：与《市场驱动力》（五维归一化子图）互补——"
           "本页用温度计卡 + 信号灯直观呈现「市场冷/热到什么程度」，"
           "指标口径同 21 指标参考表（ADL/ADR/新高新低/VIX/PCR/涨停占比/北向/融资/PE/股息率）。"
           "单源失败优雅降级，绝不抛红错。")
