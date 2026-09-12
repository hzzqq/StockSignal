"""
页面 59：市场温度计 · 极端区历史回测

把牧羊人 8 指标合成 0-100 综合「市场温度」，配五档分档（冰点/偏冷/中性/活跃/狂热）；
叠加两大历史回测能力：
  · 极端区信号：极端恐慌 → 次日红盘（sentiment_edge 已实证 z=+4.36，可发布）；
  · 历史情境类比：对今日广度向量在全历史找最近相似日（market_regime，无前视泄漏）。

实时数据来自 get_shepherd_today；缺失优雅降级；历史类比基于 4771 天广度真值。
温度是描述性指标（市场当前冷热），不声称预测能力。
"""
import logging

import streamlit as st
import plotly.graph_objects as go

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, section_header
from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules import market_temperature as mt
from modules import shepherd

logger = logging.getLogger(__name__)

dark = render_standard_page(
    title="市场温度计 · 极端区历史回测", icon="🌡️",
    caption="牧羊人 8 指标合成 0-100 综合温度 + 五档分档；叠加极端恐慌反弹信号与历史相似日回看。"
            "温度是描述性指标，不声称预测能力。",
)

try:
    # ── 侧边栏：温度基准窗口 ──
    window = st.sidebar.selectbox(
        "温度基准窗口",
        options=[("近一季 (60 日)", 60), ("近一年 (250 日)", 250), ("全历史 (2007 起)", 2000)],
        index=2, format_func=lambda x: x[0],
    )
    hist_days = window[1]

    # ── 实时数据（网络受限时各指标独立降级）──
    today, meta = shepherd.get_shepherd_today()
    avail = meta.get("available", [])
    unavail = meta.get("unavailable", [])
    st.info(
        f"📡 实时指标：可用 **{len(avail)}** 项，缺失 **{len(unavail)}** 项"
        f"（缺失指标不参与温度打分，温度按实际可得项合成）。"
    )

    detail = mt.temperature_contributions(today, hist_days=hist_days)
    temp = detail["temp"]
    band = mt.temperature_band(temp)
    contributions = detail["contributions"]

    if not contributions:
        st.warning("⚠️ 当前实时指标全部缺失，无法合成有效温度（按安全默认 50° 展示）。请稍后重试或检查数据源。")

    # ── 温度计 gauge ──
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(temp, 1),
        number={"font": {"size": 46, "color": band["color"]}, "suffix": "°"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#94a3b8",
                     "tickfont": {"color": "#94a3b8"}},
            "bar": {"color": band["color"], "thickness": 0.28},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 1,
            "bordercolor": "#475569",
            "steps": [
                {"range": [0, 20], "color": "#1d4ed8"},
                {"range": [20, 40], "color": "#0891b2"},
                {"range": [40, 60], "color": "#ca8a04"},
                {"range": [60, 80], "color": "#ea580c"},
                {"range": [80, 100], "color": "#b91c1c"},
            ],
            "threshold": {"line": {"color": band["color"], "width": 5},
                          "thickness": 0.85, "value": round(temp, 1)},
        },
        title={"text": f"当前市场温度 · {band['label']}",
               "font": {"size": 18, "color": band["color"]}},
    ))
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=330, margin=dict(l=20, r=20, t=55, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb" if dark else "#1f2937"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"💡 {band['advice']}")

    # ── 分档图例 ──
    legend_html = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:12px">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:{b["color"]}"></span>'
        f'{b["label"]}（{b["lo"]}–{b["hi"]-1 if b["hi"]<=100 else 100}°）</span>'
        for b in mt.BANDS
    )
    st.markdown(
        f'<div style="margin:2px 0 14px">{legend_html}</div>',
        unsafe_allow_html=True,
    )

    # ── 各指标贡献 ──
    if contributions:
        section_header("各指标热度贡献", "单个牧羊人指标在所选历史窗口中的经验分位热度（0=最冷，100=最热）", icon="🔥")
        names = [f'{c["name"]} {c["value"]:.0f}{c["unit"]}' for c in contributions]
        heats = [c["heat"] for c in contributions]
        colors = [mt.temperature_band(h)["color"] for h in heats]
        fig_c = go.Figure(go.Bar(
            x=heats, y=names, orientation="h",
            marker_color=colors,
            text=[f'{h:.0f}°' for h in heats], textposition="outside",
        ))
        fig_c.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=max(220, 38 * len(names) + 60), margin=dict(l=10, r=40, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb" if dark else "#1f2937"),
            xaxis=dict(range=[0, 108], title="热度"),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_c, use_container_width=True)
        st.caption("方向说明：↑ 指标越高越热（如涨停家数）；↓ 指标越低越热（如跌停家数）。缺失指标不计入。")

    # ── 极端区信号 ──
    section_header("极端区信号", "极端恐慌 → 次日反弹（唯一经全历史实证的统计边际）", icon="⚠️")
    sig = mt.extreme_zone_signal(today)
    if not sig.get("available"):
        st.warning(f"极端区信号校准件不可用：{sig.get('reason', '未知')}。本次不做方向表态。")
    elif sig.get("triggered"):
        prob = sig.get("prob")
        base = sig.get("base_rate")
        edge = sig.get("edge_pp")
        hit = sig["hits"][0] if sig.get("hits") else {}
        st.markdown(
            f"""
            <div style="border-left:6px solid #dc2626;background:{_hex_to_rgba('#dc2626', 0.12)};
            border-radius:10px;padding:14px 18px;margin-bottom:10px;font-size:13px">
              <div style="font-size:14px;font-weight:800;color:#dc2626">⚠️ 恐慌出清反弹信号触发</div>
              <div style="margin-top:6px">{sig.get('statement', '')}</div>
              <div style="margin-top:6px;opacity:.8">样本 {hit.get('n')} 天 · z={hit.get('z')} · 边际 +{edge}pp</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # 未触发 / 无法判定：诚实区分「看了没到极值」与「根本没法看」
        st.info(sig.get("statement", "当前未进入历史极值区间，不做方向表态。"))

    # ── 历史情境类比 ──
    section_header("历史情境类比", "与今日广度向量最相似的交易日，及其后 5/10/20 日真实表现", icon="🕰️")
    st.caption("⚠️ 历史相似 ≠ 预测。下表为相似日之后真实市场表现统计，仅供情境参照（无前视泄漏）。")
    ana = mt.historical_analogs(today, k=8)
    if not ana.get("available"):
        st.warning(f"历史情境类比不可用：{ana.get('reason', '未知')}")
    else:
        tm = ana.get("today_metrics", {})
        st.info(
            f"📅 今日广度：红盘率 {tm.get('red_ratio')} · 涨停 {tm.get('limit_up')} · 跌停 {tm.get('limit_down')}；"
            f"以下为全历史中最相似的 {len(ana['analogs'])} 个交易日。"
        )
        analogs = ana["analogs"]
        if not analogs:
            st.caption("（无可用相似日）")
        cols = st.columns(max(1, min(len(analogs), 4)))
        for idx, a in enumerate(analogs):
            col = cols[idx % 4]
            with col:
                ac = mt.temperature_band(50)["color"]  # 中性灰蓝，避免与温度语义混用
                f5 = a["forward"].get("d5", {})
                f10 = a["forward"].get("d10", {})
                f20 = a["forward"].get("d20", {})
                up5 = f5.get("up_frac")
                up5_color = UP_COLOR if (up5 is not None and up5 > 0.5) else DOWN_COLOR
                st.markdown(
                    f"""
                    <div style="border:1px solid {_hex_to_rgba(ac,0.5)};border-left:4px solid {ac};
                    border-radius:8px;padding:10px 12px;margin-bottom:8px;font-size:12px">
                      <div style="font-weight:700;color:{ac}">{a['date']}</div>
                      <div style="opacity:.7">相似距离 {a['distance']:.3f} · 状态 {a['state']}</div>
                      <div style="margin-top:4px">后5日 红盘率均值 <b>{f5.get('avg_red','—')}</b></div>
                      <div>后5日 上涨日占比 <b style="color:{up5_color}">{up5 if up5 is None else f'{up5*100:.0f}%'}</b></div>
                      <div style="opacity:.7">后10日红盘均值 {f10.get('avg_red','—')} · 后20日 {f20.get('avg_red','—')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    sf_card(
        "方法学与诚实声明",
        "温度为**描述性**指标：把牧羊人指标按其在历史窗口中的经验分位合成 0-100 热度（跨年代可比），"
        "分五档（冰点/偏冷/中性/活跃/狂热）。**温度不预测涨跌**，仅刻画当前市场冷热。"
        "极端区信号仅「极端恐慌→次日红盘」这一条有统计依据（全历史 296 天，z=+4.36，可发布）；"
        "其余时刻本模块明确弃权。历史情境类比复用市场状态机的无前视泄漏检索（只回看目标日之前），"
        "相似≠预测。所有结论基于已修复的 4771 天广度真值，未使用任何缺失字段。",
        icon="📐",
    )

except Exception as e:  # noqa: BLE001
    logger.exception("[59_市场温度计] 渲染失败")
    st.error(f"页面渲染失败：{e}")
