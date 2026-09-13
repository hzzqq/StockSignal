"""
页面 66：维度领先-滞后矩阵（方案⑦）

用离线可靠广度维度（涨跌/平家数、涨停/跌停家数、红盘占比）的全历史日序列，计算两两互相关在 lag 0~20 日的最优领先滞后，
呈现「谁先动、谁确认」的传导结构。互相关仅描述协同/错位，**非因果、非预测**。

数据边界：连板梯队类维度（连板高度/连板家数/炸板率/封成比/昨日涨停表现/倒跌停）离线缺真值，
已通过数据闸门剔除，不进入相关计算、不编造。
"""
import logging

import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules import lead_lag_matrix as ll
from modules.breadth_features import OFFLINE_MISSING

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="维度领先-滞后矩阵", icon="📑",
    caption="离线可靠广度维度两两互相关的最优领先滞后（lag 0~20 日），看传导结构。"
            "互相关仅描述协同/错位，非因果、非预测。",
)

try:
    res = ll.lead_lag_matrix()
    st.markdown("### 🔗 领先-滞后矩阵（行领先列，单位：交易日）")
    if res.get("available") and res.get("matrix"):
        dims = res["dims"]
        names = [res["labels"][d] for d in dims]
        zmat = [[res["matrix"][i][j] for j in range(len(dims))] for i in range(len(dims))]
        fig = go.Figure(go.Heatmap(
            z=zmat, x=names, y=names, colorscale="RdBu", zmid=0,
            text=zmat, texttemplate="%{text}", colorbar=dict(title="领先 lag"),
        ))
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=480, margin=dict(l=80, r=20, t=20, b=80),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            xaxis_title="领先维度", yaxis_title="滞后维度",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("正值 = 行维度领先列维度该天数（正相关）；负值 = 反向领先；0 = 窗口内无显著领先。"
                   "互相关衡量两个序列在时间上的协同/错位，非因果、非预测。")
    else:
        st.info("暂无足够广度历史生成领先-滞后矩阵。")

    # ── 诚实数据边界：展示被剔除维度 ──
    st.markdown("---")
    st.markdown("### 🚧 离线数据边界（务必阅读）")
    dropped = res.get("dropped", {})
    if dropped:
        lines = "".join(f"\n- **{k}**：{v}" for k, v in dropped.items())
        st.markdown(f"以下维度经数据质量闸门剔除（非空率过低或近乎常数，不做相关计算）：{lines}")
    st.markdown(
        "本页仅使用离线健康镜像中**可靠填充**的广度字段（上涨/下跌/平盘家数、涨停/跌停家数、红盘占比）。"
        "\n\n📐 方法学：对各维度日序列做 z-score 归一后，计算两两在 lag 0~20 日的最优互相关，"
        "取符号表示领先方向与相关性正负。**非因果、非预测**，仅描述历史协同结构。"
    )
except Exception as exc:  # noqa: BLE001
    logger.exception("维度领先滞后矩阵页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
