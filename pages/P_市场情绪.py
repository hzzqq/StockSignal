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
from datetime import datetime

from modules.page_utils import render_standard_page, import_autorefresh
from modules.ui_theme import sf_card, sf_metric
from modules.session import get_token, fragment_market_alerts_panel
from modules.market_drivers import get_market_drivers, DIMS
from modules.shepherd import (get_shepherd_indicators, get_shepherd_indicators_range,
                              THRESHOLDS, shepherd_temperature,
                              get_zt_industry_distribution, get_zt_top_board,
                              get_zt_ladder)
from modules import shepherd_forecast as _sf
from modules import shepherd_note as _sn
from modules import shepherd_ladder as _sl
from modules.page_guard import safe_fragment
from modules.page_widgets import _section_title, _in_trading_hours, _empty_info
from modules.colors import _hex_to_rgba
from modules.chart_cache import cached_fig

from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box
st_autorefresh = import_autorefresh()

dark = render_standard_page(
    title="市场情绪 · 广度与情绪温度计", icon="🌡️",
    caption="市场冷/热一眼看尽：广度(ADL/ADR/新高新低) + 情绪(VIX/涨停占比/PCR/北向/融资净买) + "
            "估值(PE 历史百分位/股息率) → 综合「市场温度」0-100。数据源同《市场驱动力》指标表，单源失败优雅降级。",
)
st.page_link("pages/H_市场驱动力.py", label="📊 看《市场驱动力》五维归一化相关性分析（互补视角）", icon="🔗")
sf_card("市场温度计导读", "本页用「温度计卡 + 信号灯 + sparkline」呈现市场冷/热：广度(ADL/ADR/新高新低)、情绪(VIX/涨停占比/PCR/北向/融资净买)、估值(PE 百分位/股息率)，并给出综合「市场温度」0-100 读数。单源失败优雅降级。", icon="🌡️")

# ── 首页快捷入口跳转聚焦（一次性：pop 掉标记，刷新即恢复常态）──
_FOCUS_NOTE = bool(st.session_state.pop("shep_focus_note", False))
if _FOCUS_NOTE:
    st.markdown(
        "<div style='border-left:4px solid #7c5cff;background:rgba(124,92,255,.10);"
        "border-radius:8px;padding:10px 14px;font-size:13px;margin-bottom:6px'>"
        "📔 已从首页跳转 —— <b>情绪笔记 / 次日走势预判</b>在页面下方，已为你高亮 👇</div>",
        unsafe_allow_html=True,
    )


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
        xc_handle_error("市场驱动力数据加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
        return
    if df is None or df.empty:
        _empty_info("暂无市场数据（网络/代理受限或数据源暂未接入）。")
        _render_status(meta)
        return
    _cache_banner(meta)  # 缓存降级提示
    t = _market_temp(df)
    if t is None:
        xc_warn_box("可用指标不足，无法计算综合温度。")
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
        xc_handle_error("市场驱动力数据加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
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
        xc_handle_error("市场驱动力数据加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
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
        xc_handle_error("市场驱动力数据加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
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
    """按 THRESHOLDS 给单一牧羊人指标打信号灯（高=热 / 高=冷 / dir=0 观察项）。"""
    v = _last(s)
    th = THRESHOLDS.get(key)
    if v is None or th is None:
        return ("—", "#888", "暂无数据")
    if th["dir"] == 0:
        return ("观察", "#888", f"{th['name']} {v:.2f}{th['unit']}（不参与温度计）")
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


# ───────── 复盘方法论新增卡（视频《如何复盘非常重要》，含杨哥规律文案）─────────
def _median_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 1.0:
        return ("普涨修复", "#ee2a2a", f"中位数 {v:+.2f}%，今日人均赚钱（确定性修复）")
    if v >= 0:
        return ("中性", "#f59e0b", f"中位数 {v:+.2f}%，人均微赚/微亏")
    return ("亏钱效应", "#3b82f6", f"中位数 {v:+.2f}%，今日人均亏钱")


def _hb_wave_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 30:
        return ("易V反", "#f59e0b", f"回头波>10% 共 {v:.0f} 家；杨哥规律：≥30~50 家次日易V反")
    if v >= 20:
        return ("分歧", "#f59e0b", f"回头波>10% 共 {v:.0f} 家，说多不多说少不少")
    return ("追高安全", "#10b981", f"回头波>10% 仅 {v:.0f} 家，追高回撤小")


def _zbfail_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 45:
        return ("分歧大", "#ee2a2a", f"炸板 {v:.0f} 家；炸板率≥50% 次日易V反(杨哥规律)")
    if v >= 20:
        return ("分歧", "#f59e0b", f"炸板 {v:.0f} 家")
    return ("封板稳", "#10b981", f"炸板仅 {v:.0f} 家")


def _c2b_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 15:
        return ("梯队厚", "#ee2a2a", f"2板及以上 {v:.0f} 家，赚钱效应好")
    if v >= 5:
        return ("常温", "#f59e0b", f"2板及以上 {v:.0f} 家")
    return ("梯队断层", "#3b82f6", f"2板及以上仅 {v:.0f} 家")


def _fc_sig(s):
    v = _last(s)
    if v is None:
        return ("—", "#888", "暂无数据")
    if v >= 1.0:
        return ("封板强", "#ee2a2a", f"平均封成比 {v:.2f}（封板资金/成交额）")
    if v >= 0.4:
        return ("常温", "#f59e0b", f"平均封成比 {v:.2f}")
    return ("封板弱", "#3b82f6", f"平均封成比 {v:.2f}")


_SHEPHERD_REVIEW = [
    dict(key="median_chg", name="中位数涨跌幅", color="#ee2a2a", fmt=lambda v: f"{v:+.2f}%",
         signal=_median_sig),
    dict(key="hb_wave10", name="回头波>10%家数", color="#7c5cff", fmt=lambda v: f"{v:.0f}家",
         signal=_hb_wave_sig),
    dict(key="zt_fail_count", name="炸板家数", color="#f59e0b", fmt=lambda v: f"{v:.0f}家",
         signal=_zbfail_sig),
    dict(key="connect_2b", name="连板家数(≥2板)", color="#f59e0b", fmt=lambda v: f"{v:.0f}家",
         signal=_c2b_sig),
    dict(key="touch_down", name="倒跌停家数", color="#3b82f6", fmt=lambda v: f"{v:.0f}家",
         signal=_make_shep_sig("touch_down")),
    dict(key="fc_ratio", name="平均封成比", color="#16c2c2", fmt=lambda v: f"{v:.2f}",
         signal=_fc_sig),
    dict(key="real_limit_up", name="有效涨停(真实)", color="#ee2a2a", fmt=lambda v: f"{v:.0f}家",
         signal=_make_shep_sig("real_limit_up")),
    dict(key="avg_price", name="平均股价(观察)", color="#2b8aef", fmt=lambda v: f"{v:.2f}元",
         signal=_make_shep_sig("avg_price")),
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
    """构建牧羊人指标三行折线图（重计算，按数据+主题缓存）。

    第三行为复盘方法论新指标：中位数涨跌幅%（左轴）+ 回头波>10%家数 / 炸板家数（次轴）。
    """
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        specs=[[{}], [{}], [{"secondary_y": True}]],
        subplot_titles=("涨跌 / 涨停 / 跌停家数",
                        "昨日涨停表现(%) / 红盘占比(%)",
                        "中位数涨跌幅(%) ｜ 回头波>10%家数 / 炸板家数"),
        row_heights=[1, 1, 1],
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
    # ── 第三行：复盘方法论新指标（中位数% 左轴；回头波/炸板 次轴）──
    med = pd.to_numeric(d["median_chg"], errors="coerce") if "median_chg" in d.columns else None
    if med is not None and med.notna().any():
        is_pt = med.notna().sum() < 2
        tr = dict(x=d["date"], y=med.values, name="中位数涨跌幅%" + (" (今)" if is_pt else ""),
                  mode="markers" if is_pt else "lines",
                  line=dict(width=1.8, color="#ee2a2a"),
                  hovertemplate="%{x|%Y-%m-%d}<br>中位数涨跌幅：%{y:.2f}%<extra></extra>")
        if is_pt:
            tr["marker"] = dict(size=11, symbol="diamond", color="#ee2a2a")
        fig.add_trace(go.Scatter(**tr), row=3, col=1, secondary_y=False)
    for k, (col, name) in dict(hb_wave10=("#7c5cff", "回头波>10%家数"),
                               zt_fail_count=("#f59e0b", "炸板家数")).items():
        if k not in d.columns:
            continue
        s = pd.to_numeric(d[k], errors="coerce").dropna()
        if s.empty:
            continue
        is_pt = len(s) < 2
        tr = dict(x=d["date"], y=s.values, name=name + (" (今)" if is_pt else ""),
                  mode="markers" if is_pt else "lines",
                  line=dict(width=1.6, color=col, dash="dot" if k == "zt_fail_count" else None),
                  hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}：%{{y:.0f}} 家<extra></extra>")
        if is_pt:
            tr["marker"] = dict(size=11, symbol="diamond", color=col)
        fig.add_trace(go.Scatter(**tr), row=3, col=1, secondary_y=True)
    if "limit_up" in d.columns:
        fig.add_hline(y=50, line_dash="dot", line_color="#888", row=1, col=1,
                      annotation_text="涨停50(亢奋)", annotation_font_size=9)
    if "zt_prev_ret" in d.columns:
        fig.add_hline(y=0, line_dash="dot", line_color="#888", row=2, col=1)
        fig.add_hline(y=3, line_dash="dot", line_color="#888", row=2, col=1,
                      annotation_text="昨板3%(炸裂)", annotation_font_size=9)
    # 第三行参考线：中位数 0 轴 + 回头波 50 家 V反参考（次轴）
    if med is not None and med.notna().any():
        fig.add_hline(y=0, line_dash="dot", line_color="#888", row=3, col=1)
    if "hb_wave10" in d.columns:
        try:
            fig.add_hline(y=50, line_dash="dot", line_color="#7c5cff", row=3, col=1,
                          secondary_y=True, annotation_text="回头波50家(易V反)",
                          annotation_font_size=9)
        except Exception:  # noqa: BLE001  # 旧版 plotly 无 secondary_y 参数
            fig.add_hline(y=50, line_dash="dot", line_color="#7c5cff", row=3, col=1,
                          annotation_text="回头波50家(易V反)", annotation_font_size=9)
    theme = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6e6e6" if dark else "#1a1a1a"),
        xaxis=dict(gridcolor="#2a2a3a" if dark else "#ececec"),
        yaxis=dict(gridcolor="#2a2a3a" if dark else "#ececec"),
    )
    fig.update_layout(
        height=760, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center", font=dict(size=10)),
        margin=dict(l=55, r=25, t=60, b=40), hovermode="x unified", **theme)
    fig.update_xaxes(tickangle=-30)
    # 三行子图统一主题网格（yaxis/yaxis2 原有 + 第三行 yaxis5/yaxis6）
    fig.update_yaxes(gridcolor="#2a2a3a" if dark else "#ececec")
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
        xc_handle_error("牧羊人指标加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
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


@safe_fragment("牧羊人复盘方法论")
def fragment_shepherd_review():
    _section_title("📋 复盘方法论指标（视频《如何复盘非常重要》新增）", accent="#7c5cff")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=120000, limit=120, key="shep_rev_auto")
    try:
        with st.spinner("加载牧羊人指标…"):
            df, meta = _load_shepherd(60)
    except Exception as e:
        xc_handle_error("牧羊人指标加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
        return
    if df is None or df.empty:
        _empty_info("暂无牧羊人指标数据（网络/代理受限）。")
        return

    # 中位数涨跌加速（杨哥：上涨加速/下跌加速，数据出来会简化）
    try:
        if "median_chg" in df.columns:
            s = pd.to_numeric(df["median_chg"], errors="coerce").dropna()
            if len(s) >= 2:
                acc = float(s.iloc[-1] - s.iloc[-2])
                word = "上涨加速" if acc > 0.1 else ("下跌加速" if acc < -0.1 else "走平")
                st.caption(f"⚡ 中位数涨跌加速：{word}（今日 {s.iloc[-1]:+.2f}% vs 昨日 {s.iloc[-2]:+.2f}%，Δ {acc:+.2f}pct）")
    except Exception:  # noqa: BLE001
        pass

    # 新增指标卡（两行 × 4 列）
    for row_start in (0, 4):
        batch = _SHEPHERD_REVIEW[row_start:row_start + 4]
        cols = st.columns(len(batch))
        for c, cfg in zip(cols, batch):
            _card(c, cfg, df, dark)

    st.caption("🆕 以上指标源自杨哥复盘视频第二课：中位数=当日人均赚亏；回头波>10%=追高者回撤"
               "（≥30~50 家次日易V反）；炸板率=炸板/(涨停+炸板)（≥50% 次日易V反）；"
               "连板梯队=2板及以上家数（赚钱效应）；倒跌停=盘中触及跌停；封成比=封板资金/成交额。"
               "历史序列需重跑 v2 重构脚本后才有长周期值，当前近 60 日为实时回测。")

    # ── 最高板标的（视频：每天最高板代表市场情绪高度）──
    top = get_zt_top_board()
    if top:
        st.markdown(
            f"🏆 **今日最高板**：[{top['name']} ({top['code']})]({''}) {top['boards']} 板 · {top['industry']}"
            if False else
            f"🏆 **今日最高板**：{top['name']}（{top['code']}）{top['boards']} 板 · {top['industry']}"
        )
        st.caption("杨哥：把每天最高标的票列出来，它代表情绪——最高板往上走时容易赚钱，断板/回落时越来越难赚。")

    # ── 连板梯队全景（视频：梯队厚度决定赚钱效应能否扩散）──
    try:
        with st.spinner("加载连板梯队…"):
            lad = get_zt_ladder(top_per_level=3)
    except Exception:  # noqa: BLE001
        lad = None
    if lad and lad.get("levels"):
        # 落盘各档家数（供跨日晋级率递推；缺历史时后续晋级率优雅为 None）
        # ⚠️ 用**数据日期**而非 now()：周末/盘后打开页面时 now() 会记一个非交易日，
        #    跨日递推就会把周末当「昨日」，晋级率直接算错。
        try:
            _sl.record_ladder_snapshot(_last_data_date(df),
                                       lad.get("distribution"), lad.get("max_boards"), lad.get("total_connect"))
        except Exception:  # noqa: BLE001
            pass
        total = int(lad.get("total_connect") or 0)
        mx = int(lad.get("max_boards") or 0)
        # 梯队诊断：厚度 + 高度 + 断层
        if total >= 30 and mx >= 6:
            diag, dcolor = "梯队极厚 + 高度打开 → 主升确认，接力环境健康（注意盛极而衰）", "#ee2a2a"
        elif total >= 15:
            diag, dcolor = "梯队厚 → 赚钱效应线状扩散，接力顺畅", "#f59e0b"
        elif total >= 5:
            diag, dcolor = "梯队正常 → 有一定接力，但补涨梯队不够厚", "#3b82f6"
        else:
            diag, dcolor = "梯队断层 / 独苗行情 → 主线缺乏补涨，持续性差", "#00d486"
        # 断层检测：最高板往下到 2 板之间若有空档 = 接力资金缺席
        have = {int(l["boards"]) for l in lad["levels"]}
        gaps = [b for b in range(2, mx) if b not in have]
        if gaps:
            diag += f"；⚠️ **梯队断层**：{mx}板与2板之间缺 {'/'.join(str(g) + '板' for g in sorted(gaps, reverse=True))}，接力资金缺席"

        with st.container(border=True):
            st.markdown("**🪜 连板梯队全景**（最高板往下每一档的代表股，梯队厚度=赚钱效应能否扩散）")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("最高板", f"{mx} 板")
            with c2:
                st.metric("连板总家数(≥2板)", f"{total} 家")
            with c3:
                st.metric("梯队档位", f"{len(lad['levels'])} 档")
            st.markdown(
                f"<div style='border-left:3px solid {dcolor};padding-left:10px;"
                f"font-size:13px;color:{dcolor}'>{diag}</div>",
                unsafe_allow_html=True,
            )

            # 连板晋级率（跨日递推，需≥2日历史；比「家数」更细的接力信号）
            try:
                _pr = _sl.ladder_promotion_rates()
                # ⚠️ 用 overall 而非 rates["2b"]：2b 可能算不出（昨日缺首板档），
                #    此时 overall 已回落到可用档均值；直接格式化 None 会抛 TypeError
                #    并被下面的 except 吞掉，表现为「晋级率整块不显示」。
                if _pr.get("ready") and _pr.get("overall") is not None:
                    ov = float(_pr["overall"])
                    p2 = _pr["rates"].get("2b")
                    label = "首板→二板" if p2 is not None else "综合"
                    _pr_txt = (f"📈 **连板晋级率（{label}）{ov:.1f}%**　"
                               f"历史 {_pr['days']} 日"
                               "　· 晋级率越高=接力意愿越强，梯队越能自我维持")
                    st.markdown(
                        f"<div style='margin-top:6px;font-size:12px;opacity:.85'>{_pr_txt}</div>",
                        unsafe_allow_html=True,
                    )
            except Exception:  # noqa: BLE001
                pass

            # 逐档代表股（封单大的优先）
            for lv in lad["levels"]:
                bs, cnt = int(lv["boards"]), int(lv["count"])
                names = []
                for s in lv.get("stocks", []):
                    nm = s.get("name") or "—"
                    cd = str(s.get("code") or "")[-6:]
                    ind = s.get("industry") or ""
                    seal = float(s.get("seal") or 0)
                    seal_txt = f"封{seal / 1e8:.2f}亿" if seal > 0 else ""
                    names.append(f"`{nm}({cd})` {ind} {seal_txt}".strip())
                line = f"**{bs}板** · {cnt}家：　" + "｜".join(names) if names else f"**{bs}板** · {cnt}家"
                st.markdown(line)

            # 连板分布柱状图（含首板）
            dist = lad.get("distribution") or []
            if dist:
                dx = [str(b) for b, _ in dist]
                dy = [c for _, c in dist]
                fig = go.Figure(go.Bar(
                    x=dx, y=dy, marker_color="#ee2a2a", opacity=0.85,
                    hovertemplate="%{x}板：%{y} 家<extra></extra>",
                ))
                fig.update_layout(
                    height=230, margin=dict(l=10, r=10, t=28, b=10),
                    title="连板数分布（含首板）",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e6e6e6" if dark else "#1a1a1a", size=11),
                    xaxis=dict(title="连板数", gridcolor="#2a2a3a" if dark else "#ececec"),
                    yaxis=dict(title="家数", gridcolor="#2a2a3a" if dark else "#ececec"),
                )
                st.plotly_chart(fig, use_container_width=True,
                                config={"displaylogo": False, "responsive": True, "displayModeBar": False},
                                key="zt_ladder_bar")
            st.caption("杨哥：梯队「厚」= 赚钱效应线状扩散，接力顺畅；梯队「断层」= 接力资金缺席，"
                       "主线只是一只独苗。结合最高板高度判断情绪空间：高度打开 + 梯队厚 = 主升确认。")

    # ── 涨停板行业分布（视频第三表：每个涨停票炒什么板块都要了如指掌）──
    dist = get_zt_industry_distribution(8)
    if dist is not None and not dist.empty:
        fig = go.Figure(go.Bar(
            x=dist["涨停家数"], y=dist["行业"], orientation="h",
            marker_color="#ee2a2a", opacity=0.85,
            hovertemplate="%{y}：%{x} 家<extra></extra>",
        ))
        fig.update_layout(
            height=260, margin=dict(l=10, r=10, t=30, b=10),
            title="今日涨停行业分布 Top8（板块效应）",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6e6e6" if dark else "#1a1a1a", size=11),
            yaxis=dict(autorange="reversed", gridcolor="#2a2a3a" if dark else "#ececec"),
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displaylogo": False, "responsive": True, "displayModeBar": False}, key="zt_industry_bar")

    # ── 两融-指数背离（视频：两融增加+指数不创新高=警惕见顶）──
    try:
        with st.spinner("检查两融与指数背离…"):
            ddf, _ = _load_drivers(180)
        if ddf is not None and not ddf.empty and "margin_balance" in ddf.columns:
            mb = pd.to_numeric(ddf["margin_balance"], errors="coerce").dropna()
            if len(mb) >= 21:
                mb_delta = float(mb.iloc[-1] - mb.iloc[-21])
                idx_delta = None
                if "idx_ma20" in ddf.columns:
                    im = pd.to_numeric(ddf["idx_ma20"], errors="coerce").dropna()
                    if len(im) >= 21:
                        idx_delta = float(im.iloc[-1] - im.iloc[-21])
                txt = f"两融余额 {mb.iloc[-1]:,.0f} 亿，近20日 {mb_delta:+,.0f} 亿"
                if idx_delta is not None:
                    txt += f"；MA20 近20日 {idx_delta:+,.0f} 点"
                    if mb_delta > 0 and idx_delta < 0:
                        xc_warn_box(f"⚠️ 两融-指数顶背离（杨哥 7 月见顶信号）：{txt}。两融持续增加而指数不创新高，警惕见顶。")
                    else:
                        st.caption(f"💰 {txt} —— 暂无两融-指数背离。")
                else:
                    st.caption(f"💰 {txt}。")
    except Exception:  # noqa: BLE001
        pass


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
        xc_handle_error("牧羊人历史加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
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


def _last_data_date(df) -> str:
    """取牧羊人数据最后一行的交易日 'YYYY-MM-DD'；拿不到时退回今天。

    落盘类操作（连板梯队快照 / 情绪笔记）一律用它而不是 now()：
    周末、节假日、盘后打开页面时 now() 是个非交易日，会把「昨日」指到空档上，
    导致跨日晋级率、笔记回填全部错位。
    """
    try:
        return str(pd.to_datetime(df["date"].iloc[-1]).date())
    except Exception:  # noqa: BLE001
        return pd.Timestamp.now().strftime("%Y-%m-%d")


def _row_to_indicators(df, i=-1):
    """把牧羊人 DataFrame 的第 i 行转成指标 dict（供 forecast/note 用）。"""
    if df is None or df.empty:
        return {}
    try:
        row = df.iloc[i]
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for k in df.columns:
        if k == "date":
            continue
        try:
            v = float(row[k])
            if v == v:  # 过滤 NaN
                out[k] = v
        except Exception:  # noqa: BLE001
            continue
    return out


@safe_fragment("次日走势预判")
def fragment_shepherd_forecast():
    """「用今日指标判断明天大概怎么走」——周期定位 + 评分 + 方向 + 情景 + 联动信号。"""
    _section_title("🔮 次日走势预判（今日指标 → 明日大概率走向）", accent="#ee2a2a")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=180000, limit=80, key="shep_fc_auto")
    try:
        with st.spinner("加载牧羊人指标…"):
            df, meta = _load_shepherd(60)
    except Exception as e:
        xc_handle_error("牧羊人指标加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
        return
    if df is None or df.empty:
        _empty_info("暂无牧羊人指标数据（网络/代理受限）。")
        return

    today = _row_to_indicators(df, -1)
    prev = _row_to_indicators(df, -2) if len(df) >= 2 else None
    # 合并连板晋级率（来自每日梯队落盘的历史递推），作为更细的接力信号
    try:
        today.update(_sl.current_promo_as_indicators())
    except Exception:  # noqa: BLE001
        pass
    if not today:
        _empty_info("今日指标不足，无法预判。")
        return
    try:
        fc = _sf.forecast_next_day(today, prev)
    except Exception as e:  # noqa: BLE001
        xc_handle_error("次日预判计算失败", e, hint="请稍后重试")
        return

    cyc = fc.get("cycle") or {}
    bias = fc.get("bias", "中性")
    bcolor = {"偏多": "#ee2a2a", "偏空": "#00d486", "中性": "#f59e0b"}.get(bias, "#f59e0b")

    # ① 情绪周期定位 + 方向总览
    with st.container(border=True):
        st.markdown(
            f"### {cyc.get('emoji', '⚪')} 情绪周期：**{cyc.get('name', '—')}**　"
            f"<span style='color:{bcolor};font-size:22px'>{bias}</span>　"
            f"<span style='font-size:13px;opacity:.75'>置信度 {fc.get('confidence', 0)}%</span>",
            unsafe_allow_html=True,
        )
        if cyc.get("desc"):
            st.caption(cyc["desc"])
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("次日情绪评分", f"{fc.get('score', 0):.0f} / 100")
        with c2:
            st.metric("方向判断", bias)
        with c3:
            st.metric("置信度", f"{fc.get('confidence', 0)}%")
        for r in (cyc.get("reasons") or [])[:6]:
            st.markdown(f"- {r}")

    # ② 命中的指标联动规则（组合信号比单指标可靠）
    sigs = fc.get("signals") or []
    st.markdown("**🔗 今日命中的指标联动**")
    if not sigs:
        st.caption("今日未命中任何联动规则（信号较平淡，以单指标档位为准）。")
    else:
        for s in sigs:
            st.markdown(
                f"<div style='border-left:3px solid {s.get('color', '#888')};padding:6px 10px;"
                f"margin:6px 0;background:rgba(255,255,255,.03)'>"
                f"<b>{s.get('name')}</b>　<code>{s.get('logic', '')}</code><br>"
                f"<span style='font-size:12px;opacity:.85'>→ {s.get('effect', '')}</span></div>",
                unsafe_allow_html=True,
            )

    # ③ 三情景推演
    st.markdown("**🎲 次日三情景推演**")
    for sc in fc.get("scenario") or []:
        p = int(sc.get("prob", 0))
        st.markdown(
            f"<div style='margin:6px 0'>"
            f"<div style='display:flex;justify-content:space-between;font-size:13px'>"
            f"<span style='color:{sc.get('color', '#888')}'><b>{sc.get('name')}</b></span>"
            f"<span>{p}%</span></div>"
            f"<div style='background:rgba(255,255,255,.08);height:8px;border-radius:4px'>"
            f"<div style='width:{p}%;background:{sc.get('color', '#888')};height:8px;border-radius:4px'></div>"
            f"</div><div style='font-size:12px;opacity:.7;margin-top:2px'>{sc.get('desc', '')}"
            f"<br>　{sc.get('trigger', '')}</div></div>",
            unsafe_allow_html=True,
        )

    # ④ 各预测指标档位（哪些指标最能反映次日 + 当前落在哪一档）
    drivers = fc.get("drivers") or []
    if drivers:
        st.markdown("**📊 次日预测指标档位**（按权重排序，权重=对次日走向的影响强度）")
        rows = []
        for d in drivers:
            dir_txt = {1: "正向延续（今日越强→明日越易接力）",
                       -1: "反向修复（今日越惨→明日越易V反）",
                       0: "观察/确认项"}.get(d.get("dir"), "")
            unit = d.get("unit", "")
            try:
                val = f"{d['value']:.2f}{unit}" if isinstance(d["value"], float) else f"{d['value']}{unit}"
            except Exception:  # noqa: BLE001
                val = f"{d.get('value')}{unit}"
            rows.append({
                "指标": d.get("name"),
                "当前值": val,
                "档位": d.get("band", "—"),
                "权重": d.get("weight", 0),
                "与次日的关系": dir_txt,
                "当前档位含义": d.get("desc", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     column_config={"权重": st.column_config.NumberColumn(format="%d", width="small"),
                                    "当前档位含义": st.column_config.TextColumn(width="large")})
        with st.expander("📖 为什么这些指标能预示次日？（点击展开原理）"):
            for d in drivers:
                st.markdown(f"- **{d.get('name')}**（权重 {d.get('weight')}）：{d.get('why', '')}")
    st.caption(fc.get("summary", ""))
    st.caption("📚 口径来源：杨哥复盘视频方法论（V反/延续规律）+ 实盘复盘圈「盯四个数」"
               "（涨停÷跌停比 / 昨板溢价 / 空间板高度 / 梯队完整性，2026-08-29 资料交叉验证一致）。"
               "指标按「与次日走向的相关性强弱」加权，正向延续 / 反向修复 / 观察确认三类分开标注。")
    st.caption("⚠️ 预判基于历史统计规律与情绪周期框架，是概率而非确定性结论，不构成投资建议。")


@safe_fragment("情绪笔记")
def fragment_shepherd_note():
    """每天记录一次情绪 + 回填次日实际 + 对过去的情绪做回测分析。"""
    _section_title("📔 情绪笔记（每日情绪快照 + 历史情绪回测）", accent="#7c5cff")
    if _FOCUS_NOTE:   # 首页跳转过来时高亮一次，帮助定位
        st.markdown(
            "<div style='border:2px solid #7c5cff;border-radius:10px;padding:8px 12px;"
            "font-size:13px;margin-bottom:8px'>🎯 <b>就是这里</b> —— "
            "上方是「次日走势预判」，下方是「情绪笔记」与「历史情绪回测」。</div>",
            unsafe_allow_html=True,
        )
    try:
        with st.spinner("加载牧羊人指标…"):
            df, meta = _load_shepherd(60)
    except Exception as e:
        xc_handle_error("牧羊人指标加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
        return
    if df is None or df.empty:
        _empty_info("暂无牧羊人指标数据（网络/代理受限）。")
        return

    today = _row_to_indicators(df, -1)
    prev = _row_to_indicators(df, -2) if len(df) >= 2 else None
    # 合并连板晋级率（与预判片段保持一致，让快照里的预判也含晋级率信号）
    try:
        today.update(_sl.current_promo_as_indicators())
    except Exception:  # noqa: BLE001
        pass
    # 与梯队快照同口径：用数据日期，避免周末/盘后建出一条「非交易日」的空笔记
    dstr = _last_data_date(df)
    try:
        fc = _sf.forecast_next_day(today, prev) if today else None
    except Exception:  # noqa: BLE001
        fc = None

    # ── ① 今日情绪快照 ──
    with st.container(border=True):
        cyc = (fc or {}).get("cycle") or {}
        st.markdown(f"**📅 今日（{dstr or '—'}）情绪快照**　"
                    f"{cyc.get('emoji', '')} {cyc.get('name', '—')} ｜ "
                    f"评分 {(fc or {}).get('score', 0):.0f} ｜ 次日方向 **{(fc or {}).get('bias', '—')}**")
        note_txt = st.text_area("今日手记（可写盘面感受、主线、明日计划，留空则不改动已存手记）",
                                value="", key="shep_note_text", height=80,
                                placeholder="例：最高板断板，梯队只剩 2 家，明天先看能不能修复…")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("💾 保存/更新今日笔记", key="shep_note_save", use_container_width=True):
                ok = _sn.save_note(dstr or datetime.now().strftime("%Y-%m-%d"), today, fc, note_txt or "")
                if ok:
                    xc_success_box("✅ 今日情绪笔记已保存（含指标快照与次日预判）。")
                else:
                    xc_warn_box("⚠️ 保存失败，请检查 data/ 目录写权限。")
        with b2:
            if st.button("🔄 回填次日实际走势", key="shep_note_backfill", use_container_width=True):
                n = _sn.backfill_actuals(df)
                if n:
                    xc_success_box(f"✅ 已回填 {n} 条笔记的次日实际走势（用于验证预判准不准）。")
                else:
                    st.caption("没有需要回填的笔记（可能都已回填，或历史数据缺次日值）。")
        with b3:
            if st.button("🗑️ 删除今日笔记", key="shep_note_del", use_container_width=True):
                if _sn.delete_note(dstr):
                    xc_success_box("已删除今日笔记。")
                else:
                    st.caption("今日尚无笔记。")

    # ── ② 历史情绪回测（分析过去的情绪）──
    st.markdown("**🔬 历史情绪回测**（对过去每个交易日重跑情绪定位，统计「当时处于某阶段 → 次日实际怎么走」）")
    rng = st.selectbox("回测区间", ["近 60 交易日", "近 250 交易日", "近 1250 交易日"],
                       index=0, key="shep_note_range")
    days_map = {"近 60 交易日": 60, "近 250 交易日": 250, "近 1250 交易日": 1250}
    if st.button("📊 分析历史情绪（真机回测）", key="shep_note_analyze", use_container_width=True):
        try:
            with st.spinner("拉取真实区间数据并逐日重跑情绪定位…"):
                analysis, _meta = _sn.backtest_real(days_map[rng])
            if _meta and _meta.get("missing_columns"):
                st.caption("⚠️ 部分指标在所选区间缺失：" +
                           "；".join(f"{k}（{r}）" for k, r in _meta["missing_columns"].items()))
        except Exception as e:  # noqa: BLE001
            xc_handle_error("历史情绪分析失败", e, hint="请稍后重试")
            analysis = None
        if analysis is not None:
            st.session_state["shep_note_analysis"] = analysis
    analysis = st.session_state.get("shep_note_analysis")
    if analysis and analysis.get("rows"):
        acc = analysis.get("accuracy", {})
        rate = acc.get("rate")
        if rate is not None:
            st.metric("预判方向准确率", f"{rate:.1f}%",
                      help=f"有效样本 {acc.get('valid')} 日，命中 {acc.get('hit')} 次")
        else:
            st.caption("暂无可判定的次日样本（所选区间缺 zt_prev_ret，需更长历史或跑 v2 重构补齐）。")
        byc = analysis.get("by_cycle") or []
        if byc:
            rows = []
            for b in byc:
                rows.append({
                    "情绪阶段": f"{b.get('emoji', '')}{b.get('name')}",
                    "出现次数": b.get("count"),
                    "有效样本": b.get("valid"),
                    "次日打板溢价均值(%)": b.get("avg_next"),
                    "次日偏强胜率(%)": b.get("win_rate"),
                    "偏强/震荡/偏弱": f"{b.get('up')}/{b.get('flat')}/{b.get('down')}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            # 胜率柱状图
            fig = go.Figure(go.Bar(
                x=[f"{b.get('emoji', '')}{b.get('name')}" for b in byc],
                y=[b.get("win_rate") or 0 for b in byc],
                marker_color=[b.get("color", "#888") for b in byc], opacity=0.85,
                hovertemplate="%{x}：次日偏强 %{y:.1f}%<extra></extra>",
            ))
            fig.update_layout(
                height=260, margin=dict(l=10, r=10, t=28, b=10), title="各情绪阶段 → 次日偏强胜率(%)",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6e6e6" if dark else "#1a1a1a", size=11),
                yaxis=dict(gridcolor="#2a2a3a" if dark else "#ececec"),
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displaylogo": False, "responsive": True, "displayModeBar": False},
                            key="shep_note_winrate")
        st.caption(_sn.summary_of(analysis))
        st.caption("口径：次日走势以「次日打板赚钱效应 zt_prev_ret」为主（历史全期可得），"
                   "缺失时用次日涨停家数环比替代；命中=偏多→次日偏强 / 偏空→次日偏弱 / 中性→震荡。"
                   "样本越小越不稳定，结论仅供参考，不构成投资建议。")

    # ── ③ 历史笔记列表 ──
    notes = _sn.load_notes() or {}
    if notes:
        st.markdown(f"**🗂️ 已记录的情绪笔记（{len(notes)} 条）**")
        items = sorted(notes.items(), key=lambda kv: kv[0], reverse=True)[:20]
        rows = []
        for d, rec in items:
            f_ = rec.get("forecast") or {}
            a_ = rec.get("actual_next") or {}
            rows.append({
                "日期": d,
                "情绪阶段": f"{f_.get('cycle_emoji') or ''}{f_.get('cycle_name') or '—'}",
                "评分": f_.get("score"),
                "预判次日": f_.get("bias") or "—",
                "次日实际": a_.get("verdict") or "待回填",
                "次日溢价(%)": a_.get("zt_prev_ret"),
                "手记": (rec.get("user_note") or "")[:60],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     column_config={"手记": st.column_config.TextColumn(width="large")})
    else:
        st.caption("还没有笔记 —— 点上面「保存/更新今日笔记」开始记录，之后可回填次日实际走势验证预判。")


# 市场异动面板已抽取到 modules.session.fragment_market_alerts_panel（全局共享，风格统一）。

fragment_thermometer()
fragment_breadth()
fragment_sentiment()
fragment_valuation()
fragment_shepherd()
fragment_shepherd_review()
fragment_shepherd_forecast()
fragment_shepherd_note()
fragment_shepherd_chart()
fragment_market_alerts_panel()

st.caption("🌡️ 《市场广度 & 情绪温度计》：与《市场驱动力》（五维归一化子图）互补——"
           "本页用温度计卡 + 信号灯直观呈现「市场冷/热到什么程度」，"
           "指标口径同 21 指标参考表（ADL/ADR/新高新低/VIX/PCR/涨停占比/北向/融资/PE/股息率）。"
           "单源失败优雅降级，绝不抛红错。")
