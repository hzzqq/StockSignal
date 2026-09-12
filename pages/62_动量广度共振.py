"""
页面 62：动量 × 广度 共振矩阵（方案④ 离线版）

把「广度（红盘率）」与「动量（涨停前日收益 zt_prev_ret）」两个离线可得的广度内部维度
做二维分档，呈现它们的**联合分布（共现）矩阵**，直观看二者是否经常同冷同热。

数据边界（诚实声明，页面内可见）：原方案为「资金流×广度共振」，但主力净流入需联网实时获取，
离线基座无真值；本页以「涨停前日收益」作动量代理刻画共振结构，真·资金流联网可用时再增强。
本矩阵描述共现结构，**不是**收益预测。
"""
import logging

import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, section_header
from modules import momentum_breadth_resonance as mbr

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="动量 × 广度 共振矩阵", icon="🧲",
    caption="广度（红盘率）× 动量（涨停前日收益）联合分布矩阵，看二者是否经常同冷同热。"
            "离线以涨停前日收益作动量代理；真·资金流需联网增强。矩阵描述共现结构，非收益预测。",
)

try:
    mat = mbr.resonance_matrix()
    cur = mbr.current_cell()
    stats = mbr.resonance_stats(mat)

    # ── 共现强度卡 ──
    st.markdown("### 📊 共振强度（共现结构）")
    if stats.get("available"):
        st.markdown(sf_card(
            title="广度–动量 共现概览",
            body=f"样本 <b>{stats['n_days']}</b> 交易日 ｜ "
                 f"「广度≥活跃 且 动量≥强」共现 <b>{stats['co_hot']}%</b> ｜ "
                 f"「广度≤偏冷 且 动量≤温和」共现 <b>{stats['co_cold']}%</b><br>"
                 f"最常见组合：<b>{stats['dominant_cell'][0]} × {stats['dominant_cell'][1]}</b>"
                 f"（{stats['dominant_cell'][2]} 天）",
        ), unsafe_allow_html=True)
        st.caption("共现占比高 = 两维度常同步；低 = 常背离。仅描述历史共现结构，不构成方向预测。")
    else:
        st.warning("⚠️ 广度历史不可用，无法计算共振矩阵。")

    # ── 共振矩阵热力图 ──
    st.markdown("### 🔥 广度 × 动量 联合分布矩阵（共现天数）")
    if mat.get("available"):
        M = mat["matrix"]
        fig = go.Figure(go.Heatmap(
            z=M,
            x=mat["mom_labels"], y=mat["rr_labels"],
            colorscale="Viridis",
            text=[[str(v) for v in row] for row in M],
            texttemplate="%{text}",
            colorbar=dict(title="天数"),
        ))
        # 标注当前所处格
        if cur.get("available") and cur.get("rr_band") is not None:
            fig.add_annotation(
                x=cur["mom_band"], y=cur["rr_band"],
                text="◉ 当前", showarrow=False,
                font=dict(color="white", size=12),
            )
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=420, margin=dict(l=60, r=20, t=20, b=60),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            xaxis_title="动量（涨停前日收益）", yaxis_title="广度（红盘率）",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("行=广度五档（冰点→狂热），列=动量五档（强杀跌→极强）。颜色越亮=共现天数越多。"
                    "◉ 标记当前交易日所处的（广度,动量）格。")
    else:
        st.info("暂无足够广度历史生成共振矩阵。")

    # ── 当前状态 ──
    st.markdown("### 📍 当前状态")
    if cur.get("available") and cur.get("rr_band") is not None:
        st.markdown(sf_card(
            title=f"当前（{cur['date']}）",
            body=f"广度 <b>{cur['red_ratio']}%</b> → <b>{cur['rr_label']}</b> ｜ "
                 f"动量 <b>{cur['zt_prev_ret']}</b> → <b>{cur['mom_label']}</b>",
            accent="#36c5d8",
        ), unsafe_allow_html=True)
    elif cur.get("available"):
        st.info("最新广度记录缺 red_ratio / zt_prev_ret，无法定位共振格。")
    else:
        st.warning("⚠️ 无法读取当前广度状态。")

    # ── 方法学声明 ──
    st.markdown("---")
    st.caption(
        "📐 方法学：本页用牧羊人广度聚合序列中的 red_ratio（广度）与 zt_prev_ret（涨停股前一日收益，动量代理）"
        "两个**离线可得**变量。原方案「资金流×广度共振」的主力净流入属网络实时数据，离线基座无真值，故以动量代理替代，"
        "真·资金流联网可用时再作增强维度。共振矩阵是两维度的**联合分布（共现天数）**，刻画「同冷同热」结构，"
        "不预测收益、不引入编造数据。"
    )

except Exception as exc:  # noqa: BLE001
    logger.exception("动量广度共振页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
