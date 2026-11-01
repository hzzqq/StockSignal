# -*- coding: utf-8 -*-
"""pages/97_决策回放.py — T-325 方向D：决策复盘回放器。

按交易日回放「当日当时的决策依据」：
  归档快照（温度/周期/仓位/理由） → 连板晋级率 → 事件因子（诚实标注 P1 未归档）
  → 次日实际广度对照 + 预测打分对账。

诚实边界：
- 只回放已归档日期（data/snapshots/，稀疏归档自 2026-08-31 起）；无归档不编造；
- 次日对照取 CSV 严格后一交易日，缺失如实标注「无数据」，不默认 0；
- A 股红涨绿跌全局语义（KPI 卡经 ui_kit xc_kpi_grid 渲染，收益类按 delta_dir/tone 正红负绿）。
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
from modules.ui_kit import xc_kpi_grid

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
    xc_kpi_grid([
        {"label": "市场温度", "value": f"{snap.get('temperature', '—')}"},
        {"label": "情绪周期", "value": str(snap.get("cycle") or "—")},
        {"label": "建议仓位", "value": f"{pos.get('pct', snap.get('position_pct', '—'))}%"},
        {"label": "置信度", "value": str(snap.get("confidence") or "—")},
    ])
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
    _promo = snap.get("promo_overall")
    xc_kpi_grid([{"label": "综合晋级率",
                  "value": "—" if _promo is None else str(_promo)}])
    ladder = snap.get("ladder") or {}
    if ladder:
        xc_kpi_grid([{"label": str(k), "value": f"{v if v is not None else '—'}"}
                     for k, v in ladder.items()])
    else:
        st.caption("归档快照未含梯队明细")

    # ── ③ 事件因子（P1 诚实边界） ──
    st.subheader("📡 事件因子")
    ev = snap.get("event_factor") or {}
    if ev:
        xc_kpi_grid([
            {"label": "可用性", "value": "可用" if ev.get("available") else "不可用"},
            {"label": "信号", "value": str(ev.get("signal") or "—")},
            {"label": "数据日", "value": str(ev.get("date") or "—")},
        ])
    st.info(f"ℹ️ {P1_REPLAY_NOTE}")

    # ── ④ 次日实际对照 + 预测对账 ──
    st.subheader("⚖️ 次日实际对照与预测对账")
    nxt = rec.get("next_day")
    if nxt:
        diff = None
        if nxt.get("up_count") is not None and nxt.get("down_count") is not None:
            diff = nxt["up_count"] - nxt["down_count"]
        xc_kpi_grid([
            {"label": "次日交易日", "value": str(nxt.get("date") or "—")},
            {"label": "上涨家数", "value": str(nxt.get("up_count") if nxt.get("up_count") is not None else "无数据")},
            {"label": "下跌家数", "value": str(nxt.get("down_count") if nxt.get("down_count") is not None else "无数据")},
        ])
        if diff is not None:
            tone = "#e64545" if diff > 0 else ("#2e9e5b" if diff < 0 else "#8a8f98")
            label = "普涨" if diff > 0 else ("普跌" if diff < 0 else "均衡")
            # ui_audit_exempt: unsafe-allow-html 广度差徽标：tone/label 为内部常量 + diff 数值，无用户/DB 输入流向
            st.markdown(
                f"<span style='color:{tone};font-weight:600'>广度差 {diff:+d}（{label}）"
                f"</span>", unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html
        else:
            st.caption("次日广度数据缺失（CSV 稀疏段），如实不补")
    else:
        st.caption("次日无交易数据（归档为末段 / 假日），如实不补")

    pred = rec.get("prediction")
    if pred:
        _realized = pred.get("realized")
        # A 股红涨绿跌：次日实际涨跌为带符号收益，正红负绿
        _rl_tone = ('up' if _realized > 0 else ('down' if _realized < 0 else 'flat')
                    if isinstance(_realized, (int, float)) else 'flat')
        xc_kpi_grid([
            {"label": "当日预测方向", "value": str(pred.get("bias") or "—")},
            {"label": "次日实际涨跌", "value": "—" if _realized is None else f"{float(_realized):+.2f}%",
             "tone": _rl_tone},
            {"label": "打分结果",
             "value": {True: "命中", False: "未命中", None: "无方向信息（平盘/未打分）"}.get(pred.get("hit"), str(pred.get("hit")))},
            {"label": "预测仓位", "value": f"{pred.get('pct', '—')}%"},
        ])
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

    # ── 方法学与来源注脚（B 类页五段式收尾）──
    st.markdown("---")
    st.caption("口径与来源：归档快照=每日快照脚本落盘（data/snapshots/，稀疏归档自 2026-08-31 起，只回放已归档日）；次日实际广度/涨跌=本地 CSV 严格后一交易日（缺失如实标注，不默认 0）；预测对账=prediction_log 打分记录。全部为历史归档数据（非实时行情），不构成投资建议。")


main()