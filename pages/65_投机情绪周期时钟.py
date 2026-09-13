"""
页面 65：投机情绪周期时钟（方案⑥）

把涨停梯队质量（连板高度 / 连板家数 / 炸板率 / 昨日涨停表现 / 平均封成比）做成时间序列，
识别「梯队厚→断层→退潮→冰点→重启」的投机情绪周期。纯离线、描述性，不预测。

数据边界：仅用 shepherd_history 内部广度维度，无指数/行业/资金流/逐股，不编造。
"""
import logging

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card
from modules import speculative_clock as sc

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="投机情绪周期时钟", icon="🗞️",
    caption="涨停梯队质量（连板高度/连板家数/炸板率/昨日涨停表现/平均封成比）时序，识别投机情绪周期。"
            "纯离线、描述性框架，不预测收益。维度均来自 shepherd_history 内部广度变量。",
)

try:
    _win = st.sidebar.selectbox(
        "时间窗口", options=[60, 120, 250, 750, 2000], index=2,
        format_func=lambda x: f"近 {x} 日",
    )
    res = sc.speculative_sentiment_series(window=_win)
    cur = sc.current_phase()

    # ── 当前相位 ──
    st.markdown("### 🧭 当前投机情绪相位")
    if cur.get("available"):
        st.markdown(sf_card(
            title=f"当前（{cur['date']}）· {cur['phase']}",
            body=f"连板高度 <b>{cur['connect_hl']}</b> ｜ 连板家数(≥2板) <b>{cur['connect_2b']}</b> ｜ "
                 f"炸板率 <b>{cur['zt_fail_ratio']}%</b> ｜ 昨日涨停表现 <b>{cur['zt_prev_ret']}</b> ｜ "
                 f"平均封成比 <b>{cur['fc_ratio']}</b><br><span style='color:#8c8c8c'>{cur['reason']}</span>",
            accent="#36c5d8",
        ), unsafe_allow_html=True)
    else:
        st.warning("⚠️ 无法读取当前广度状态。")

    # ── 时序图（各序列按自身 min/max 归一化叠加）──
    st.markdown("### 📈 梯队质量时序（归一化叠加）")
    if res.get("available") and res.get("dates"):
        s = res["series"]
        cols = list(s.keys())
        fig = go.Figure()
        palette = ["#36c5d8", "#ea580c", "#a855f7", "#22c55e", "#eab308"]
        for idx, c in enumerate(cols):
            vals = [v for v in s[c]]
            arr = np.array([np.nan if v is None else v for v in vals], dtype=float)
            if np.nanmax(arr) == np.nanmin(arr):
                norm = arr - np.nanmin(arr)
            else:
                norm = (arr - np.nanmin(arr)) / (np.nanmax(arr) - np.nanmin(arr))
            fig.add_trace(go.Scatter(
                x=res["dates"], y=norm, name=res["labels"][c], mode="lines",
                line=dict(width=1.6, color=palette[idx % len(palette)]),
            ))
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=420, margin=dict(l=40, r=20, t=20, b=60),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            xaxis_title="日期", yaxis_title="归一化(各自 min–max)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("各线按自身区间归一化以便叠加对比走势；橙线=炸板率（越高越分歧）、紫线=连板高度（越高越亢奋）。"
                   "仅描述历史周期，不构成方向预测。")
    else:
        st.info("暂无足够梯队质量历史生成时序图。")

    st.markdown("---")
    st.caption(
        "📐 方法学：本页用牧羊人广度聚合序列中的涨停梯队质量维度（连板高度/连板家数/炸板率/昨日涨停表现/平均封成比），"
        "全部为离线可得变量。相位判定为极简规则（亢奋/退潮/梯队断层/冰点/中性），用于描述投机情绪所处阶段，"
        "不预测收益、不引入编造数据。"
    )
except Exception as exc:  # noqa: BLE001
    logger.exception("投机情绪周期时钟页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
