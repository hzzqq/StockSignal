"""页面 77：财报猎手（G10）

对标悟空量化的「财报猎手」：扫描**业绩预告**，把「预增 / 扭亏 / 预减」等信号分级，
快速筛出值得关注的业绩异动标的——事件驱动能力的增强。

数据源：东财业绩预告（``modules.fundflow.get_earnings_forecast``，best-effort，缓存 30 分钟）。

诚实性红线：
  · 预告类型分级为**启发式文本映射**，非预测；预增≠必涨，预告也可能被修正；
  · 接口不稳定时返回空表，页面明示「未就绪」，**不编造数据**；
  · 「业绩变动幅度」口径以数据源为准，页面原样展示不做再加工。
"""
from __future__ import annotations

import logging

import streamlit as st

from modules.financial_hunter import SIGNAL_ORDER, annotate, col_of, scan
from modules.page_utils import render_standard_page
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)

PERIODS = ["20260630", "20260331", "20251231", "20250930", "20250630"]
SIGNAL_COLOR = {"利好": "#dc2626", "偏多": "#f97316", "中性": "#94a3b8",
                "偏空": "#22c55e", "利空": "#16a34a"}


def _fmt_period(p: str) -> str:
    return f"{p[:4]}-{p[4:6]}-{p[6:]}" if len(p) == 8 else p


dark = render_standard_page(
    title="财报猎手", icon="🎣",
    caption="业绩预告信号扫描：预增/扭亏/预减等分级筛查。数据源东财业绩预告（best-effort）。"
            "启发式分级，非预测，不构成投资建议。",
)

period = st.selectbox("报告期", options=PERIODS, index=0, format_func=_fmt_period, key="fh_period")
_min_pct = st.slider("最小业绩变动幅度（%）", -200, 200, 0, step=10, key="fh_minpct")
_sigs = st.multiselect("只看信号级别", options=SIGNAL_ORDER, default=["利好", "偏多"], key="fh_signals")

try:
    from modules.fundflow import get_earnings_forecast
    raw = get_earnings_forecast(period)
except Exception as e:  # noqa: BLE001
    logger.warning(f"[fh] 业绩预告获取失败: {e}")
    st.error("⚠️ 业绩预告数据获取失败（接口异常或网络不可用），请稍后重试。")
    st.stop()

if raw is None or len(raw) == 0:
    st.info(f"📭 **{_fmt_period(period)}** 暂无业绩预告数据（可能未到披露期或接口暂不可用）。可切换其他报告期。")
    st.stop()

anno = annotate(raw)
# 顶部统计用全量（未过滤）
_vc = anno["_signal"].value_counts()
c1, c2, c3, c4 = st.columns(4)
with c1:
    sf_metric("预告总数", str(len(anno)), _fmt_period(period))
with c2:
    sf_metric("利好（预增/扭亏）", str(int(_vc.get("利好", 0))), "最强信号")
with c3:
    sf_metric("偏多（略增/续盈）", str(int(_vc.get("偏多", 0))), "")
with c4:
    sf_metric("利空（首亏/预减）", str(int(_vc.get("利空", 0))), "风险提示")

st.markdown("---")
section_header("信号分布", "按预告类型文本启发式分级", icon="📊")
_order = [s for s in SIGNAL_ORDER if _vc.get(s, 0) > 0]
st.markdown(
    "　".join(f"<span style='color:{SIGNAL_COLOR.get(s, '#94a3b8')};font-weight:700'>"
              f"{s} {int(_vc.get(s, 0))}</span>" for s in _order),
    unsafe_allow_html=True,
)

st.markdown("---")
section_header("猎手结果", f"筛选：信号 {'/'.join(_sigs) if _sigs else '全部'} · 变动幅度 ≥ {_min_pct}%", icon="🎯")
hits = scan(raw, min_pct=_min_pct, signals=_sigs or None)
if hits is None or hits.empty:
    st.info("当前筛选条件下无匹配标的（可放宽幅度或信号级别）。")
else:
    code_c, name_c, type_c = col_of(hits, "code"), col_of(hits, "name"), col_of(hits, "type")
    date_c, reason_c, metric_c = col_of(hits, "date"), col_of(hits, "reason"), col_of(hits, "metric")
    rows = ""
    for _, r in hits.head(60).iterrows():
        nm = str(r.get(name_c, "")) if name_c else ""
        cd = str(r.get(code_c, "")) if code_c else ""
        ty = str(r.get(type_c, "")) if type_c else ""
        sig = str(r.get("_signal", ""))
        pct = r.get("_pct")
        pct_txt = f"{float(pct):+.1f}%" if pct == pct and pct is not None else "—"
        dt = str(r.get(date_c, "")) if date_c else ""
        reason = str(r.get(reason_c, ""))[:60] if reason_c else ""
        rows += (
            "<div style='border:1px solid rgba(148,163,184,.2);border-radius:10px;"
            "padding:8px 12px;margin:6px 0'>"
            "<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<div><b>{nm}</b> <span style='opacity:.6;font-size:12px'>{cd} · {dt}</span></div>"
            "<div>"
            f"<span style='color:{SIGNAL_COLOR.get(sig, '#94a3b8')};font-size:11px;"
            f"border:1px solid {SIGNAL_COLOR.get(sig, '#94a3b8')};border-radius:6px;padding:1px 6px'>{sig}</span> "
            f"<b style='margin-left:6px'>{ty}</b> "
            f"<b style='color:{'#dc2626' if (pct or 0) >= 0 else '#16a34a'};margin-left:6px'>{pct_txt}</b>"
            "</div></div>"
            + (f"<div style='opacity:.7;font-size:11px;margin-top:3px'>{reason}</div>" if reason else "")
            + "</div>"
        )
    st.markdown(rows, unsafe_allow_html=True)

st.caption("⚠️ 说明：业绩预告分级为启发式文本映射，非预测模型，不构成投资建议；"
           "预告数据可能被后续修正，请以正式财报为准。数据源 best-effort，缺失即明示不编造。")
