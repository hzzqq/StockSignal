"""页面 73：自定义看板 / 工作区（G5）

对标 OpenBB 的 Workspace / Dashboards / Folders：用户把常用模块拼装成一页，
直接解决本项目「41 页太散、找不到重点」的痛点。

设计：
- 模块注册表 ``WIDGETS``：key → (标签, 图标, 渲染函数)。新增模块只需加一条。
- 用户选择（多选，**顺序即展示顺序**）存 ``st.session_state`` 并持久化到
  ``data/user_dashboard.json``（data/ 已 gitignore，属用户本地偏好，不入库）。
- 复用现有本地数据源（快照 / 牧羊人 / 状态机），**逐模块异常隔离**：
  单个模块取数失败只在该卡片内提示，不影响整页与其它模块——对齐「诚实降级」红线。
- 纯前端编排，无新业务逻辑；不编造数据，取不到就明说。
"""
from __future__ import annotations

import json
import logging
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.colors import UP_COLOR
from modules.page_utils import render_standard_page
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)

_PREF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "user_dashboard.json"
)


# ── 模块渲染器（每个都自带异常兜底；取不到数据显示「未就绪」而非崩溃/编造）──
def _w_market_state(dark):
    from modules import market_regime as mr
    rep = mr.regime_report(k=8)
    if not rep or not rep.get("available"):
        st.info("📭 市场状态机数据未就绪。")
        return
    latest = rep["latest"]
    c1, c2 = st.columns(2)
    with c1:
        sf_metric("市场状态", latest.get("state") or "—", "五档状态机")
    with c2:
        conf = latest.get("confidence")
        sf_metric("置信度", f"{conf * 100:.0f}%" if isinstance(conf, (int, float)) else "—", "规则强度")


def _w_temperature(dark):
    from modules.shepherd import load_latest_snapshot
    snap = load_latest_snapshot() or {}
    temp = snap.get("temperature")
    cycle = snap.get("cycle")
    c1, c2 = st.columns(2)
    with c1:
        sf_metric("市场温度", f"{temp:.1f}" if isinstance(temp, (int, float)) else "—", "0-100")
    with c2:
        sf_metric("情绪周期", cycle or "—", "来自每日决策快照")


def _w_decision(dark):
    from modules.shepherd import load_latest_snapshot
    snap = load_latest_snapshot() or {}
    pos = snap.get("position")
    date = snap.get("date") or snap.get("as_of") or "—"
    c1, c2 = st.columns(2)
    with c1:
        sf_metric("建议仓位", f"{pos:.0f}%" if isinstance(pos, (int, float)) else "—", "决策闭环")
    with c2:
        sf_metric("快照日期", str(date), "数据新鲜度以日期为准")


def _w_zt_ladder(dark):
    from modules.shepherd import _trading_days, get_zt_ladder
    days = _trading_days(3)
    ladder = get_zt_ladder(days[-1]) if days else {}
    dist = (ladder or {}).get("distribution") or []
    if not dist:
        st.info("📭 连板梯队数据未就绪。")
        return
    fig = go.Figure(go.Bar(
        x=[f"{b}板" for b, _ in dist], y=[c for _, c in dist],
        marker_color=UP_COLOR, text=[c for _, c in dist], textposition="outside",
    ))
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=240, margin=dict(l=10, r=10, t=20, b=10), showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")


def _w_limit_stats(dark):
    from modules.shepherd import get_shepherd_indicators
    df, _meta = get_shepherd_indicators(days=5)
    if df is None or df.empty:
        st.info("📭 牧羊人情绪指标未就绪。")
        return
    row = df.iloc[-1]
    fr = row.get("zt_fail_ratio")
    lu = row.get("limit_up")
    c1, c2 = st.columns(2)
    with c1:
        sf_metric("涨停家数", str(int(lu)) if lu == lu and lu is not None else "—", "全市场")
    with c2:
        sf_metric("炸板率", f"{float(fr):.1f}%" if fr == fr and fr is not None else "—",
                  "炸板/(涨停+炸板)")


def _w_breadth(dark):
    from modules.shepherd import get_shepherd_indicators
    df, _meta = get_shepherd_indicators(days=30)
    if df is None or df.empty:
        st.info("📭 广度数据未就绪。")
        return
    col = "median_chg" if "median_chg" in df.columns else None
    if not col:
        st.info("📭 该数据源无中位涨跌字段。")
        return
    s = pd.to_numeric(df[col], errors="coerce").dropna().tail(30)
    if s.empty:
        st.info("📭 无有效样本。")
        return
    fig = go.Figure(go.Scatter(y=s.values, mode="lines", line=dict(color=UP_COLOR)))
    fig.update_layout(template="plotly_dark" if dark else "plotly_white",
                      height=220, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    st.plotly_chart(fig, width="stretch")


# key → (标签, 图标, 渲染器)
WIDGETS = {
    "market_state": ("市场状态机", "🔄", _w_market_state),
    "temperature": ("市场温度 / 情绪周期", "🌡️", _w_temperature),
    "decision": ("今日决策仓位", "🎯", _w_decision),
    "zt_ladder": ("连板梯队", "🪜", _w_zt_ladder),
    "limit_stats": ("涨停 / 炸板统计", "📊", _w_limit_stats),
    "breadth": ("中位涨跌趋势", "📈", _w_breadth),
}
DEFAULT_SELECTION = ["decision", "market_state", "temperature", "zt_ladder"]


def _load_prefs() -> list:
    try:
        if os.path.exists(_PREF_PATH):
            with open(_PREF_PATH, encoding="utf-8") as f:
                data = json.load(f)
            sel = [k for k in data.get("widgets", []) if k in WIDGETS]
            if sel:
                return sel
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[dashboard] 读取偏好失败: {e}")
    return list(DEFAULT_SELECTION)


def _save_prefs(sel: list) -> bool:
    try:
        os.makedirs(os.path.dirname(_PREF_PATH), exist_ok=True)
        with open(_PREF_PATH, "w", encoding="utf-8") as f:
            json.dump({"widgets": list(sel)}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[dashboard] 保存偏好失败: {e}")
        return False


dark = render_standard_page(
    title="自定义看板", icon="🧩",
    caption="把常用模块拼装成一页工作区（对标 OpenBB Workspace）：多选模块、顺序即展示顺序，"
            "偏好保存在本地 data/user_dashboard.json，换页不丢。",
)

section_header("模块配置", "选择要显示的模块；顺序即页面展示顺序", icon="⚙️")
sel = st.multiselect(
    "我的模块",
    options=list(WIDGETS.keys()),
    default=_load_prefs(),
    format_func=lambda k: f"{WIDGETS[k][1]} {WIDGETS[k][0]}",
    key="dash_widgets",
)
_btn1, _btn2, _spacer = st.columns([1, 1, 3])
with _btn1:
    if st.button("💾 保存为我的看板", key="dash_save", width="stretch"):
        st.success("✅ 已保存。") if _save_prefs(sel) else st.warning("⚠️ 保存失败（磁盘只读或异常）。")
with _btn2:
    if st.button("♻️ 恢复默认", key="dash_reset", width="stretch"):
        st.session_state["dash_widgets"] = list(DEFAULT_SELECTION)
        st.rerun()

st.markdown("---")

if not sel:
    st.info("请至少选择一个模块。")
else:
    for key in sel:
        label, icon, fn = WIDGETS[key]
        with st.container(border=True):
            section_header(label, icon=icon)
            try:
                fn(dark)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[dashboard] 模块 {key} 渲染失败: {e}")
                st.warning(f"⚠️ 模块「{label}」暂不可用（数据源异常），其余模块不受影响。")

st.caption("⚠️ 说明：本页仅做前端编排，所有数据来自既有本地数据源（快照 / 牧羊人 / 状态机）；"
           "取不到即明示「未就绪」，不编造。")
