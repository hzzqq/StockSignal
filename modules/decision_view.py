"""modules/decision_view.py — 决策面板共享渲染组件（依赖 streamlit）。

把 50_市场情绪 / 54_今日决策面板 中重复的「情绪信号四卡 + 仓位建议大卡 + 梯队晋级率表」
收敛为单一实现，避免两页配色/口径漂移（改一处即全改）。

纯展示：数据取自 modules.decision / modules.shepherd_ladder 的返回值，不在这里做计算。
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render_signal_cards(temp, cyc_name, cyc_emoji, score, bias, overall, latest_date,
                         temp_delta=None, overall_delta=None):
    """顶部情绪信号四卡：市场温度 / 情绪周期 / 次日评分 / 综合晋级率。

    :param temp: 市场温度 0-100
    :param cyc_name: 情绪周期名（如「修复确认」）
    :param cyc_emoji: 周期 emoji
    :param score: 次日情绪评分（可 None）
    :param bias: 偏多/偏空/中性
    :param overall: 综合晋级率(%) 或 None
    :param latest_date: 晋级率最新快照日期
    :param temp_delta: 温度较昨日变化（可 None，不显示 delta）
    :param overall_delta: 晋级率较昨日变化（可 None，不显示 delta）
    """
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _temp_label = "过热" if temp >= 70 else ("温和" if temp >= 45 else "偏冷")
        _delta = None if temp_delta is None else round(float(temp_delta), 1)
        st.metric("🌡️ 市场温度", f"{temp:.0f}", delta=_delta,
                  delta_color="off" if _delta is not None else None,
                  help="牧羊人 17 项综合温度 0-100，越高越热；delta=较昨日")
        st.caption(_temp_label)
    with c2:
        st.metric("🔄 情绪周期", cyc_name or "—")
        st.caption(cyc_emoji or "⚪")
    with c3:
        st.metric("🔮 次日评分", f"{score:.0f}" if score is not None else "—",
                  help="次日情绪评分 0-100，越高环境越友好")
        st.caption(f"方向 {bias}")
    with c4:
        _od = None if overall_delta is None else round(float(overall_delta), 1)
        st.metric("🪜 综合晋级率", f"{overall:.1f}%" if overall is not None else "—",
                  delta=_od, delta_color="off" if _od is not None else None,
                  help="连板梯队首板→二板晋级率，代表接力意愿；delta=较昨日")
        st.caption(latest_date or "—")


def render_position_card(pos, bias=None, confidence=None, cyc_name=None):
    """仓位建议大卡。pos 来自 modules.decision.derive_position 的返回。

    红涨绿跌：pos['color'] 已按 band 定好（偏多/激进=红，偏空/防御=绿，中性=黄）。
    """
    st.markdown(
        f"<div style='border:1px solid {pos['color']};border-radius:12px;padding:14px 18px;"
        f"margin:10px 0;background:linear-gradient(90deg,{pos['color']}22,{pos['color']}05)'>"
        f"<div style='display:flex;justify-content:space-between;align-items:baseline'>"
        f"<span style='font-size:14px;opacity:.8'>📊 仓位建议（{pos['band']}）</span>"
        f"<span style='font-size:34px;font-weight:700;color:{pos['color']}'>{pos['pct']}%</span></div>"
        f"<div style='height:10px;background:rgba(128,128,128,.2);border-radius:5px;margin:8px 0'>"
        f"<div style='width:{pos['pct']}%;background:{pos['color']};height:10px;border-radius:5px'></div></div>"
        f"<div style='font-size:12px;opacity:.85'>" +
        "；".join(pos["reasons"]) +
        f"<br><span style='opacity:.6'>次日方向 {bias or '—'}｜置信度 {confidence or 0}%｜"
        f"情绪周期 {cyc_name or '—'}</span></div></div>",
        unsafe_allow_html=True,
    )
    st.caption("⚠️ 仓位建议由温度/周期/评分/晋级率透明推导，是概率参考而非确定性指令，不构成投资建议。")


def render_ladder_table(promo):
    """连板梯队晋级率表。promo 来自 shepherd_ladder.ladder_promotion_rates 的返回。"""
    overall = promo.get("overall")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("综合晋级率（首板→二板）", f"{overall:.1f}%" if overall is not None else "—")
    with c2:
        st.metric("历史天数", promo.get("days", 0))
    rates = promo.get("rates") or {}
    if rates:
        rows = []
        for tier, r in rates.items():
            rows.append({"档位": tier, "晋级率": f"{r:.1f}%" if r is not None else "—"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(f"最新快照日期：{promo.get('latest_date', '—')}　·　"
               "晋级率 = 当日 n 板家数 / 昨日 (n-1) 板家数；≥60% 接力强、<20% 梯队断档。")
