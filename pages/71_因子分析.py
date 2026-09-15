"""页面 71：因子分析（G3）

对标 FactorHub / tick-stock-panel 的「因子分析」：IC/IR（截面）、分层收益、多空组合，
直补本项目「策略回测有、因子分析无」的能力断档。

方法（纯逻辑见 ``modules.factor_analysis``）：
- 因子池：动量(20d) / 反转(5d) / 波动率(20d) / 换手率(20d)。
- 截面 IC：每期对（因子值, 未来 h 日收益）求 **Spearman 秩相关**；IR = IC均值 / IC标准差。
- 分层收益：每期按因子分 N 层，看各层未来收益是否**单调**；多空 = 最高层 − 最低层。
- 收益严格用 ``iloc[i+h]``，**后移避免前视泄漏**。

诚实性红线：
  · IC/IR 是**统计描述**，小样本（交易日少 / 标的少）不具统计意义，页面明示样本数；
  · 不预测涨跌、不承诺收益；因子失效是常态，历史有效≠未来有效；
  · 数据取不到/有效标的<3 时**不出结论**，明示原因。
"""
from __future__ import annotations

import logging
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.colors import UP_COLOR, DOWN_COLOR
from modules.factor_analysis import (
    FACTORS, build_panels, cumulative, ic_series, ic_summary, layered_returns, long_short,
)
from modules.page_utils import render_standard_page
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)

DEFAULT_CODES = [
    "600519", "000858", "601318", "600036", "000001", "600030",
    "601012", "002594", "300750", "600900", "601888", "000651",
]
_LAYER_COLORS = ["#1d4ed8", "#0ea5e9", "#22c55e", "#f59e0b", "#dc2626",
                 "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#b45309"]


@st.cache_data(ttl=1800, show_spinner=False)
def _hist_cached(code: str) -> pd.DataFrame:
    """个股日线历史（前复权，缓存 30 分钟）。失败抛出，由 build_panels 逐股兜底。"""
    import akshare as ak
    return ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")


dark = render_standard_page(
    title="因子分析", icon="🧮",
    caption="截面 IC/IR + 分层收益 + 多空组合。因子：动量/反转/波动率/换手。"
            "纯统计描述，非预测；历史有效≠未来有效，请注意样本量。",
)

section_header("参数设置", "标的池越小越快；首次拉取历史行情需数十秒（之后缓存 30 分钟）", icon="⚙️")
codes_txt = st.text_area(
    "标的池（逗号/空格分隔的 6 位代码）",
    value=", ".join(DEFAULT_CODES), key="fa_codes", height=80,
)
c1, c2, c3 = st.columns(3)
factor = c1.selectbox("因子", options=list(FACTORS.keys()),
                      format_func=lambda k: FACTORS[k], key="fa_factor")
days = c2.slider("回看交易日", 60, 250, 120, key="fa_days")
n_layers = c3.slider("分层数", 3, 10, 5, key="fa_layers")
forward = st.slider("持有期 h（用 t 日因子预测 t+h 日收益）", 1, 10, 1, key="fa_forward")

if st.button("🚀 运行分析", key="fa_run", type="primary"):
    codes = [c for c in re.split(r"[,\s;，、]+", codes_txt) if c.strip()]
    if len(codes) < 3:
        st.warning("请至少提供 3 个有效代码。")
        st.stop()
    with st.spinner("拉取历史行情并计算 IC / 分层 / 多空…"):
        try:
            fp, ret, errs = build_panels(codes, days, factor, _hist_cached)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[factor] 面板构建失败: {e}")
            st.error("⚠️ 数据获取失败（网络不可用或接口异常），请稍后重试。")
            st.stop()
    if fp is None:
        st.warning("有效标的不足 3 只，无法计算截面 IC（诚实不出结论）。")
        if errs:
            st.caption("失败明细：" + "；".join(f"{c}:{m}" for c, m in errs[:12]))
        st.stop()

    ic = ic_series(fp, ret, forward=forward)
    summ = ic_summary(ic)
    lay = layered_returns(fp, ret, n_layers=int(n_layers), forward=forward)
    ls = long_short(lay)

    st.markdown("---")
    section_header("IC / IR 汇总", f"因子「{FACTORS.get(factor, factor)}」· 截面 Spearman", icon="📐")
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        sf_metric("IC 均值", f"{summ['ic_mean']:.3f}" if summ["n"] else "—", "越靠近 ±1 越强")
    with k2:
        sf_metric("IR", f"{summ['ir']:.2f}" if summ["n"] else "—", "IC均值/标准差")
    with k3:
        sf_metric("IC 胜率", f"{summ['positive_ratio'] * 100:.0f}%" if summ["n"] else "—", "IC>0 占比")
    with k4:
        sf_metric("t 值", f"{summ['t_stat']:.2f}" if summ["n"] else "—", "|t|>2 方具统计意义")
    with k5:
        sf_metric("样本期数", str(summ["n"]), "越小越不可信")
    if summ["n"] and summ["n"] < 20:
        st.warning(f"⚠️ 仅 {summ['n']} 期样本，**统计意义不足**；结论仅供参考，勿据此下注。")

    if not ic.empty:
        fig_ic = go.Figure(go.Bar(
            x=[str(d)[:10] for d in ic.index], y=ic.values,
            marker_color=[UP_COLOR if v >= 0 else DOWN_COLOR for v in ic.values],
        ))
        fig_ic.update_layout(template="plotly_dark" if dark else "plotly_white",
                             height=260, margin=dict(l=10, r=10, t=30, b=10),
                             title="逐期截面 IC", yaxis_title="IC", showlegend=False)
        st.plotly_chart(fig_ic, width="stretch")

    st.markdown("---")
    section_header("分层收益", f"按因子分 {n_layers} 层，看未来收益是否单调（0=因子最小层）", icon="📊")
    if lay is not None and not lay.empty:
        cum = cumulative(lay)
        fig_lay = go.Figure()
        cols = sorted(cum.columns, key=lambda c: int(c))
        for i, c in enumerate(cols):
            fig_lay.add_trace(go.Scatter(
                x=[str(d)[:10] for d in cum.index], y=cum[c].values, mode="lines",
                name=f"第 {int(c) + 1} 层", line=dict(color=_LAYER_COLORS[i % len(_LAYER_COLORS)]),
            ))
        fig_lay.update_layout(template="plotly_dark" if dark else "plotly_white",
                              height=340, margin=dict(l=10, r=10, t=30, b=10),
                              yaxis_title="累计收益", legend=dict(orientation="h"))
        st.plotly_chart(fig_lay, width="stretch")
        # 单调性提示：末层 vs 首层累计
        top_c, bot_c = cum[cols[-1]].iloc[-1], cum[cols[0]].iloc[-1]
        if top_c > bot_c:
            st.success(f"✅ 最高层累计 {top_c * 100:+.1f}% > 最低层 {bot_c * 100:+.1f}% —— 因子方向与收益**同向**（历史）。")
        else:
            st.warning(f"⚠️ 最高层累计 {top_c * 100:+.1f}% ≤ 最低层 {bot_c * 100:+.1f}% —— 该因子在本视角下**方向失效**。")
    else:
        st.info("分层收益样本不足，无法绘图。")

    st.markdown("---")
    section_header("多空组合", "最高层 − 最低层；看因子多空价差是否稳定为正", icon="↕️")
    if not ls.empty:
        ls_cum = (1.0 + ls.fillna(0.0)).cumprod() - 1.0
        fig_ls = go.Figure(go.Scatter(
            x=[str(d)[:10] for d in ls_cum.index], y=ls_cum.values, mode="lines",
            line=dict(color=UP_COLOR),
        ))
        fig_ls.update_layout(template="plotly_dark" if dark else "plotly_white",
                             height=280, margin=dict(l=10, r=10, t=30, b=10),
                             yaxis_title="多空累计收益", showlegend=False)
        st.plotly_chart(fig_ls, width="stretch")
        st.caption(f"多空累计 **{ls_cum.iloc[-1] * 100:+.1f}%**（{len(ls)} 期）")
    else:
        st.info("多空组合样本不足。")

    if errs:
        with st.expander(f"⚠️ {len(errs)} 个标的取数失败（未纳入）"):
            st.write("；".join(f"{c}: {m}" for c, m in errs))

    st.caption("⚠️ 说明：IC/IR、分层、多空均为**历史统计描述**，非预测模型，不构成投资建议；"
               "小样本不具统计意义，因子失效是常态。收益严格后移 h 日计算，无前视泄漏。")
else:
    st.info("👆 设置参数后点「运行分析」。首次拉取 12 只标的历史行情约需数十秒，之后走 30 分钟缓存。")
