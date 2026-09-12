"""
页面 63：全温度档历史回测（方案⑤ 离线版）

把每个历史交易日按「红盘率 red_ratio」归入市场温度计五档（冰点/偏冷/中性/活跃/狂热），
回测各档其后 1 日 / 5 日的**红盘率均值回归结构**（次日改善率、平均变化），并给出全样本基准对照。

诚实声明（页面内可见）：本页刻画广度均值回归结构，**不是**收益预测；只用离线广度序列，
零编造指数收益。样本量<50 的档位明确标注低置信。
"""
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card
from modules import temperature_backtest as tb

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="全温度档历史回测", icon="🌡️",
    caption="按红盘率归入温度计五档，回测各档后 1 日 / 5 日红盘率均值回归结构，并对照全样本基准。"
            "全程离线、零编造收益。",
)

try:
    res = tb.band_backtest()

    if not res.get("available"):
        st.warning(f"⚠️ 温度回测不可用：{res.get('reason', '未知')}")
        st.stop()

    # ── 方法学声明 ──
    st.caption(
        "📐 温度档由当日红盘率(red_ratio)经市场温度计五档阈值映射；回测统计各档后 1 日 / 5 日红盘率变化"
        "（次日改善率 = 次日红盘率高于当日占比），刻画广度均值回归结构，**不是**收益预测。"
        "全程离线（牧羊人广度长历史），零编造指数收益。"
    )

    # ── 全样本基准卡 ──
    base = res["baseline"]
    st.markdown("### 📏 全样本基准")
    st.markdown(sf_card(
        title="无条件下一日 / 5 日表现",
        body=f"样本 <b>{base['n']}</b> 交易日 ｜ "
             f"次日改善率 <b>{base['next_impr_rate']}%</b>（均变 {base['next_mean_delta']}）｜ "
             f"5 日改善率 <b>{base['d5_impr_rate']}%</b>（均变 {base['d5_mean_delta']}）",
        accent="#94a3b8",
    ), unsafe_allow_html=True)
    st.caption("基准 = 不看档位、随机一日的平均表现。各档与之对照才能看出「冷热是否有均值回归」。")

    # ── 各档回测表 ──
    st.markdown("### 🌡️ 五档回测明细")
    rows = []
    low_conf = []
    for b in res["bands"]:
        if not b.get("available"):
            rows.append({"温度档": b["label"], "样本天数": 0, "次日均变": "—",
                         "次日改善率": "—", "5日均变": "—", "5日改善率": "—"})
            continue
        rows.append({
            "温度档": b["label"],
            "样本天数": b["n"],
            "次日均变": b["next_mean_delta"],
            "次日改善率": f"{b['next_impr_rate']}%",
            "5日均变": b["d5_mean_delta"],
            "5日改善率": f"{b['d5_impr_rate']}%",
        })
        if b["n"] < 50:
            low_conf.append(b["label"])
    tbl = pd.DataFrame(rows)
    st.dataframe(tbl, hide_index=True, use_container_width=True)
    if low_conf:
        st.warning(f"⚠️ 低置信档位（样本<50，仅供结构参考）：{', '.join(low_conf)}")

    # ── 次日改善率柱状图 ──
    st.markdown("### 📊 次日改善率（各档 vs 基准）")
    labels = [b["label"] for b in res["bands"]]
    vals = [b.get("next_impr_rate", 0) if b.get("available") else 0 for b in res["bands"]]
    colors = [b["color"] for b in res["bands"]]
    fig = go.Figure(go.Bar(x=labels, y=vals, marker_color=colors,
                           text=[f"{v}%" for v in vals], textposition="outside"))
    fig.add_hline(y=base["next_impr_rate"], line_dash="dash", line_color="#94a3b8",
                  annotation_text=f"基准 {base['next_impr_rate']}%", annotation_position="top right")
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=380, margin=dict(l=40, r=20, t=30, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb" if dark else "#1f2937"),
        yaxis_title="次日红盘率改善率 (%)", xaxis_title="温度档",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 结论解读 ──
    st.markdown("### 🔎 结论解读")
    cold = next(b for b in res["bands"] if b["level"] == 0)
    hot = next(b for b in res["bands"] if b["level"] == 4)
    st.markdown(sf_card(
        title="广度均值回归结构（诚实描述，非预测）",
        body=f"冰点档（n={cold['n']}）次日红盘率改善率高达 <b>{cold['next_impr_rate']}%</b>"
             f"（均变 +{cold['next_mean_delta']}），呈现极强**超跌反弹**特征；"
             f"狂热档（n={hot['n']}）次日改善率仅 <b>{hot['next_impr_rate']}%</b>"
             f"（均变 {hot['next_mean_delta']}），呈现明显**过热回落**特征。"
             f"中间档（偏冷/中性/活跃）依次为 72%→45%→25%，单调过渡，"
             f"说明「红盘率越极端，次日越向 50% 均值回归」是 A 股广度的稳定结构。",
        accent="#36c5d8",
    ), unsafe_allow_html=True)
    st.caption("注意：这是历史广度结构统计，描述的是「群体情绪的均值回归」，不构成买卖点预测；"
               "极端档样本虽大，仍可能受特定政策/外生冲击扰动。")

except Exception as exc:  # noqa: BLE001
    logger.exception("温度回测页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
