"""
页面 56：市场状态机 + 历史情境类比

把 P0–P3 修复的 4771 天广度真值（data/shepherd_history.json）变现为两个高亮点能力：
  · 市场状态机：规则可解释的 5 档分类（暴跌/恐慌/震荡/结构牛/普涨）+ 状态转移矩阵；
  · 历史情境类比：对「今天」的广度向量，在全历史找最近的 k 个相似交易日，
    统计其后 5/10/20 日的市场表现（红盘率均值、上涨日占比、红盘率中位变化）。

全部离线、零网络；类比只回看过去（无前视泄漏），明确标注「历史相似，不代表未来」。
数据口径同《市场情绪》《今日决策面板》，单源失败优雅降级，绝不抛红错。
"""
import logging

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, section_header
from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules import market_regime as mr

logger = logging.getLogger(__name__)

# 状态→信号灯独立配色（风险/健康语义，与涨跌色解耦，符合项目红线）
STATE_COLORS = {
    "暴跌": "#dc2626",
    "恐慌": "#f97316",
    "震荡": "#f59e0b",
    "结构牛": "#22c55e",
    "普涨": "#16a34a",
}

dark = render_standard_page(
    title="市场状态机 · 历史情境类比", icon="🧭",
    caption="用 4771 天广度真值训出可解释的五档市场状态机 + 转移矩阵，并对今日做历史相似日回看。"
            "离线、零前视泄漏；历史相似≠预测。",
)

# ── 数据（缓存，避免每次重算）──
@st.cache_data(show_spinner="正在加载广度历史…", ttl=3600)
def _load_report(k: int):
    return mr.regime_report(k=k)


def _state_color(state: str) -> str:
    return STATE_COLORS.get(state, "#94a3b8")


try:
    k = int(st.sidebar.slider("类比相似日数量", 3, 15, 8, 1))
    rep = _load_report(k)

    if not rep.get("available"):
        st.error(f"状态机不可用：{rep.get('reason', '未知原因')}")
        st.stop()

    latest = rep["latest"]
    sc = _state_color(latest["state"])

    # 数据新鲜度诚实提示（最新真值日可能早于今天）
    st.info(
        f"📅 数据区间 {rep['data']['start']} ~ {rep['data']['end']}"
        f"（共 {rep['data']['rows']} 个交易日）；状态判定基于最新真值日 **{latest['date']}**。"
    )

    # ── 当前状态卡 ──
    st.markdown(
        f"""
        <div style="border-left:6px solid {sc};background:{_hex_to_rgba(sc, 0.12)};
        border-radius:10px;padding:14px 18px;margin-bottom:10px">
          <div style="font-size:13px;opacity:.7">最新市场状态</div>
          <div style="font-size:30px;font-weight:800;color:{sc}">{latest['state']}</div>
          <div style="font-size:12px;opacity:.75">状态置信度 {latest['confidence']*100:.0f}%
          · 红盘率 {latest['metrics']['red_ratio']}% · 涨停 {latest['metrics']['limit_up']} · 跌停 {latest['metrics']['limit_down']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 状态分布 + 转移矩阵 ──
    c1, c2 = st.columns([1, 1.4])
    with c1:
        section_header("全历史状态分布", "2007 年至今各状态出现天数", icon="📊")
        dist = rep["state_distribution"]
        fig_d = go.Figure(go.Bar(
            x=[s for s in mr.STATE_ORDER],
            y=[dist[s] for s in mr.STATE_ORDER],
            marker_color=[_state_color(s) for s in mr.STATE_ORDER],
        ))
        fig_d.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=300, margin=dict(l=30, r=10, t=10, b=30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
        )
        st.plotly_chart(fig_d, use_container_width=True)

    with c2:
        section_header("状态转移矩阵", "行=今日状态，列=次日状态（概率）", icon="🔀")
        mat = rep["transition_matrix"]
        z = [[mat[a][b] for b in mr.STATE_ORDER] for a in mr.STATE_ORDER]
        fig_m = go.Figure(go.Heatmap(
            z=z, x=mr.STATE_ORDER, y=mr.STATE_ORDER,
            colorscale="Blues", zmin=0, zmax=1,
            text=[[f"{mat[a][b]*100:.0f}%" for b in mr.STATE_ORDER] for a in mr.STATE_ORDER],
            texttemplate="%{text}", showscale=False,
        ))
        fig_m.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=300, margin=dict(l=60, r=10, t=10, b=30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_m, use_container_width=True)

    # ── 历史情境类比 ──
    section_header("历史情境类比", f"与 {latest['date']} 广度最相似的 {len(rep['analogs'])} 个交易日，及其后表现", icon="🕰️")
    st.caption("⚠️ 历史相似 ≠ 预测。下表为相似日之后 5/10/20 个交易日的真实市场表现统计，仅供情境参照。")

    cols = st.columns(min(len(rep["analogs"]), 4))
    for idx, a in enumerate(rep["analogs"]):
        col = cols[idx % 4]
        with col:
            ac = _state_color(a["state"])
            f5 = a["forward"].get("d5", {})
            f10 = a["forward"].get("d10", {})
            f20 = a["forward"].get("d20", {})
            up5 = f5.get("up_frac")
            up5_color = UP_COLOR if (up5 is not None and up5 > 0.5) else DOWN_COLOR
            st.markdown(
                f"""
                <div style="border:1px solid {_hex_to_rgba(ac,0.5)};border-left:4px solid {ac};
                border-radius:8px;padding:10px 12px;margin-bottom:8px;font-size:12px">
                  <div style="font-weight:700;color:{ac}">{a['date']}</div>
                  <div style="opacity:.7">相似度距离 {a['distance']:.3f} · 状态 {a['state']}</div>
                  <div style="margin-top:4px">后5日 红盘率均值 <b>{f5.get('avg_red','—')}</b></div>
                  <div>后5日 上涨日占比 <b style="color:{up5_color}">{up5 if up5 is None else f'{up5*100:.0f}%'}</b></div>
                  <div style="opacity:.7">后10日红盘均值 {f10.get('avg_red','—')} · 后20日 {f20.get('avg_red','—')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    sf_card(
        "方法学与诚实声明",
        "状态机为规则可解释的五档分类（阈值由全样本分位定），非黑箱模型；历史类比仅回看目标日之前的交易日"
        "（无前视泄漏），用欧氏距离在 z-score 标准化后的 [红盘率, 涨停, 跌停] 向量上检索最近邻。"
        "所有结论基于已修复的 4771 天广度真值，未使用任何缺失字段（zt_fail_ratio/zt_prev_ret 在历史上多为 NaN，已弃用）。",
        icon="📐",
    )

except Exception as e:  # noqa: BLE001
    logger.exception("[56_市场状态机] 渲染失败")
    st.error(f"页面渲染失败：{e}")
