"""
页面 68：情绪拐点扫描器（方案⑨）

对离线可靠广度维度算滚动 z-score（窗口 60 日），检测「极端后反转」形态：自 < -2 回升越过 -1 → 触底反转；
自 > +2 回落越过 +1 → 触顶回落。汇总近期拐点事件并标注单维度折线。仅描述历史形态，非预测。

数据边界：连板梯队类维度离线缺真值，已通过数据闸门剔除，不扫描、不编造。
"""
import logging

import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules import inflection_scanner as ins
from modules.breadth_features import OFFLINE_MISSING, labels as _flabels, data_as_of

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="情绪拐点扫描器", icon="📝",
    caption="离线可靠广度维度滚动 z-score 极端后反转检测（触底反转 / 触顶回落）。仅描述历史形态，非预测。",
)
st.caption(f"📅 数据截至 **{data_as_of()}**（离线健康镜像快照，**非实时行情**）")

try:
    ev = ins.list_events()
    _fl = _flabels()
    usable = ev.get("dims", [])
    if not usable:
        st.warning("⚠️ 无可用广度维度生成拐点扫描（数据不足或维度被剔除）。")
    else:
        _dim = st.sidebar.selectbox(
            "扫描维度", options=usable, index=0,
            format_func=lambda k: _fl.get(k, k),
        )
        ser = ins.series_for(_dim)
        st.markdown("### 🔔 近期拐点事件（末 20 交易日）")
        if ev.get("available") and ev["events"]:
            rows = [{"日期": e["date"], "维度": e["label"], "类型": e["type"],
                     "极值": e["extreme"], "现值": e["current"]} for e in ev["events"]]
            st.dataframe(rows, width="stretch", hide_index=True)
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
            st.plotly_chart(fig, width="stretch")
            st.caption("橙点=检测到的拐点；红线 ±2 为极端阈值，黄线 ±1 为反转确认阈值。z-score 仅描述相对自身 60 日均值的偏离，非预测。")
        else:
            st.info("该维度无足够历史生成 z-score 轨迹。")

    # ── 诚实数据边界 ──
    st.markdown("---")
    st.markdown("### 🚧 离线数据边界（务必阅读）")
    dropped = ev.get("dropped", {})
    if dropped:
        lines = "".join(f"\n- **{k}**：{v}" for k, v in dropped.items())
        st.markdown(f"以下维度经数据质量闸门剔除（离线缺真值，不参与扫描）：{lines}")
    miss = "; ".join(f"**{k}**（{v}）" for k, v in OFFLINE_MISSING.items())
    st.markdown(
        f"本页仅对离线可靠广度字段（上涨/下跌/平盘家数、涨停/跌停家数、红盘占比）做 z-score 拐点检测。"
        f"\n\n⚠️ 这些维度是**市场宽度的动量/反转形态**（涨跌幅家数、极限宽度），并非狭义『投资者情绪调查』类指标；"
        f"连板梯队类情绪维度离线缺真值已剔除，故本页的『情绪』实为『广度动能的极端反转』。"
        f"\n\n以下维度离线缺真值，已剔除、不编造：{miss}。"
        f"\n\n📐 方法学：对维度计算 60 日滚动 z-score，检测「自极端(<−2 或 >+2)反转越过确认阈值(∓1)」形态。"
        f"这是历史序列的形态描述，**不构成方向预测或买卖建议**。"
    )
except Exception as exc:  # noqa: BLE001
    logger.exception("情绪拐点扫描器页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
