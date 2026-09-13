"""
页面 69：温度持续期与回归时长（方案⑩）

以「红盘占比」五档（冰点/偏冷/中性/活跃/狂热）作为温度代理，统计每段同档连续 run 的时长分布，
并重点统计「冰点」run 到首次回到 ≥中性 的中位天数（磨底时长）。历史统计描述，非预测。

数据边界：仅用 shepherd_history 内部可观测的 red_ratio，无指数/行业/资金流/逐股，不编造。
"""
import logging

import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card
from modules import regime_duration as rd

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="温度持续期与回归时长", icon="📚",
    caption="红盘占比五档的持续期分布 + 冰点回归中性的中位磨底时长。历史统计描述，非预测。"
            "温度代理=红盘占比五档，变量来自 shepherd_history 内部。",
)

try:
    res = rd.regime_duration()
    if res.get("available"):
        st.markdown("### ⏳ 各温度档持续期（中位天数）")
        bands = res["band_labels"]
        meds = [res["durations"][b]["median"] for b in range(5)]
        ns = [res["durations"][b]["n"] for b in range(5)]

        fig = go.Figure(go.Bar(
            x=bands, y=[m if m is not None else 0 for m in meds],
            text=[f"{m}天 (n={n})" if m is not None else "n=0" for m, n in zip(meds, ns)],
            textposition="auto",
            marker_color=["#3b82f6", "#06b6d4", "#22c55e", "#f59e0b", "#ef4444"],
        ))
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white", height=340,
            margin=dict(l=40, r=20, t=20, b=40),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            xaxis_title="温度档", yaxis_title="中位持续天数",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("每根柱=该温度档历史连续 run 的中位天数；样本数 n 标于柱上。仅描述历史停留时长，不预测未来。")

        # 明细表
        st.markdown("### 📊 持续期明细")
        for b in range(5):
            s = res["durations"][b]
            st.markdown(f"- **{bands[b]}**：run 数 <b>{s['n']}</b> ｜ 均值 <b>{s['mean']}</b> 天 ｜ 中位 <b>{s['median']}</b> 天", unsafe_allow_html=True)

        rec = res["recovery"]
        st.markdown("### 🧊 冰点 → 回归中性 磨底时长")
        if rec.get("n"):
            st.markdown(sf_card(
                title="冰点后中位磨底时长",
                body=f"中位 <b>{rec['median']}</b> 天 ｜ 均值 <b>{rec['mean']}</b> 天 ｜ 样本 <b>{rec['n']}</b> 段",
                accent="#ea580c",
            ), unsafe_allow_html=True)
            st.caption("统计自每段「冰点」run 结束到首个 ≥中性 交易日的间隔天数；描述历史磨底节奏，非预测。")
        else:
            st.info("历史中无完整「冰点→回归中性」样本可供统计。")
    else:
        st.warning("⚠️ 无法计算温度持续期（红盘占比历史缺失）。")

    st.markdown("---")
    st.caption(
        "📐 方法学：本页以红盘占比五档作为温度代理，对每日标档后统计连续同档 run 的时长分布，"
        "并测算冰点 run 到首次回到 ≥中性 的中位天数。全部基于 shepherd_history 内部 red_ratio，"
        "不引入指数/行业/资金流等编造数据；结果为历史统计描述，不构成预测或买卖建议。"
    )
except Exception as exc:  # noqa: BLE001
    logger.exception("温度持续期页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
