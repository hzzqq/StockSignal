# -*- coding: utf-8 -*-
"""pages/97_决策回放.py — T-325 方向D：决策复盘回放器。

按交易日回放「当日当时的决策依据」：
  归档快照（温度/周期/仓位/理由） → 连板晋级率 → 事件因子（诚实标注 P1 未归档）
  → 次日实际广度对照 + 预测打分对账。

诚实边界：
- 只回放已归档日期（data/snapshots/，稀疏归档自 2026-08-31 起）；无归档不编造；
- 次日对照取 CSV 严格后一交易日，缺失如实标注「无数据」，不默认 0；
- A 股红涨绿跌全局语义（delta_color="normal"）。
"""
from __future__ import annotations

import logging

import streamlit as st

from modules.decision_replay import (
    P1_REPLAY_NOTE,
    build_replay,
    list_replayable_dates,
)
from modules.page_utils import render_standard_page

logger = logging.getLogger(__name__)

dark = render_standard_page(
    "决策回放", "⏪",
    caption="回放当日当时的决策依据（归档快照 + 次日实际对照 + 预测打分对账）")


@st.fragment
def render_replay(date: str) -> None:
    rec = build_replay(date)
    if rec.get("status") != "ok":
        st.warning(f"⚠️ {rec.get('reason', '该日期不可回放')}")
        return
    snap = rec.get("snapshot") or {}

    # ── ① 当日当时快照 ──
    st.subheader("🎯 当日当时快照")
    pos = snap.get("position") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("市场温度", f"{snap.get('temperature', '—')}", delta_color="normal")
    c2.metric("情绪周期", str(snap.get("cycle") or "—"), delta_color="normal")
    c3.metric("建议仓位", f"{pos.get('pct', snap.get('position_pct', '—'))}%",
              delta_color="normal")
    c4.metric("置信度", str(snap.get("confidence") or "—"), delta_color="normal")
    cap = (f"快照生成 {snap.get('generated_at') or '—'} · 数据截至 "
           f"{snap.get('as_of') or snap.get('date') or '—'}"
           f" · 数据龄 {snap.get('data_age_days', '—')} 天 · "
           f"新鲜度 {str((snap.get('data_freshness') or {}).get('status') or '—')}")
    st.caption(cap)
    reasons = pos.get("reasons") or []
    if reasons:
        st.markdown("**仓位推导理由**")
        for r in reasons:
            st.markdown(f"- {r}")

    # ── ② 连板晋级率 ──
    st.subheader("🪜 连板晋级率")
    st.metric("综合晋级率", f"{snap.get('promo_overall') if snap.get('promo_overall') is not None else '—'}",
              delta_color="normal")
    ladder = snap.get("ladder") or {}
    if ladder:
        cols = st.columns(min(len(ladder), 6))
        for col, (k, v) in zip(cols, ladder.items()):
            col.metric(str(k), f"{v if v is not None else '—'}", delta_color="normal")
    else:
        st.caption("归档快照未含梯队明细")

    # ── ③ 事件因子（P1 诚实边界） ──
    st.subheader("📡 事件因子")
    ev = snap.get("event_factor") or {}
    if ev:
        e1, e2, e3 = st.columns(3)
        e1.metric("可用性", "可用" if ev.get("available") else "不可用", delta_color="normal")
        e2.metric("信号", str(ev.get("signal") or "—"), delta_color="normal")
        e3.metric("数据日", str(ev.get("date") or "—"), delta_color="normal")
    st.info(f"ℹ️ {P1_REPLAY_NOTE}")

    # ── ④ 次日实际对照 + 预测对账 ──
    st.subheader("⚖️ 次日实际对照与预测对账")
    nxt = rec.get("next_day")
    if nxt:
        diff = None
        if nxt.get("up_count") is not None and nxt.get("down_count") is not None:
            diff = nxt["up_count"] - nxt["down_count"]
        m1, m2, m3 = st.columns(3)
        m1.metric("次日交易日", str(nxt.get("date") or "—"), delta_color="normal")
        m2.metric("上涨家数", nxt.get("up_count") if nxt.get("up_count") is not None else "无数据",
                  delta_color="normal")
        m3.metric("下跌家数", nxt.get("down_count") if nxt.get("down_count") is not None else "无数据",
                  delta_color="normal")
        if diff is not None:
            tone = "#e64545" if diff > 0 else ("#2e9e5b" if diff < 0 else "#8a8f98")
            label = "普涨" if diff > 0 else ("普跌" if diff < 0 else "均衡")
            st.markdown(
                f"<span style='color:{tone};font-weight:600'>广度差 {diff:+d}（{label}）"
                f"</span>", unsafe_allow_html=True)
        else:
            st.caption("次日广度数据缺失（CSV 稀疏段），如实不补")
    else:
        st.caption("次日无交易数据（归档为末段 / 假日），如实不补")

    pred = rec.get("prediction")
    if pred:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("当日预测方向", str(pred.get("bias") or "—"), delta_color="normal")
        realized = pred.get("realized")
        p2.metric("次日实际涨跌", "—" if realized is None else f"{float(realized):+.2f}%",
                  delta_color="normal")
        hit = pred.get("hit")
        hit_label = {True: "命中", False: "未命中", None: "无方向信息（平盘/未打分）"}.get(hit, str(hit))
        p3.metric("打分结果", hit_label, delta_color="normal")
        p4.metric("预测仓位", f"{pred.get('pct', '—')}%", delta_color="normal")
    else:
        st.caption("该日无预测打分记录（prediction_log 未覆盖），如实不补")


def main() -> None:
    dates = list_replayable_dates()
    if not dates:
        st.warning("⚠️ 尚无归档快照（data/snapshots/ 为空）——先运行 scripts/daily_snapshot.py 生成归档")
        return
    sel = st.selectbox("选择回放日期（仅已归档日）", dates, index=len(dates) - 1,
                       help="只有「当日当时」归档的日期可回放；无归档日期不提供事后重构口径")
    render_replay(sel)


main()
