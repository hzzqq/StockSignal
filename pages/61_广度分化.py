"""
页面 61：广度结构分化 · 日历热力 + 分化检测

把全市场广度从「内部结构」角度拆开看：
  · 广度日历热力图：按 年×月 聚合红盘率，看广度的季节/区间结构；
  · 结构分化检测：红盘率偏高（表面普涨）却伴随跌停数偏高（内部分化/杀跌），
    即典型的「涨多但杀跌」结构牛特征（如 2017、2021 核心资产牛市）。

数据边界（诚实声明，页面内可见）：离线基座只有全市场广度聚合序列，无行业分类、无指数序列，
故不做「行业广度热力」或「广度 vs 指数背离」，改为可落地的广度内部结构分化刻画。
"""
import logging

import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, section_header
from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules import breadth_divergence as bd

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="广度结构分化 · 日历热力 + 分化检测", icon="🧩",
    caption="从广度内部结构刻画市场分化：年×月红盘率日历热力图 + 「涨多但杀跌」结构分化检测。"
            "离线基座无行业/指数序列，故用广度内部结构（红盘率 vs 跌停）替代行业/指数维度。",
)

try:
    cal = bd.breadth_calendar()
    div = bd.divergence_episodes()

    # ── 当前分化状态卡 ──
    st.markdown("### 🔎 当前广度结构")
    if div.get("available") and div.get("current"):
        cur = div["current"]
        if cur["is_divergent"]:
            st.markdown(sf_card(
                title=f"⚠️ 结构分化（{cur['date']}）",
                body=f"红盘率 <b>{cur['red_ratio']}%</b>（表面不弱）但跌停 <b>{cur['limit_down']}</b> 家"
                     f"（跌停占比 <b>{cur['limit_down_ratio']}%</b>，处历史高位）→ "
                     f"<b style='color:{DOWN_COLOR}'>涨多但杀跌，广度内部结构分化</b>。",
                accent=DOWN_COLOR,
            ), unsafe_allow_html=True)
        else:
            st.markdown(sf_card(
                title=f"结构均衡（{cur['date']}）",
                body=f"红盘率 <b>{cur['red_ratio']}%</b> ｜ 跌停 <b>{cur['limit_down']}</b> 家"
                     f"（跌停占比 <b>{cur['limit_down_ratio']}%</b>，未触历史高位）→ 广度内部结构未见明显分化。",
                accent="#36c5d8",
            ), unsafe_allow_html=True)
        st.caption(
            f"判定阈值：红盘率 ≥ {div['threshold_red']}% 且 跌停占比 ≥ 历史 {int(0.90*100)} 分位"
            f"（p90={'-' if div['ld_p90'] is None else f'{div['ld_p90']:.2f}%'}）。历史共 {div['n_episodes']} 个分化日。"
        )
    else:
        st.warning("⚠️ 广度历史不可用，无法计算分化状态。")

    # ── 日历热力图 ──
    st.markdown("### 🗓️ 广度日历热力图（年×月 平均红盘率 %）")
    if cal.get("available") and cal["z"]:
        z = cal["z"]
        years = cal["years"]
        months = cal["months"]
        fig = go.Figure(go.Heatmap(
            z=z, x=[f"{m}月" for m in months], y=[str(y) for y in years],
            colorscale=[[0, "#1d4ed8"], [0.4, "#0891b2"], [0.5, "#ca8a04"],
                        [0.6, "#ea580c"], [1, "#b91c1c"]],
            zmin=0, zmax=100, hoverongaps=False,
            colorbar=dict(title="红盘率%"),
        ))
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=max(360, 36 * len(years)), margin=dict(l=50, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("蓝=冰点（普跌） → 红=狂热（普涨）。可读出广度牛熊区间结构（如 2015 上半年的极端红、2018 的全年冷）。")
    else:
        st.info("暂无足够广度历史生成日历热力图。")

    # ── 历史分化日列表 ──
    st.markdown("### 📜 历史「涨多但杀跌」分化日（节选最近 15 个）")
    if div.get("available") and div["episodes"]:
        import pandas as pd
        ep = div["episodes"][-15:]
        df = pd.DataFrame(ep)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("无分化日记录。")

    # ── 方法学声明 ──
    st.markdown("---")
    st.caption(
        "📐 方法学：本页只用牧羊人广度聚合序列（red_ratio / 涨跌家数 / 涨跌停）。因离线基座无行业分类、无指数序列，"
        "无法做「行业广度热力」或「广度 vs 指数背离」，故改用广度**内部结构**刻画分化：日历热力展示广度的区间结构；"
        "分化检测标记「红盘率偏高且跌停占比处历史高位」的「涨多但杀跌」日，对应结构牛中「少数权重涨、广度冷/杀跌」的特征。"
        "所有判定基于广度内部可观测变量，不引入任何外部或编造数据。"
    )

except Exception as exc:  # noqa: BLE001
    logger.exception("广度分化页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
