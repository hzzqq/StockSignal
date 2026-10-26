# -*- coding: utf-8 -*-
"""pages/98_仓位落地.py — T-326 方向B：个股→组合落地（仓位分配器页面）。

把市场仓位决策落到具体标的：市场仓位（当日快照 position.pct）× 三源评分
（荐股引擎综合分 / 用户 StockScore / 等权明示降级）→ 个股目标权重。

诚实边界（老板 2026-10-26 拍板）：
- 纯建议层，只读：不自动下单、绝不直写 portfolio.csv，建议 ≠ 交易；
- 无当日快照 → unavailable，不实时臆算；
- 评分缺失的标的剔除并注明，绝不编造；
- 单票上限（默认 20%）封顶，总敞口被 cap 约束时如实交代缺口；
- 等权＝明示降级（meta.degraded），页面明示「未使用任何评分信号」；
- 所有 metric 为中性值 → delta_color="off"（A 股红涨绿跌语义在此无涨跌可比）。
"""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from modules import position_allocator as pa
from modules.page_utils import render_standard_page

logger = logging.getLogger(__name__)

render_standard_page(
    "仓位落地", "🎯",
    caption="市场仓位 × 个股评分 → 个股目标权重（纯建议 · 只读 · 不写持仓）")

st.warning("⚠️ **建议 ≠ 交易**：本页只产出「目标权重」参考，系统不会自动下单，"
           "也绝不写入你的持仓记录（portfolio.csv 只读不碰）。数据源=当日归档快照，"
           "无快照不实时臆算。", icon="🚦")

SOURCE_LABELS = {
    "recommend": "📊 荐股引擎综合分",
    "user": "⭐ 用户 StockScore",
    "equal": "⚖️ 等权（明示降级）",
}


def _render_market_header(pct: float, pmeta: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("市场仓位（快照）", f"{pct:g}%", delta_color="off")
    with c2:
        st.metric("仓位档", str(pmeta.get("band") or "—"), delta_color="off")
    temp = pmeta.get("temperature")
    with c3:
        st.metric("市场温度", f"{temp:g}" if isinstance(temp, (int, float)) else "—",
                  delta_color="off")
    with c4:
        st.metric("快照数据日", str(pmeta.get("snapshot_date") or "—"), delta_color="off")


@st.fragment
def render_alloc(source: str) -> None:
    result = pa.build_allocation(source)
    if result.get("status") != "ok":
        st.warning(f"⚠️ {result.get('reason', '分配不可用')}")
        return
    meta = result["meta"]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("分配票数", meta["n_alloc"], delta_color="off")
    with m2:
        st.metric("Σ目标权重", f"{meta['sum_pct']:g}%", delta_color="off")
    with m3:
        st.metric("单票上限", f"{meta['cap_pct']:g}%", delta_color="off")
    with m4:
        st.metric("剔除票数（评分缺失）", meta["n_excluded"], delta_color="off")

    if meta.get("degraded"):
        st.info(f"ℹ️ {meta.get('degraded_note', '等权明示降级：未使用任何评分信号')}")
    if meta.get("overflow_pct"):
        st.warning(f"⚠️ 标的数 × 单票上限不足以承载市场仓位：总敞口被封顶在 "
                   f"{meta['sum_pct']:g}%（目标 {meta['target_pct']:g}%，"
                   f"缺口 {meta['overflow_pct']:g}% 如实少配，不凑满）。")
    capped = meta.get("capped") or []
    if capped:
        st.caption(f"截断标注：{'、'.join(capped)} 触及单票上限，超出部分已按权重重分给其余标的。")

    rows = [{"代码": a["code"], "名称": a["name"],
             "评分": a["score"] if a["score"] is not None else "—",
             "目标权重": f"{a['weight']:.2%}",
             "目标仓位": f"{a['pct']:g}%",
             "触上限": "是" if a["code"] in capped else "否"}
            for a in result["allocations"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    excluded = result.get("excluded") or []
    if excluded:
        with st.expander(f"🚫 被剔除标的（{len(excluded)}，评分缺失不编造）"):
            for e in excluded:
                st.markdown(f"- `{e['code']}` {e['name']}：{e['reason']}")

    src = meta.get("source") or {}
    mkt = meta.get("market") or {}
    parts = [f"评分源：{src.get('label', '—')}"]
    if src.get("generated_at"):
        parts.append(f"推荐生成 {src['generated_at']}")
    if src.get("data_as_of"):
        parts.append(f"行情截至 {src['data_as_of']}")
    if mkt.get("snapshot_date"):
        parts.append(f"市场快照 {mkt['snapshot_date']}")
    st.caption(" · ".join(parts) + "　｜　建议≠交易，请结合自身风控独立决策")


def main() -> None:
    pct, pmeta = pa.load_market_pct()
    if pct is None:
        st.warning(f"⚠️ {pmeta.get('reason', '市场仓位不可得')}")
        st.caption("本页只读当日归档快照（data/daily_snapshot.json），"
                   "不做实时推导——避免基于残缺输入给出看似完整的仓位建议。")
        return
    _render_market_header(pct, pmeta)
    source = st.radio(
        "评分源", list(SOURCE_LABELS),
        format_func=lambda k: SOURCE_LABELS[k],
        horizontal=True,
        help="推荐引擎/用户评分：权重∝评分；等权：自选池均分（明示降级，不构成强弱排序）。"
             "单票上限默认 20%，Σ权重=市场仓位。")
    render_alloc(source)


main()
