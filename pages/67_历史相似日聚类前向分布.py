"""
页面 67：历史相似日聚类 + 前向分布（方案⑧）

取最新一日的真实广度向量，在全历史按欧氏距离找最相似 top-N 日（排除末日 ±15 交易日防前视泄漏），
统计这些相似日后继 5/10/20 交易日的红盘占比分布。这是**历史类比**，非预测。

数据边界：连板梯队类维度离线缺真值，已通过数据闸门剔除，不进入距离计算、不编造。
"""
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card
from modules import similar_day_cluster as sdc
from modules.breadth_features import OFFLINE_MISSING, data_as_of

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="历史相似日聚类 · 前向分布", icon="📰",
    caption="最新一日真实广度向量在全历史找最相似 top-N 日，统计其后继 5/10/20 日红盘占比分布。"
            "历史类比，非预测。",
)
st.caption(f"📅 数据截至 **{data_as_of()}**（离线健康镜像快照，**非实时行情**）")

try:
    res = sdc.similar_day_cluster()
    if res.get("available"):
        st.markdown(f"### 🎯 历史相似日（目标日 {res['target_date']}，排除末 ±{res['exclude_window']} 日防前视泄漏）")
        fs = res["forward_stats"]
        cols = st.columns(3)
        for i, off in enumerate([5, 10, 20]):
            s = fs.get(off, {})
            if s.get("n"):
                cols[i].markdown(sf_card(
                    title=f"后 {off} 日红盘占比",
                    body=f"均值 <b>{s['mean']}%</b> ｜ 中位 <b>{s['median']}%</b><br>"
                         f"红盘占比(≥50) <b>{s['up_ratio']}%</b> ｜ 样本 <b>{s['n']}</b> 日",
                ), unsafe_allow_html=True)
            else:
                cols[i].info(f"后 {off} 日无足够前向样本")

        fig = go.Figure(go.Bar(
            x=[f"后{off}日" for off in [5, 10, 20]],
            y=[fs.get(off, {}).get("up_ratio", 0) for off in [5, 10, 20]],
            text=[f"{fs.get(off, {}).get('up_ratio', 0)}%" for off in [5, 10, 20]],
            textposition="auto", marker_color="#36c5d8",
        ))
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white", height=300,
            margin=dict(l=40, r=20, t=20, b=40),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            xaxis_title="前向窗口", yaxis_title="红盘占比(%)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("红盘占比(≥50%) 越高，说明历史上相似情境后继更常偏暖。仅描述经验分布，不保证复现。")

        st.markdown("### 📋 最相似历史日（按距离升序）")
        rows = []
        for it in res["similar"]:
            f = it["fwd"]
            rows.append({
                "日期": it["date"], "距离": it["dist"],
                "后5日红盘%": f.get(5), "后10日红盘%": f.get(10), "后20日红盘%": f.get(20),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.warning(f"⚠️ 无法生成历史相似日聚类（{res.get('reason','数据不足')}）。")

    # ── 诚实数据边界 ──
    st.markdown("---")
    st.markdown("### 🚧 离线数据边界（务必阅读）")
    dropped = res.get("dropped", {})
    if dropped:
        lines = "".join(f"\n- **{k}**：{v}" for k, v in dropped.items())
        st.markdown(f"以下维度经数据质量闸门剔除（离线缺真值，不参与距离计算）：{lines}")
    else:
        st.markdown("本次聚类使用的全部维度均为离线可靠字段。")
    miss = "; ".join(f"**{k}**（{v}）" for k, v in OFFLINE_MISSING.items())
    st.markdown(
        f"本页仅用离线可靠广度字段（上涨/下跌/平盘家数、涨停/跌停家数、红盘占比）计算相似度。"
        f"\n\n⚠️ 相似度距离中 涨/跌/平家数 与 红盘占比 属同一信息族（red_ratio 由前三者派生），"
        f"会放大『家数族』权重；结论应以『形态相似』定性参考，勿作精确趋同预期。"
        f"\n\n以下维度离线缺真值，已剔除、不编造：{miss}。"
        f"\n\n📐 方法学：取最新一日向量，按标准化欧氏距离检索最相似日并排除末日邻居防前视泄漏；"
        f"以相似日后继红盘占比构建经验分布（卡片中『红盘占比>50%的交易日占比』即 up_ratio）。"
        f"**历史类比非预测、不构成买卖建议**。"
    )
except Exception as exc:  # noqa: BLE001
    logger.exception("历史相似日聚类页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
