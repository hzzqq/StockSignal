"""pages/82_数据时效性看板.py — 决策依赖全数据源「时效性 SLA 看板」（方向 #3）。

把「数据陈旧」从一句模糊提示升级成**可观测、可告警的一等公民**：逐源展示真实数据
截止日(as_of)、距今天数(lag_days)、状态灯(ok/warn/stale)与**停更检测**(stalled)。

- stalled（停更）：区别于 stale（lag 大）。一个源可能今天 lag 才 5(还 warn)，但 as_of 已
  连续多日冻结——这是"正在坏掉"的信号，靠 lag 看不出，靠停更检测提前报警
  （对应掘金/米筐的 Point-in-Time 数据质量严谨性）。详见 modules.data_health.detect_stall。
- 每次打开本页会落一条健康观测（record_health_observation），日积月累才有"最后推进日"
  可比——停更检测需要历史观测才能生效（单日打开只会看到未知/无历史）。
- 看板只读本地文件、不触网；陈旧源的「刷新命令」由 modules.data_health.build_refresh_plan
  生成（联网/跨仓命令在真机/CI 才会真正跑通，本页只展示，不伪造执行结果）。
"""
from __future__ import annotations

import logging

import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_kit import xc_kpi_grid, stat_tile, info_banner
from modules import data_health as dh

logger = logging.getLogger(__name__)


STATUS_META = {
    "ok":      ("✅ 新鲜",   "#1aa260", "数据截止日在阈值内"),
    "warn":    ("⚠️ 偏旧",   "#f5a623", "滞后 ≥4 天，仓位已封顶 60%"),
    "stale":   ("🔴 陈旧",   "#ee2a2a", "滞后 ≥8 天，仓位已封顶 40%"),
    "unknown": ("❓ 未知",   "#94a3b8", "取不到真实截止日，无法判定（不臆造）"),
}
_STALL_COLOR = "#a855f7"   # 停更用紫色，与 stale 红区分


def _source_card(row: dict) -> dict:
    """把 single source 行转成 xc_kpi_grid 卡片 dict。"""
    stt = row.get("status", "unknown")
    label, color, hint = STATUS_META.get(stt, STATUS_META["unknown"])
    as_of = row.get("as_of") or "—"
    lag = row.get("lag_days")
    lag_txt = f"滞后 {lag} 天" if lag is not None else "滞后未知"
    meta = f"截止 {as_of}　·　{lag_txt}"
    if row.get("stalled"):
        meta += f"　·　⏸ 已停更 {row.get('frozen_days')} 天"
    accent = _STALL_COLOR if row.get("stalled") else color
    return {
        "label": row["name"],
        "value": label,
        "sub": hint,
        "meta": meta,
        "accent": accent,
        "tone": "down" if stt in ("stale", "warn") else ("flat" if stt == "unknown" else "up"),
    }


def main():
    dark = render_standard_page(title="数据时效性 SLA 看板", icon="🔭", layout="wide")

    # 落一条观测，积累"最后推进日"历史（停更检测依赖历史）
    try:
        dh.record_health_observation()
    except Exception as e:  # noqa: BLE001 - 观测失败不阻断看板，但留痕可查（T-160）
        logger.warning("[data-sla] 健康观测落盘失败: %s", e)

    rows = dh.health_rows_enriched()
    if not rows:
        info_banner("暂无可观测的数据源。", kind="warning", icon="🩺")
        return

    # ── 概览 KPI ──
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_warn = sum(1 for r in rows if r["status"] == "warn")
    n_stale = sum(1 for r in rows if r["status"] == "stale")
    n_unknown = sum(1 for r in rows if r["status"] == "unknown")
    n_stalled = sum(1 for r in rows if r.get("stalled"))
    xc_kpi_grid([
        {"label": "数据源总数", "value": str(len(rows)), "accent": "#667eea"},
        {"label": "新鲜", "value": str(n_ok), "accent": "#1aa260", "tone": "up"},
        {"label": "偏旧", "value": str(n_warn), "accent": "#f5a623", "tone": "flat"},
        {"label": "陈旧", "value": str(n_stale), "accent": "#ee2a2a", "tone": "down"},
        {"label": "停更", "value": str(n_stalled), "accent": _STALL_COLOR, "tone": "down"},
        {"label": "未知", "value": str(n_unknown), "accent": "#94a3b8", "tone": "flat"},
    ])

    if n_stalled:
        info_banner(
            f"⏸ 检测到 {n_stalled} 个数据源 as_of 已连续冻结（停更）——滞后可能还没到 stale，"
            f"但数据已在悄悄失效，请优先按下方命令刷新。",
            kind="danger", icon="🛑")
    elif n_stale:
        info_banner(
            f"🔴 有 {n_stale} 个数据源陈旧（滞后 ≥8 天），仓位建议已自动封顶 40%。",
            kind="warning", icon="⏳")
    else:
        info_banner("全部决策依赖源均在时效阈值内；停更检测需多日观测历史方能生效。",
                    kind="success", icon="✅")

    # ── 逐源卡片 ──
    st.markdown("### 📡 逐源时效状态")
    xc_kpi_grid([_source_card(r) for r in rows], min_col=240)

    # ── 刷新计划 ──
    st.markdown("### 🛠 一键刷新计划")
    plan = dh.build_refresh_plan(stale_only=True)
    if not plan:
        st.caption("当前没有陈旧/停更源，无需刷新。")
    else:
        for p in plan:
            cov = "、".join(p["covers"])
            tag = "🌐 联网" if p["mode"] == "live" else "🔗 跨仓"
            st.markdown(f"**{tag} · 覆盖：{cov}**")
            if p["stale_sources"]:
                st.caption("需刷新：" + "、".join(p["stale_sources"]))
            cmd = p["cmd"].strip()
            if p["mode"] == "external":
                st.code(cmd, language="bash")
            else:
                st.code(cmd, language="python")
            st.caption(p["desc"])

    # ── 口径说明 ──
    st.markdown("---")
    st.caption(
        "口径：as_of=各源真实数据截止日（内容优先，取不到标 unknown 不臆造）；"
        "stale=距今天数≥8；warn≥4；stalled=as_of 连续冻结≥5 天（提前于 stale 报警）。"
        "本页只读本地文件，不触网；联网/跨仓刷新命令需在真机/CI 执行。")


if __name__ == "__main__":
    main()
