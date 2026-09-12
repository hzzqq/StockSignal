"""
页面 60：事件对比分析 · 信号强弱 × 市场广度 对照

把 P1-QuantFactor EV 模型的「个股级信号池」（看多/看空 + score）与当日全市场广度
（红盘率 / 涨跌家数 / 涨跌停）并置，做「信号极性 × 广度状态」的截面对照，
判断信号与广度是否同向 / 是否逆向抄底。

数据边界（诚实声明，页面内可见）：
  · 事件因子池是离线快照，无历史事件日期、无逐股后续涨跌 → 本页**不**做事件→股价因果回测；
  · 仅做「信号强弱 vs 当下广度」对照，供快速识别「共振 / 背离 / 逆向」结构。
"""
import logging

import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, section_header
from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules import event_compare as ec

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="事件对比分析 · 信号 × 广度 对照", icon="🔍",
    caption="P1-QuantFactor EV 信号池（看多/看空 + 强度）与当日全市场广度并置对照，"
            "识别「共振 / 背离 / 逆向」结构。信号池为离线快照、无历史事件日期，本页不做事件→股价因果回测。",
)

try:
    # ── 取数（各自优雅降级）──
    pool = ec.load_event_pool()
    breadth = ec.current_breadth()
    cmp = ec.signal_breadth_compare(pool_result=pool, breadth=breadth)
    rows = ec.build_compare_rows(pool_result=pool, breadth=breadth)

    # ── 顶部：两源快照卡片 ──
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📡 事件信号池")
        st.markdown(sf_card(
            title=f"P1 EV 信号池（{cmp['pool_date'] or '—'}）"
                   f"{' · 🔴 LIVE' if cmp['pool_live'] else (' · 📦 离线' if cmp['pool_available'] else ' · ⚠️ 不可用')}"
                   f"{' · 数据偏旧' if cmp['pool_stale'] else ''}",
            body=f"共 <b>{cmp['n']}</b> 只信号 ｜ 看多 <b style='color:{UP_COLOR}'>{cmp['bull']}</b> "
                 f"／ 看空 <b style='color:{DOWN_COLOR}'>{cmp['bear']}</b><br>"
                 f"看多占比 <b>{('-' if cmp['bull_pct'] is None else f'{cmp['bull_pct']:.0f}%')}</b> ｜ "
                 f"看多均分 {('-' if cmp['bull_score_avg'] is None else f'{cmp['bull_score_avg']:.1f}')} ／ "
                 f"看空均分 {('-' if cmp['bear_score_avg'] is None else f'{cmp['bear_score_avg']:.1f}')}",
        ), unsafe_allow_html=True)
    with c2:
        st.markdown("### 🌐 当日市场广度")
        if cmp["breadth_available"]:
            st.markdown(sf_card(
                title=f"牧羊人广度（{cmp['breadth_date']}）",
                body=f"红盘率 <b>{cmp['red_ratio']:.1f}%</b> ｜ 上涨 {cmp['up_count']} ／ 下跌 {cmp['down_count']}<br>"
                     f"涨停 {cmp['limit_up']} ／ 跌停 {cmp['limit_down']}",
            ), unsafe_allow_html=True)
        else:
            st.warning(f"⚠️ 广度数据不可用：{cmp['breadth_note'] or '无数据'}")

    # ── 对照结论条 ──
    st.markdown("### 🧭 信号 × 广度 对照结论")
    kind = cmp["alignment_kind"]
    color = {"momentum": UP_COLOR, "contrarian": "#36c5d8",
             "diverge_hot": DOWN_COLOR, "cautious": "#ca8a04",
             "unknown": "#94a3b8"}.get(kind, "#94a3b8")
    st.markdown(sf_card(
        title="结构判定",
        body=f"<b style='color:{color}'>{cmp['alignment']}</b>",
        accent=color,
    ), unsafe_allow_html=True)
    st.caption("判定仅基于「看多信号占比」与「当日红盘率」两个可观测量的关系，不含任何未来预测。")

    # ── 对照表 ──
    st.markdown("### 📋 信号-广度对照表（按强度降序）")
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows)
        df_disp = df.rename(columns={
            "rank": "排名", "symbol": "代码", "signal": "信号",
            "score": "强度", "source": "来源", "market_red_ratio": "当日红盘率(%)",
        })
        # 信号着色（A股：看多=红 / 看空=绿）
        def _sig_color(v):
            return f"color:{UP_COLOR}" if str(v) == "看多" else f"color:{DOWN_COLOR}"
        st.dataframe(
            df_disp.style.applymap(_sig_color, subset=["信号"]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("事件因子池为空或不可用，无可对照信号。")

    # ── 方法学声明 ──
    st.markdown("---")
    st.caption(
        "📐 方法学：事件因子池（data/event_pool_brief.json）为 P1-QuantFactor EV 模型的个股级信号快照，"
        "含 symbol / 信号极性 / 强度 score，但**不含历史事件日期、不含逐股后续涨跌**。本页仅将信号强弱与"
        "当日全市场广度（红盘率/涨跌家数/涨跌停）并置，做「极性 × 广度状态」截面对照，用于识别共振/背离/逆向。"
        "不做、也无法做「事件→股价因果回测」——后者需逐股历史价格，离线基座无此数据。"
    )

except Exception as exc:  # noqa: BLE001 - 页面级兜底，避免整页崩溃
    logger.exception("事件对比分析页渲染失败")
    st.error(f"⚠️ 页面渲染异常：{exc}")
