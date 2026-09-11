"""
页面 58：连板龙头强度 × 事件×广度共振

把「连板梯队」从家数刻画升级为**市场级连板龙头强度指数**，并把它与
《市场状态机》的五档状态做**共振判定**，再叠加本地事件因子多头池（P1 EV）
做「事件×广度」交叉验证。全部复用既有模块（shepherd_ladder / market_regime /
shepherd），离线零网，单源失败优雅降级。

诚实性红线（本页可见）：
  · 梯队历史仅逐日家数分布、**无逐股名称** → 龙头是「市场级强度」，不列个股。
  · 历史样本极小（生产仅 ~8 日）→ 晋级概率明确标注「即时观测、小样本」。
  · 事件池为离线快照 → 展示数据日期与时效性，非实时事件。
"""
import logging

import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric, section_header
from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules import market_regime as mr
from modules import shepherd_ladder as sl

logger = logging.getLogger(__name__)

STATE_COLORS = {
    "暴跌": "#dc2626", "恐慌": "#f97316", "震荡": "#f59e0b",
    "结构牛": "#22c55e", "普涨": "#16a34a",
}
LEADER_BAND_COLOR = {  # 龙头强度分档配色（非涨跌语义，强度语义）
    "high": "#16a34a", "mid": "#f59e0b", "low": "#94a3b8",
}


def _leader_color(score):
    if score is None:
        return "#94a3b8"
    if score >= 60:
        return LEADER_BAND_COLOR["high"]
    if score >= 30:
        return LEADER_BAND_COLOR["mid"]
    return LEADER_BAND_COLOR["low"]


def _bar(label, value, color, maxv=100.0, suffix=""):
    pct = max(0.0, min(100.0, (float(value) / maxv) * 100.0)) if value is not None else 0.0
    return (
        f"<div style='margin:6px 0'>"
        f"<div style='display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px'>"
        f"<span>{label}</span><span style='color:{color};font-weight:700'>{value if value is not None else '—'}{suffix}</span></div>"
        f"<div style='height:8px;background:{_hex_to_rgba(color,0.18)};border-radius:5px'>"
        f"<span style='display:block;height:100%;width:{pct:.1f}%;background:{color};border-radius:5px'></span></div></div>"
    )


def _safe(v, nd=2, na="N/A"):
    if v is None or (isinstance(v, float) and v != v):
        return na
    return f"{v:.{nd}f}"


dark = render_standard_page(
    title="连板龙头 × 事件共振", icon="🐉",
    caption="市场级连板龙头强度 + 市场状态共振判定 + 事件因子多头池交叉验证。离线零网，小样本诚实标注。",
)

try:
    regime = mr.regime_report(k=8)
    ls = sl.leader_strength_index()
    ndp = sl.next_day_promotion_probability()
    ep = sl.load_event_pool()
    state = regime["latest"]["state"] if regime.get("available") else None
    rr = None
    try:
        from modules.shepherd import get_shepherd_indicators
        df, _ = get_shepherd_indicators(days=5)
        if df is not None and not df.empty:
            rr = float(df.iloc[-1].get("red_ratio", float("nan")))
    except Exception:
        rr = None
    reso = sl.event_breadth_resonance(state, ls.get("score"), red_ratio=rr)

    st.info(
        f"📅 梯队最新快照 **{ls.get('date') or '—'}** · 状态真值日 **{regime['latest']['date']}**"
        + ("（历史样本极小，概率类读数仅供参考）" if (ndp.get("n_pairs") or 0) < 10 else "")
    )

    # ── 顶部指标卡 ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        lcol = _leader_color(ls.get("score"))
        sf_metric("连板龙头强度", _safe(ls.get("score"), 1), "0-100 · 市场级")
    with c2:
        sc = STATE_COLORS.get(state, "#94a3b8")
        sf_metric("市场状态", state or "—", f"置信度 {regime['latest']['confidence']*100:.0f}%")
    with c3:
        ht = ndp.get("height_trend", "—")
        htc = {"高度扩张": "#16a34a", "高度退潮": "#dc2626", "高度持平": "#f59e0b", "无数据": "#94a3b8"}.get(ht, "#94a3b8")
        sf_metric("连板高度趋势", ht, f"最新 {ndp.get('max_boards')} 板")
    with c4:
        sup = reso.get("support")
        sup_label = {"bullish": "多头共振", "neutral": "中性", "bearish": "退潮风险", "none": "无信号"}.get(sup, "—")
        sf_metric("共振结论", sup_label, reso.get("label", ""))

    # ── 龙头强度分解 ──
    st.markdown("---")
    section_header("连板龙头强度分解", "高度 + 高位集中度 + 接力意愿（市场级，非个股）", icon="📐")
    comp = ls.get("components", {})
    html = ""
    html += _bar("连板高度（最高板映射）", comp.get("height"), _leader_color(comp.get("height")), suffix="")
    html += _bar("高位集中度（≥4板/总连板）", comp.get("density"), _leader_color(comp.get("density")), suffix="")
    html += _bar("接力意愿（2板晋级率）", comp.get("promo"), _leader_color(comp.get("promo")), suffix="%")
    st.markdown(html, unsafe_allow_html=True)
    if ls.get("distribution"):
        dist_str = " · ".join(f"{k}板 {v}家" for k, v in sorted(ls["distribution"].items()))
        st.caption(f"最新分布：{dist_str}（总连板 {ls.get('total_connect')} 家，最高 {ls.get('max_boards')} 板）")
    st.caption(ls.get("note", ""))

    # ── 次日晋级概率 ──
    st.markdown("---")
    section_header("次日晋级概率（诚实标注）", "即时观测值，非稳定历史概率", icon="🔭")
    pcol1, pcol2, pcol3 = st.columns(3)
    with pcol1:
        sf_metric("即时 2板晋级率", _safe(ndp.get("live_rate"), 1) + "%", "最近一对快照")
    with pcol2:
        sf_metric("历史平均晋级率", _safe(ndp.get("hist_rate"), 1) + "%", f"基于 {ndp.get('n_pairs')} 个日对")
    with pcol3:
        sf_metric("连板高度趋势", ndp.get("height_trend", "—"), "近5日均线比较")
    st.caption(ndp.get("note", ""))

    # ── 事件 × 广度共振 ──
    st.markdown("---")
    section_header("连板强度 × 市场状态 共振", "两路独立信号交叉验证", icon="🧲")
    rcol = reso.get("color", "#94a3b8")
    st.markdown(
        f"<div style='border-left:5px solid {rcol};border-radius:10px;padding:12px 16px;"
        f"background:{_hex_to_rgba(rcol,0.12)}'>"
        f"<div style='font-size:18px;font-weight:800;color:{rcol}'>{reso.get('label')}</div>"
        f"<div style='font-size:13px;opacity:.85;margin-top:4px'>{reso.get('detail','')}</div>"
        f"<div style='font-size:12px;opacity:.7;margin-top:6px'>状态「{state}」× 龙头强度 "
        f"{_safe(ls.get('score'),1)}（{('高' if ls.get('score',0)>=60 else '中' if ls.get('score',0)>=30 else '低')}）</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 事件因子多头池 ──
    st.markdown("---")
    section_header("事件因子多头池（交叉验证源）", "P1-QuantFactor EV 因子离线快照", icon="🎯")
    if ep.get("available"):
        if ep.get("stale"):
            st.warning("⚠️ 事件池数据较旧（" + str(ep.get("date")) + "），时效性存疑，仅作结构参考。")
        else:
            st.caption("事件池数据日期：" + str(ep.get("date")))
        st.caption(ep.get("note", ""))
        sup_badge = {"bullish": "✅ 当前共振支持", "neutral": "🟡 中性·观望",
                     "bearish": "🔴 当前状态不支持追高", "none": "⚪ 无信号"}.get(reso.get("support"), "")
        st.markdown(f"**共振对事件池的指引：** {sup_badge}")
        pool = ep.get("pool", [])[:10]
        rows = ""
        for it in pool:
            rows += (
                f"<tr><td style='padding:3px 8px'>{it.get('rank')}</td>"
                f"<td style='padding:3px 8px;font-family:monospace'>{it.get('symbol')}</td>"
                f"<td style='padding:3px 8px;color:{UP_COLOR}'>{_safe(it.get('score'),1)}</td>"
                f"<td style='padding:3px 8px'>{it.get('signal','—')}</td></tr>"
            )
        st.markdown(
            f"<table style='width:100%;font-size:12px;border-collapse:collapse'>"
            f"<thead><tr style='opacity:.6'><th style='text-align:left;padding:3px 8px'>#</th>"
            f"<th style='text-align:left;padding:3px 8px'>代码</th>"
            f"<th style='text-align:left;padding:3px 8px'>评分</th>"
            f"<th style='text-align:left;padding:3px 8px'>信号</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>",
            unsafe_allow_html=True,
        )
        st.caption("提示：事件池为统计超额收益概率排序，非买卖指令；本页不逐一列出连板个股（离线无逐股缓存）。")
    else:
        st.warning("事件因子多头池快照不可用：" + ep.get("note", ""))

    # ── 跳转 + 诚实声明 ──
    st.markdown("---")
    section_header("相关模块", "点击进入完整功能页", icon="🔗")
    st.page_link("pages/56_市场状态机.py", label="🧭 市场状态机 · 历史情境类比", icon="📊")
    st.page_link("pages/57_市场全景.py", label="🛰️ 市场全景 · 一页纸指挥台", icon="📊")
    st.page_link("pages/50_市场情绪.py", label="🌡️ 市场情绪 · 广度与情绪温度", icon="📊")
    st.page_link("pages/54_今日决策面板.py", label="🎯 今日决策面板", icon="📊")

    sf_card(
        "诚实声明",
        "① 龙头强度是**市场级**刻画（连板高度+高位集中度+接力意愿），梯队历史仅存逐日家数、"
        "无逐股名称，故本页不列个股龙头；② 晋级概率由最近1-2日推算、历史平均亦仅数个日对，"
        "属**即时观测、小样本**，绝非稳定历史概率；③ 事件池为离线快照，数据日期见上，"
        "非实时事件；④ 共振判定是「两路独立信号是否同向」的交叉验证，历史相似 ≠ 预测。",
        icon="📐",
    )

except Exception as e:  # noqa: BLE001
    logger.exception("[58_连板龙头共振] 渲染失败")
    st.error(f"页面渲染失败：{e}")
