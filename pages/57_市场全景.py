"""
页面 57：市场全景一页纸（指挥台）

把分散在《市场情绪》《今日决策面板》《市场状态机》的核心读数聚合到一个屏，
作为演示 / 答辩的入口：市场温度、当前状态、广度快照、历史类比速览。
全部复用既有 modules 函数（shepherd / decision / market_regime），不重复计算逻辑。
单源失败优雅降级，绝不抛红错。
"""
import logging

import streamlit as st
import pandas as pd

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric, section_header
from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules import market_regime as mr
from modules.shepherd import get_shepherd_indicators, shepherd_temperature

logger = logging.getLogger(__name__)

STATE_COLORS = {
    "暴跌": "#dc2626", "恐慌": "#f97316", "震荡": "#f59e0b",
    "结构牛": "#22c55e", "普涨": "#16a34a",
}

dark = render_standard_page(
    title="市场全景 · 一页纸指挥台", icon="🛰️",
    caption="把市场温度、当前状态、广度快照、历史类比速览聚到一个屏，作为演示/答辩入口。复用既有模块，不重复计算。",
)


def _safe(v, nd=2, na="N/A"):
    if v is None or (isinstance(v, float) and v != v):
        return na
    return f"{v:.{nd}f}"


try:
    # ── 数据 ──
    df, meta = get_shepherd_indicators(days=60)
    regime = mr.regime_report(k=8)

    if df is None or df.empty:
        st.error("牧羊人广度历史暂不可用（网络受限），全景无法渲染。")
        st.stop()

    latest = df.iloc[-1]
    today_dict = {k: float(latest[k]) for k in
                  ["red_ratio", "limit_up", "limit_down", "connect_hl",
                   "zt_fail_ratio", "zt_prev_ret", "hb_wave10"]
                  if k in latest and pd.notna(latest[k])}
    temp = shepherd_temperature(today_dict, hist_days=2000)

    st.info(f"📅 广度快照最新日 **{pd.to_datetime(latest['date']).strftime('%Y-%m-%d')}**"
            f" · 状态判定最新真值日 **{regime['latest']['date']}**（数据区间 {regime['data']['start']}~{regime['data']['end']}）")

    # ── 顶部指标卡 ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sf_metric("市场温度", f"{temp:.0f}", "0-100")
    with c2:
        sc = STATE_COLORS.get(regime["latest"]["state"], "#94a3b8")
        sf_metric("市场状态", regime["latest"]["state"], f"置信度 {regime['latest']['confidence']*100:.0f}%")
    with c3:
        rr = float(latest.get("red_ratio", float("nan")))
        rr_color = UP_COLOR if rr >= 50 else DOWN_COLOR
        sf_metric("红盘率", _safe(rr, 1) + "%", "涨/跌家数比")
    with c4:
        lu = int(latest.get("limit_up", 0) or 0)
        ld = int(latest.get("limit_down", 0) or 0)
        sf_metric("涨停 / 跌停", f"{lu} / {ld}", "家数")

    # ── 广度快照 + 状态机速览 ──
    st.markdown("---")
    cL, cR = st.columns([1, 1])
    with cL:
        section_header("广度快照", "最新交易日核心指标", icon="📡")
        snap = {"红盘率(%)": latest.get("red_ratio"), "涨停家数": latest.get("limit_up"),
                "跌停家数": latest.get("limit_down"), "连板高度": latest.get("connect_hl"),
                "炸板率(%)": latest.get("zt_fail_ratio")}
        for k, v in snap.items():
            st.markdown(f"- **{k}**：{_safe(v, 1)}")
        if meta and meta.get("unavailable"):
            st.caption("⚠️ 部分字段数据源缺失：" + ", ".join(str(x[0]) for x in meta["unavailable"][:3]))
    with cR:
        section_header("市场状态机速览", "五档状态 + 全历史分布", icon="🧭")
        dist = regime["state_distribution"]
        for s in mr.STATE_ORDER:
            n = dist[s]
            pct = n / regime["data"]["rows"] * 100
            col = STATE_COLORS.get(s, "#94a3b8")
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;margin:3px 0'>"
                f"<span style='width:54px;color:{col};font-weight:700'>{s}</span>"
                f"<span style='flex:1;height:10px;background:{_hex_to_rgba(col,0.25)};"
                f"border-radius:5px;position:relative'>"
                f"<span style='position:absolute;left:0;top:0;height:100%;width:{pct:.1f}%;"
                f"background:{col};border-radius:5px'></span></span>"
                f"<span style='width:70px;text-align:right;font-size:12px'>{n} 天 ({pct:.1f}%)</span></div>",
                unsafe_allow_html=True,
            )

    # ── 历史类比速览 ──
    st.markdown("---")
    section_header("历史情境类比速览", f"与 {regime['latest']['date']} 最相似的 {len(regime['analogs'])} 个交易日", icon="🕰️")
    cols = st.columns(min(len(regime["analogs"]), 4))
    for idx, a in enumerate(regime["analogs"][:4]):
        col = cols[idx % 4]
        with col:
            ac = STATE_COLORS.get(a["state"], "#94a3b8")
            f5 = a["forward"].get("d5", {})
            up5 = f5.get("up_frac")
            upc = UP_COLOR if (up5 is not None and up5 > 0.5) else DOWN_COLOR
            st.markdown(
                f"<div style='border-left:4px solid {ac};border-radius:8px;padding:8px 10px;"
                f"background:{_hex_to_rgba(ac,0.10)};font-size:12px'>"
                f"<div style='font-weight:700;color:{ac}'>{a['date']}</div>"
                f"<div style='opacity:.7'>状态 {a['state']} · 距离 {a['distance']:.3f}</div>"
                f"<div>后5日 红盘率均值 <b>{f5.get('avg_red','—')}</b></div>"
                f"<div>后5日 上涨日占比 <b style='color:{upc}'>"
                f"{up5 if up5 is None else f'{up5*100:.0f}%'}</b></div></div>",
                unsafe_allow_html=True,
            )

    # ── 跳转入口 ──
    st.markdown("---")
    section_header("深入各模块", "点击进入完整功能页", icon="🔗")
    st.page_link("pages/50_市场情绪.py", label="🌡️ 市场情绪 · 广度与情绪温度计", icon="📊")
    st.page_link("pages/54_今日决策面板.py", label="🎯 今日决策面板", icon="📊")
    st.page_link("pages/56_市场状态机.py", label="🧭 市场状态机 · 历史情境类比", icon="📊")

    sf_card(
        "诚实声明",
        "本页所有读数均来自已修复的牧羊人广度历史（4771 天真值）；温度由近期历史分位映射，"
        "状态机与类比见《市场状态机》页的方法学说明。历史相似 ≠ 预测。",
        icon="📐",
    )

except Exception as e:  # noqa: BLE001
    logger.exception("[57_市场全景] 渲染失败")
    st.error(f"页面渲染失败：{e}")
