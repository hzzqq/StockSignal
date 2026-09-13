"""
页面 65：投机情绪周期时钟（方案⑥）

用离线健康镜像可靠填充的广度字段（涨停家数 / 跌停家数 / 红盘占比 / 涨跌家数）构造「投机情绪周期」：
以涨停家数 + 红盘占比的历史分位识别 亢奋/活跃/偏冷/冰点/中性 相位。
纯离线、描述性，不预测。

数据边界：连板梯队类维度（连板高度/连板家数/炸板率/封成比/昨日涨停表现/倒跌停）离线缺真值，本页不引用、不编造。
"""
import logging

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card
from modules import speculative_clock as sc
from modules.breadth_features import OFFLINE_MISSING, labels as _flabels, data_as_of

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="投机情绪周期时钟", icon="🗞️",
    caption="用涨停家数+红盘占比的历史分位识别投机情绪相位（亢奋/活跃/偏冷/冰点/中性）。"
            "纯离线、描述性框架，不预测收益。仅用离线可靠广度字段。",
)
st.caption(f"📅 数据截至 **{data_as_of()}**（离线健康镜像快照，**非实时行情**）")

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
        if cur["phase"] == "数据不足":
            st.warning(f"⚠️ {cur.get('reason', '最新一行关键字段缺失')}")
        else:
            _lu = cur.get("limit_up")
            _rr = cur.get("red_ratio")
            _lu_pct = cur.get("limit_up_pct")
            st.markdown(sf_card(
                title=f"当前（{cur['date']}）· {cur['phase']}",
                body=f"红盘占比 <b>{_rr}</b>% ｜ 涨停家数 <b>{_lu}</b>（历史分位 "
                     f"{(_lu_pct*100):.0f}%）｜ 跌停家数 <b>{cur.get('limit_down')}</b><br>"
                     f"<span style='color:#8c8c8c'>{cur['reason']}</span>",
                accent="#36c5d8",
            ), unsafe_allow_html=True)
    else:
        st.warning("⚠️ 无法读取当前广度状态。")

    # ── 时序图（各自 min/max 归一化叠加）──
    st.markdown("### 📈 广度情绪时序（归一化叠加）")
    if res.get("available") and res.get("dates"):
        s = res["series"]
        cols = list(s.keys())
        fig = go.Figure()
        palette = ["#36c5d8", "#ea580c", "#a855f7", "#22c55e", "#eab308"]
        for idx, c in enumerate(cols):
            vals = [v for v in s[c]]
            arr = np.array([np.nan if v is None else v for v in vals], dtype=float)
            lo, hi = np.nanmin(arr), np.nanmax(arr)
            norm = arr - lo if lo == hi else (arr - lo) / (hi - lo)
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
        st.caption("各线按自身区间归一化以便叠加对比走势；仅描述历史周期，不构成方向预测。")
    else:
        st.info("暂无足够广度历史生成时序图。")

    # ── 诚实数据边界 ──
    st.markdown("---")
    st.markdown("### 🚧 离线数据边界（务必阅读）")
    miss = "; ".join(f"**{k}**（{v}）" for k, v in OFFLINE_MISSING.items())
    st.markdown(
        f"本页仅使用离线健康镜像中**可靠填充**的广度字段："
        f"{'、'.join(_flabels().values())}。"
        f"\n\n以下广度维度**离线缺真值**，本页一律不引用、不编造：{miss}。"
        f"\n\n📐 方法学：相位判定基于红盘占比 + 涨停家数的历史分位（亢奋 ≥60%且涨停家数前20% / "
        f"活跃 ≥60% / 冰点 <30%且涨停家数后20% / 偏冷 <40% / 否则中性），用于描述投机情绪所处阶段，"
        f"**不预测收益、不构成买卖建议**。"
    )
except Exception as exc:  # noqa: BLE001
    logger.exception("投机情绪周期时钟页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
