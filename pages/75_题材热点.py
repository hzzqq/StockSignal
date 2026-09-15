"""页面 75：题材热点追踪（G7）

对标钱来终端的题材视角：**Squarified treemap 热力图**（面积=板块总市值，颜色=涨跌幅，
A 股红涨绿跌）+ 题材**生命周期**（发酵 / 高潮 / 退潮 / 平淡）。

差异化：不只看「哪个题材涨」，还把题材按热度分位打上生命周期标签，帮判断「是启动、
是高潮、还是在退潮」，并与领涨股联动。

数据源：东财概念板块实时快照（akshare ``stock_board_concept_name_em``，缓存 120s）。

诚实性红线：
  · 生命周期为**启发式分类**（涨跌幅 + 换手率分位），非预测；退潮/高潮为事后描述；
  · 取不到快照时明示「未就绪」，不用陈旧数据假装实时。
"""
from __future__ import annotations

import logging

import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.theme_heat import LIFECYCLE_ORDER, col_of, load_concepts
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)

# A 股红涨绿跌配色（负=绿，0=灰，正=红）
_LIFE_COLOR = {"高潮": "#dc2626", "发酵": "#f97316", "退潮": "#16a34a", "平淡": "#64748b", "未知": "#94a3b8"}


dark = render_standard_page(
    title="题材热点追踪", icon="🧱",
    caption="概念板块 treemap 热力图（面积=总市值，颜色=涨跌幅，红涨绿跌）+ 生命周期"
            "（发酵/高潮/退潮/平淡）。启发式分类，非预测。数据源东财概念板块快照。",
)

try:
    df = load_concepts()
except Exception as e:  # noqa: BLE001
    logger.warning(f"[theme-heat] 概念快照获取失败: {e}")
    st.error("⚠️ 概念板块数据获取失败（网络不可用或接口异常），请稍后重试。")
    st.stop()

if df is None or df.empty:
    st.info("📭 概念板块快照未就绪（可能非交易时段或接口暂不可用）。")
    st.stop()

name_c = col_of(df, "name")
if not name_c:
    st.info("📭 数据源缺少板块名称字段，无法绘制热力图。")
    st.stop()

chg = df["_chg"]
n_up = int((chg > 0).sum())
n_down = int((chg < 0).sum())
top_name = str(df.loc[chg.idxmax(), name_c]) if len(df) else "—"
top_chg = float(chg.max()) if len(df) else 0.0

# ── ① KPI ──────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    sf_metric("概念板块数", str(len(df)), "东财概念")
with c2:
    sf_metric("上涨板块", str(n_up), "红盘")
with c3:
    sf_metric("下跌板块", str(n_down), "绿盘")
with c4:
    sf_metric("领涨题材", top_name, f"{top_chg:+.2f}%")

st.markdown("---")

# ── ② treemap 热力图 ──────────────────────────────────────────────────
section_header("题材热力图", "方块面积=板块总市值，颜色=涨跌幅（红涨绿跌）", icon="🗺️")
mv_c = col_of(df, "mv")
vals = df[mv_c] if mv_c else (chg.abs() + 1.0)
mx = max(abs(float(chg.min() or 0)), abs(float(chg.max() or 0)), 1.0)
fig_tm = go.Figure(go.Treemap(
    labels=df[name_c].astype(str).tolist(),
    parents=[""] * len(df),
    values=(vals.fillna(0) if hasattr(vals, "fillna") else vals),
    marker=dict(
        colors=chg, cmin=-mx, cmax=mx, cmid=0, showscale=True,
        colorscale=[[0.0, "#16a34a"], [0.5, "#94a3b8"], [1.0, "#dc2626"]],
        colorbar=dict(title="涨跌幅%"),
    ),
    text=[f"{v:+.1f}%" for v in chg],
    textinfo="label+text",
    hovertemplate="%{label}<br>涨跌幅 %{text}<extra></extra>",
))
fig_tm.update_layout(template="plotly_dark" if dark else "plotly_white",
                     height=520, margin=dict(l=10, r=10, t=20, b=10))
st.plotly_chart(fig_tm, width="stretch")

st.markdown("---")

# ── ③ 生命周期分布 + 明细 ─────────────────────────────────────────────
cc1, cc2 = st.columns([2, 3])
with cc1:
    section_header("生命周期分布", "按涨跌幅+换手分位启发式分类", icon="🔄")
    life = df["_life"].value_counts()
    order = [x for x in LIFECYCLE_ORDER if life.get(x, 0) > 0]
    fig_life = go.Figure(go.Bar(
        x=[life.get(x, 0) for x in order], y=order, orientation="h",
        marker_color=[_LIFE_COLOR.get(x, "#94a3b8") for x in order],
        text=[life.get(x, 0) for x in order], textposition="outside",
    ))
    fig_life.update_layout(template="plotly_dark" if dark else "plotly_white",
                          height=300, margin=dict(l=10, r=10, t=20, b=10),
                          xaxis_title="板块数", showlegend=False)
    st.plotly_chart(fig_life, width="stretch")

with cc2:
    section_header("热度榜（涨幅 Top 20）", "含生命周期标签与领涨股", icon="🏆")
    leader_c = col_of(df, "leader")
    top = df.sort_values("_chg", ascending=False).head(20)
    rows = ""
    for _, r in top.iterrows():
        nm = str(r.get(name_c, ""))
        ch = float(r["_chg"])
        lf = str(r.get("_life", ""))
        lead = str(r.get(leader_c, "")) if leader_c else ""
        rows += (
            "<div style='display:flex;justify-content:space-between;padding:5px 0;"
            "border-bottom:1px solid rgba(148,163,184,.15);font-size:13px'>"
            f"<span>{nm} <span style='opacity:.55;font-size:11px'>{lead}</span></span>"
            "<span>"
            f"<span style='color:{_LIFE_COLOR.get(lf, '#94a3b8')};font-size:11px;margin-right:8px'>{lf}</span>"
            f"<b style='color:{'#dc2626' if ch >= 0 else '#16a34a'}'>{ch:+.2f}%</b></span></div>"
        )
    st.markdown(rows, unsafe_allow_html=True)

st.caption("⚠️ 说明：生命周期为启发式分类（涨跌幅 + 换手率分位），是对**当下状态**的描述，"
           "非预测；「高潮」不代表继续，「退潮」不代表必然反弹。不构成投资建议。")
