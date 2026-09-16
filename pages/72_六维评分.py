"""页面 72：六维量化评分（G4）

对标悟空量化的「六维评分」：技术 / 资金 / 价值 / 成长 / 基本面 / 周期，雷达图呈现，
一眼看透个股。并入「个股研究」体系（作为其量化评分子页）。

实现：各维取自不同真实数据源（历史行情 / 实时快照 / 财务摘要 / 市场状态机），
**逐维独立取数、独立降级**——某维取不到就标「缺失」并从雷达剔除，绝不用默认值
假装有分（诚实性红线）。评分映射为可解释的线性阈值（见 ``modules.six_dim``），非拟合模型。
"""
from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.colors import UP_COLOR
from modules.page_utils import render_standard_page
from modules.six_dim import DIM_LABELS, compute_dims
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)


@st.cache_data(ttl=600, show_spinner=False)
def _hist_cached(code: str) -> pd.DataFrame:
    import akshare as ak
    return ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")


@st.cache_data(ttl=120, show_spinner=False)
def _spot_row(code: str) -> dict:
    import akshare as ak
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty or "代码" not in df.columns:
        return {}
    row = df[df["代码"].astype(str) == str(code)]
    return row.iloc[0].to_dict() if len(row) else {}


@st.cache_data(ttl=3600, show_spinner=False)
def _fin_cached(code: str) -> pd.DataFrame:
    import akshare as ak
    return ak.stock_financial_abstract(symbol=code)


def _state_fn():
    from modules import market_regime as mr
    rep = mr.regime_report(k=8)
    return rep["latest"].get("state") if rep and rep.get("available") else None


dark = render_standard_page(
    title="六维量化评分", icon="🕸️",
    caption="技术 / 资金 / 价值 / 成长 / 基本面 / 周期 六维评分雷达（各 0–100）。"
            "逐维取自真实数据源，缺失维明示并从雷达剔除。启发式映射，非预测模型。",
)

code = st.text_input("股票代码（6 位）", value="600519", key="six_dim_code").strip()
if st.button("🔍 评分", key="six_dim_run", type="primary"):
    if not (code.isdigit() and len(code) == 6):
        st.warning("请输入 6 位数字股票代码。")
        st.stop()
    with st.spinner("拉取行情 / 快照 / 财务并评分…"):
        try:
            result, raw = compute_dims(code, _hist_cached, _spot_row, _fin_cached, _state_fn)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[six-dim] 评分失败: {e}")
            st.error("⚠️ 评分失败（数据源异常），请稍后重试。")
            st.stop()

    dims = result["dims"]
    overall, coverage = result["overall"], result["coverage"]
    if coverage == 0:
        st.warning("六维数据全部不可用（网络/接口异常），无法评分——诚实不出分。")
        st.stop()

    st.markdown("---")
    section_header("综合评分", f"有效 {coverage}/6 维等权平均（缺失维不参与，避免被 0 拉低）", icon="🎯")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        sf_metric("综合分", f"{overall:.1f}" if overall is not None else "—", "0–100")
    with c2:
        sf_metric("数据覆盖", f"{coverage}/6", "维度可用性")
    with c3:
        st.caption(f"代码 **{code}**"
                   + (f" · 市场状态 **{raw['state']}**" if raw.get("state") else "")
                   + (f" · 60 日位置 {raw['pos60']:+.1f}%" if raw.get("pos60") is not None else ""))

    avail = [(k, v) for k, v in dims.items() if v is not None]
    if len(avail) >= 3:
        theta = [DIM_LABELS[k] for k, _ in avail]
        r = [v for _, v in avail]
        fig = go.Figure(go.Scatterpolar(
            r=r + r[:1], theta=theta + theta[:1], fill="toself",
            line=dict(color=UP_COLOR),
        ))
        fig.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            height=380, margin=dict(l=40, r=40, t=30, b=20), showlegend=False,
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("有效维度不足 3，雷达不可用。")

    section_header("逐维分解", "每维的原始输入与映射结果（缺失维明示原因）", icon="🧩")
    _raw_hint = {
        "technical": "MA20 偏离 / 20&60 日动量",
        "capital": f"换手 {raw.get('turnover')} · 量比 {raw.get('vol_ratio')}",
        "value": f"PE {raw.get('pe')} · PB {raw.get('pb')}",
        "growth": f"净利同比 {raw.get('profit_yoy')}",
        "fundamental": f"ROE {raw.get('roe')}",
        "cycle": f"状态 {raw.get('state')} · 60日位置 {raw.get('pos60')}",
    }
    rows = ""
    for k in ["technical", "capital", "value", "growth", "fundamental", "cycle"]:
        v = dims.get(k)
        val_txt = f"{v:.1f}" if v is not None else "— 缺失"
        color = UP_COLOR if (v or 0) >= 60 else ("#f59e0b" if (v or 0) >= 40 else "#94a3b8")
        # 钱来式评分进度条：维度分映射为横向填充条，直观拉开强弱差距
        bar = ""
        if v is not None:
            pct = max(0, min(100, int(v)))
            bar = (
                "<div style='height:6px;width:100%;background:rgba(148,163,184,.15);"
                "border-radius:3px;margin-top:5px;overflow:hidden'>"
                f"<div style='height:100%;width:{pct}%;background:{color};border-radius:3px'></div></div>"
            )
        rows += (
            "<div style='padding:7px 0;border-bottom:1px solid rgba(148,163,184,.15);font-size:13px'>"
            "<div style='display:flex;justify-content:space-between'>"
            f"<span><b>{DIM_LABELS[k]}</b> <span style='opacity:.6;font-size:11px'>{_raw_hint[k]}</span></span>"
            f"<span style='font-weight:700;color:{color}'>{val_txt}</span></div>"
            f"{bar}</div>"
        )
    st.markdown(rows, unsafe_allow_html=True)

    miss = [DIM_LABELS[k] for k, v in dims.items() if v is None]
    if miss:
        st.warning(f"⚠️ 以下维度数据缺失，未参与综合分：{'、'.join(miss)}。"
                   "（缺失即明示，不用默认值伪造分数。）")

    st.caption("⚠️ 说明：六维评分为**启发式阈值映射**（区间见 modules/six_dim），非拟合/预测模型；"
               "不同行业估值中枢差异大，价值维参考性有限。不构成投资建议。")
else:
    st.info("👆 输入 6 位代码后点「评分」。")
