# -*- coding: utf-8 -*-  # noqa: UP009
"""
P1 组合构建诊断 · 零售端落地组件（A 方向 L1/L2）

把 P1-QuantFactor 的组合构建止血诊断（⑰/⑱/⑲）以**只读、零风险**方式接入 StockSignal：
  - L1（零风险纯展示）：alpha 衰减预警徽标 —— 当「近 59 日基准相对 < +5%」或「多空 LS_t < 0」
    时顶部橙/红提示，诚实告知用户纯多头选股边缘已近归零。
  - L2（低风险）：组合构建诊断折叠区 —— 纯多头 / 市场中性 / 等权全市场 净值曲线（FULL→近59日）
    + 关键窗口收益表 + buffer=0.1「免费午餐」说明。

数据来自 `data/p1_signals/portfolio_diag.json`（由 sj 侧离线诊断导出，含 as_of 与诚实边界）。
本模块只读取、只渲染，绝不改动生产信号 / pred / ks 执行层。
"""
import logging
import os
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)
try:  # 与本仓 p1_signal 同口径优先序解析诊断 JSON
    from modules.ui_kit import (xc_warn_box, xc_success_box, xc_info_banner)  # noqa: F401
except Exception:  # noqa: BLE001
    xc_warn_box = xc_success_box = xc_info_banner = None  # type: ignore


def _diag_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    env = os.environ.get("P1_SIGNAL_DIR")
    if env:
        cand = Path(env) / "portfolio_diag.json"
        if cand.exists():
            return cand
    cand = root / "data" / "p1_signals" / "portfolio_diag.json"
    return cand


@st.cache_data(ttl=1800, show_spinner=False)
def load_diag() -> dict | None:
    """读取组合构建诊断快照；缺失/损坏则优雅降级返回 None。"""
    p = _diag_path()
    if not p.exists():
        logger.warning("portfolio_diag.json 缺失: %s", p)
        return None
    try:
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("portfolio_diag.json 解析失败: %s", e)
        return None


def render_alpha_decay_badge():
    """L1：alpha 衰减预警徽标（纯展示，读快照即可）。

    触发逻辑（与 sj 侧诊断一致）：近 59 日基准相对 < +5% → warn；多空 LS_t < 0 → 加重 warn。
    """
    d = load_diag()
    if d is None:
        return
    l1 = d.get("l1") or {}
    level = l1.get("level", "ok")
    text = l1.get("badge_text", "")
    as_of = (d.get("meta") or {}).get("as_of", "未知")
    if not text:
        return
    _suffix = f"　·　诊断截至 {as_of}（离线回测快照，非实时）"
    if level == "warn":
        if xc_warn_box is not None:
            xc_warn_box(text + _suffix)
    else:
        if xc_success_box is not None:
            xc_success_box(text + _suffix)
        elif xc_info_banner is not None:
            xc_info_banner(text + _suffix)


def render_portfolio_diag_fold(dark: bool = False):
    """L2：组合构建诊断折叠区（净值曲线 + 关键窗口收益表 + buffer 免费午餐说明）。"""
    d = load_diag()
    if d is None:
        xc_info_banner("未找到组合构建诊断数据（data/p1_signals/portfolio_diag.json）。")
        return
    from streamlit import plotly_chart  # local import 避免与顶层 st 冲突
    import plotly.graph_objects as go  # noqa: I001

    meta = d.get("meta") or {}
    summary = d.get("summary_key") or {}
    buf = d.get("buffer_free_lunch") or {}
    curves = d.get("curves") or {}
    as_of = meta.get("as_of", "未知")

    with st.expander("🩹 组合构建诊断（alpha 衰减 / 止血路径 · 离线快照）", expanded=False):
        st.caption(
            f"诊断截至 {as_of}　·　{meta.get('params','')}"
        )
        # ① 关键窗口收益表
        st.markdown("**📊 关键窗口收益（net 含真实成本；rf=10=horizon，非重叠桶）**")
        import pandas as pd
        rows = []
        for w, v in summary.items():
            rows.append({
                "窗口": w,
                "纯多头收益": f"{v.get('long_only_return', float('nan'))*100:+.1f}%" if isinstance(v.get("long_only_return"), (int, float)) else "—",
                "市场中性(多空)": f"{v.get('long_short_return', float('nan'))*100:+.1f}%" if isinstance(v.get("long_short_return"), (int, float)) else "—",
                "基准相对": f"{v.get('benchmark_relative', float('nan'))*100:+.1f}%" if isinstance(v.get("benchmark_relative"), (int, float)) else "—",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, key="p1_port_diag_tbl")
        st.caption(
            "基准相对 = 纯多头 − 等权全市场。市场中性靠 short 腿扛旗（零售端不可做空 → 不可落地为实盘）。"
        )

        # ② 净值曲线（FULL→近59日）+ 2026 标记
        lo = curves.get("long_only_net") or {}
        ls = curves.get("long_short_net") or {}
        bm = curves.get("benchmark_gross") or {}
        if lo.get("dates") and ls.get("dates") and bm.get("dates"):
            idx2026 = curves.get("idx_2026", 0)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=lo["dates"], y=lo["values"], name="纯多头 net",
                                    mode="lines", line=dict(color="#ee2a2a", width=2)))
            fig.add_trace(go.Scatter(x=ls["dates"], y=ls["values"], name="市场中性 net",
                                    mode="lines", line=dict(color="#7c5cff", width=2)))
            fig.add_trace(go.Scatter(x=bm["dates"], y=bm["values"], name="等权全市场 gross",
                                    mode="lines", line=dict(color="#888", width=1.5, dash="dot")))
            if 0 <= idx2026 < len(lo["dates"]):
                fig.add_vline(x=lo["dates"][idx2026], line_dash="dash", line_color="#f59e0b",
                              annotation_text="2026", annotation_position="top right")
            fig.update_layout(
                height=340, template="plotly_dark" if dark else "plotly_white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                margin=dict(l=40, r=20, t=30, b=30), yaxis_title="净值 (起点=1)",
            )
            plotly_chart(fig, width="stretch", key="p1_port_diag_curve")
            st.caption("纯多头 2026 已转负（−1.8%）、近59日 −7.1%；市场中性 2026 仍 +10.5% 但零售端不可做空。"
                       "曲线为离线回测快照，非实时。")
        else:
            st.caption("净值曲线数据缺失，仅展示收益表。")

        # ③ buffer=0.1 免费午餐
        st.markdown("**🍱 buffer=0.1 免费午餐**")
        b0 = buf.get("buffer0_full"); b1 = buf.get("buffer01_full")
        if isinstance(b0, (int, float)) and isinstance(b1, (int, float)):
            st.caption(f"rf=10 换手 130%→98%，全样本净 {b0*100:+.1f}%→{b1*100:+.1f}%（不降反升）。")
        st.caption(buf.get("note", ""))

        # ④ 诚实边界
        hb = meta.get("honest_boundary")
        if hb:
            st.caption("⚠️ " + hb)
