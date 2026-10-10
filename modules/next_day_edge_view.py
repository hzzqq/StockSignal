"""modules/next_day_edge_view.py — 页面组件：次日情绪极值判断（恐慌反弹信号）

复用 modules.sentiment_edge.panic_reversal 的 walk-forward 校准结论，在「今日决策面板」
等页面挂一个「明日方向」读数卡。

诚实红线（与 sentiment_edge 一致）：
  ✅ 可信：极端恐慌（跌停占比达历史前 10%）→ 次日红盘概率显著高于基准（约 +13pp，全历史 296 天 z=+4.36）
  ❌ 不可信：普通日子里次日涨跌方向 → 一律显示「方向不可预测 / 弃权」，绝不硬猜。

配色遵循 A 股约定（涨红跌绿）：概率边际为正（偏多）用 delta_color="inverse"（红）。
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BREADTH_KEYS = ("up_count", "down_count", "flat_count",
                 "limit_down", "touch_down", "limit_up", "hb_wave10")


def _to_float(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def get_today_breadth() -> dict | None:
    """取当日市场广度（涨跌/平/跌停/触及跌停/涨停家数）。

    优先用 data/daily_snapshot.json 的 indicators（面板同源、轻量）；
    失败再回退到牧羊人活数据（最新一行）。都取不到返回 None。
    """
    # ① 快照（面板同源）
    try:
        snap = json.load(open(os.path.join(_ROOT, "data", "daily_snapshot.json"), encoding="utf-8"))
        ind = snap.get("indicators") or {}
        b = {k: _to_float(ind[k]) for k in _BREADTH_KEYS if ind.get(k) is not None}
        b = {k: v for k, v in b.items() if v is not None}
        if b:
            return b
    except Exception as e:  # noqa: BLE401
        logger.warning("[next_day_edge_view] 快照取广度失败: %s", e)

    # ② 牧羊人活数据（最新一行）
    try:
        from modules.shepherd import get_shepherd_indicators
        got = get_shepherd_indicators(days=1)
        df = got[0] if isinstance(got, (tuple, list)) else got
        if df is not None and len(df):
            row = df.iloc[-1]
            b = {}
            for k in _BREADTH_KEYS:
                if k in row.index:
                    v = _to_float(row[k])
                    if v is not None:
                        b[k] = v
            if b:
                return b
    except Exception as e:  # noqa: BLE401
        logger.warning("[next_day_edge_view] 活数据取广度失败: %s", e)
    return None


def render_next_day_edge(breadth: dict | None = None, dark: bool = False):
    """渲染「次日情绪极值判断」卡片。breadth 缺省时自动取当日广度。"""
    import streamlit as st
    from modules.sentiment_edge import panic_reversal
    from modules.ui_kit import xc_warn_box, xc_info_banner

    if breadth is None:
        breadth = get_today_breadth()

    res = panic_reversal(breadth or {})

    if not res.get("available"):
        xc_warn_box("情绪极值信号层不可用", hint=res.get("reason") or "校准件缺失/损坏，本次不做方向表态。")
        return

    st.markdown("#### 🔮 明日方向 · 恐慌出清反弹信号")
    if res.get("triggered"):
        prob = res.get("prob")
        base = res.get("base_rate")
        edge = res.get("edge_pp")
        h = (res.get("hits") or [{}])[0]
        c1, c2 = st.columns(2)
        c1.metric("次日红盘概率", f"{prob:.1%}",
                  delta=f"+{edge}pp vs 基准", delta_color="inverse")  # A股：偏多=红
        c2.metric("基准（无条件）", f"{base:.1%}",
                  delta=f"样本 {h.get('n')} 天 · z={h.get('z')}", delta_color="off")
        st.caption(res.get("statement", ""))
        st.caption("📌 这是全历史 walk-forward 统计概率，非确定性预测；该结论仅在「极端恐慌形态」成立，"
                   "普通日子本模块不表态。")
    else:
        if not res.get("evaluated"):
            xc_warn_box("当日情绪指标不足", hint=res.get("statement", ""))
        else:
            xc_info_banner(res.get("statement", ""), kind="info", icon="🤝")
        st.caption("📌 普通日子次日方向经全历史检验无法超越基准率（IC≈0），本模块不硬猜方向。")

    # 透明化：展示当日尺度无关占比，供用户核对
    ratios = res.get("ratios") or {}
    if ratios:
        with st.expander("📐 当日尺度无关占比（判定依据）", expanded=False):
            st.json(ratios)

    # 弱信号风险提示（触及跌停占比与次日波动弱相关，仅提示幅度）
    sh = res.get("strength_hint")
    if sh:
        st.caption(f"⚠️ {sh.get('hint', '')}")
