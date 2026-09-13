"""
页面 68：情绪拐点扫描器（方案⑨）

对每个广度维度算滚动 z-score（窗口 60 日），检测「极端后反转」形态：自 < -2 回升越过 -1 → 触底反转；
自 > +2 回落越过 +1 → 触顶回落。汇总近期拐点事件并标注单维度折线。仅描述历史形态，非预测。

数据边界：全部维度来自 shepherd_history 内部可观测变量，无指数/行业/资金流，不编造。
"""
import logging

import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card
from modules import inflection_scanner as ins

logger = logging.getLogger(__name__)

_DIMS = [
    ("red_ratio", "红盘占比"), ("limit_up", "涨停家数"), ("limit_down", "跌停家数"),
    ("zt_prev_ret", "昨日涨停表现"), ("connect_hl", "连板高度"), ("connect_2b", "连板家数"),
    ("zt_fail_ratio", "炸板率"), ("touch_down", "倒跌停家数"),
]

dark = render_standard_page(
    title="情绪拐点扫描器", icon="📝",
    caption="广度维度滚动 z-score 极端后反转检测（触底反转 / 触顶回落）。仅描述历史形态，非预测。"
            "维度均来自 shepherd_history 内部变量。",
)

try:
    _dim = st.sidebar.selectbox(
        "扫描维度", options=[k for k, _ in _DIMS], index=0,
        format_func=lambda k: dict(_DIMS)[k],
    )
    ev = ins.list_events()
    ser = ins.series_for(_dim)

    st.markdown("### 🔔 近期拐点事件（末 20 交易日）")
    if ev.get("available") and ev["events"]:
        rows = [{"日期": e["date"], "维度": e["label"], "类型": e["type"],
                 "极值": e["extreme"], "现值": e["current"]} for e in ev["events"]]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption(f"共 {len(ev['events'])} 个事件；类型=触底反转(自<-2回升过-1) / 触顶回落(自>+2回落过+1)。")
    else:
        st.info("近 20 交易日未检测到显著拐点，或历史数据不足。")

    st.markdown("### 📉 单维度 z-score 轨迹（含拐点标注）")
    if ser.get("available") and ser.get("dates"):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ser["dates"], y=ser["z"], name="z-score",
                                mode="lines", line=dict(width=1.6, color="#36c5d8")))
        for m in ser["markers"]:
            if m < len(ser["dates"]):
                fig.add_trace(go.Scatter(
                    x=[ser["dates"][m]], y=[ser["z"][m]], mode="markers",
                    marker=dict(size=10, color="#ea580c", symbol="circle"),
                    name="拐点", showlegend=False,
                ))
        for lvl, c in [(-2, "#ef4444"), (2, "#22c55e"), (-1, "#f59e0b"), (1, "#f59e0b")]:
            fig.add_hline(y=lvl, line_dash="dot", line_color=c, opacity=0.4)
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white", height=380,
            margin=dict(l=40, r=20, t=20, b=40),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            xaxis_title="日期", yaxis_title="z-score(60日)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("橙点=检测到的拐点；红线 ±2 为极端阈值，黄线 ±1 为反转确认阈值。z-score 仅描述相对自身 60 日均值的偏离，非预测。")
    else:
        st.info("该维度无足够历史生成 z-score 轨迹。")

    st.markdown("---")
    st.caption(
        "📐 方法学：本页对每个广度维度计算 60 日滚动 z-score，检测「自极端(<−2 或 >+2)反转越过确认阈值(∓1)」的形态。"
        "这是历史序列的形态描述，不构成方向预测或买卖建议；全部变量离线可得，不引入编造数据。"
    )
except Exception as exc:  # noqa: BLE001
    logger.exception("情绪拐点扫描器页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
