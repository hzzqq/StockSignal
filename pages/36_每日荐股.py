"""
页面：📅 每日荐股（T-233）
================================================
多算法融合选股（multi_factor V5 / 双趋势共振 / 主力资金流 / P1 事件因子 / 动量量能），
每交易日收盘后由后端调度器自动生成（data/daily_recommendation.json），本页直接读本地最新份。

每只推荐附：五路算法得分归因（缺失算法如实标注 unavailable）+ 买入方案
（入场/目标/止损 = ATR 倍数，仓位提示联动决策快照）+ 逐条理由 + 免责声明。
用户可在本页关闭荐股推送（消息中心不再展示该类型；默认开启）。
"""
import json
import os

import streamlit as st

from modules.page_utils import render_standard_page
from modules.session import get_user_setting, save_user_setting
from modules.ui_kit import info_banner, xc_warn_box
from modules.recommend_engine import (
    ALGO_LABELS, DISCLAIMER, load_latest_recommendation,
)

dark = render_standard_page(
    title="每日荐股", icon="📅",
    caption="多算法融合选股 · 买入方案 · 逐算法解释（每交易日收盘后自动生成）",
    layout="wide",
)

# ── 用户设置开关（默认开启；关闭后消息中心不再展示荐股）──
_enabled = get_user_setting("daily_recommend", True)
c_toggle, _ = st.columns([1, 3])
with c_toggle:
    new_val = st.toggle("接收每日荐股（关闭后消息中心不再展示）", value=bool(_enabled),
                        key="rec_toggle")
    if new_val != bool(_enabled):
        save_user_setting("daily_recommend", bool(new_val))
        st.rerun()

rec = load_latest_recommendation()

if rec.get("status") != "ok":
    xc_warn_box(f"📅 {rec.get('reason', '推荐暂不可用')}")
    info_banner("荐股由后台调度器在每交易日 15:30 后自动生成一次（幂等）；管理员也可在 "
                "POST /api/recommendations/generate 手动触发。")
    st.stop()

# ── 数据时效护栏（T-235）：行情整体滞后超阈值时显著告警，不悄悄用旧数据荐股 ──
_st = rec.get("data_staleness") or {}
if _st.get("stale"):
    st.warning(f"⚠️ **数据时效告警**：{_st.get('note', '行情数据滞后')}——荐股依据可能过时，请谨慎参考。")

# ── 市场上下文 ──
ctx = rec.get("market_context") or {}
mc1, mc2, mc3, mc4 = st.columns(4)
with mc1:
    st.metric("市场温度", ctx.get("temperature", "—"))
with mc2:
    st.metric("情绪周期", ctx.get("cycle", "—"))
with mc3:
    pos = (ctx.get("position") or {}).get("pct", "—")
    st.metric("建议总仓位", f"{pos}%")
with mc4:
    st.metric("候选池", f"{rec.get('scored_size', '—')} / {rec.get('universe_size', '—')}")

st.caption(f"生成时间：{rec.get('generated_at', '—')} · 行情截至各标的 data_as_of · "
           f"算法缺失标的：multi_factor {rec.get('algo_unavailable', {}).get('multi_factor', 0)} 只 / "
           f"dual_trend {rec.get('algo_unavailable', {}).get('dual_trend', 0)} 只（如实降级，不编造分数）")

# ── 推荐卡片 ──
picks = rec.get("picks") or []
if not picks:
    xc_warn_box("今日候选全部被过滤（均无有效算法得分），请稍后重试或查看次日推荐。")
    st.stop()

for i, p in enumerate(picks, 1):
    with st.container(border=True):
        head_l, head_r = st.columns([3, 1])
        with head_l:
            st.markdown(
                f"### {i}. {p.get('name', '')} `{p.get('code', '')}`"
                f"<span style='font-size:14px;color:var(--txt2)'>　综合 <b style='color:var(--acc1)'>"
                f"{p.get('composite', '—')}</b>/100</span>",
                unsafe_allow_html=True,
            )
        with head_r:
            st.metric("综合评分", f"{p.get('composite', '—')}")

        # 买入方案
        plan = p.get("plan") or {}
        pl1, pl2, pl3, pl4 = st.columns(4)
        with pl1:
            st.metric("入场参考", f"¥{plan.get('entry', '—')}")
        with pl2:
            st.metric("目标价（3×ATR）", f"¥{plan.get('target', '—')}")
        with pl3:
            st.metric("止损价（2×ATR）", f"¥{plan.get('stop', '—')}")
        with pl4:
            st.metric("仓位提示", f"{plan.get('position_pct_hint', '—')}%" if plan.get("position_pct_hint") else "—",
                      help=plan.get("position_note", ""))

        # 算法归因（缺失如实标注）
        with st.expander("🔬 算法归因与理由（五路算法独立打分）", expanded=(i == 1)):
            algos = p.get("algorithms") or {}
            for k, meta in algos.items():
                label = ALGO_LABELS.get(k, k)
                if meta.get("raw") is None:
                    st.markdown(f"- **{label}**：`unavailable`（该算法在此标的不可用，未参与融合）")
                else:
                    st.markdown(
                        f"- **{label}**：原始 {meta['raw']} → 归一化 {meta['normalized']} "
                        f"（权重 {meta['weight']} → 有效 {meta['effective_weight']}）")
            if p.get("reasons"):
                st.caption("；".join(p["reasons"]))

        st.caption(f"行情截至 {p.get('data_as_of', '—')} · 单票上限 20%、等权 {len(picks)} 只 · "
                   f"点击跳转：在「个股研究」输入 {p.get('code')} 查看深度分析")

# ── 历史模拟统计引用（虚拟用户模拟器产物，存在才展示，不编造）──
_sim_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "reports", "virtual_users_sim.json")
if os.path.exists(_sim_path):
    try:
        with open(_sim_path, encoding="utf-8") as f:
            sim = json.load(f)
        s = sim.get("aggregate") or {}
        with st.expander("🧪 万级虚拟用户模拟统计（历史蒙特卡洛，非实盘）", expanded=False):
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("模拟用户数", sim.get("meta", {}).get("n_users", "—"))
            k2.metric("中位回报", f"{s.get('return_median_pct', '—')}%")
            k3.metric("正收益占比", f"{s.get('pct_positive', '—')}%")
            k4.metric("平均最大回撤", f"{s.get('maxdd_avg_pct', '—')}%")
            st.caption(f"p5 {s.get('return_p5_pct', '—')}% / p95 {s.get('return_p95_pct', '—')}% · "
                       f"{sim.get('meta', {}).get('honesty_note', '')}")
    except Exception:  # noqa: BLE001
        pass

# ── 免责声明 ──
info_banner(f"⚠️ {DISCLAIMER}")
