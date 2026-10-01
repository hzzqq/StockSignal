"""pages/84_宏观数据.py — 宏观指标看板（补 app.py 承诺已久的空白）。

``app.py`` 的功能表写着「宏观数据 | PMI、CPI、社融等关键宏观指标」，
但一直没有对应页面；投研圆桌的历史交付物也反复标注「宏观 PMI / 社融未取到，
下一轮需补宏观景气与政策变量」。本页把这块补上。

2026-09 扩展：新增 12 个全球指标（美国宏观 / 美债 / 美元 / 汇率 / 美股港股），
并按「国内 / 全球」分组；顶部增加「全球风险偏好 / 流动性评分」卡片。

红线：
- 取不到的指标显示「取不到」，**不臆造数值**。
- 「通俗解读」与「全球风险评分」是 modules.macro_data 里**规则生成**的确定性结论，
  不是大模型输出，页面上明确标注，避免把一行 if/else 当 AI 洞见。
"""
from __future__ import annotations

import streamlit as st

from modules.page_utils import render_standard_page
from modules import macro_data as md


@st.cache_data(ttl=3600, show_spinner="正在拉取宏观数据…")
def _load() -> dict:
    return md.fetch_all()


@st.cache_data(ttl=3600, show_spinner="正在计算全球风险评分…")
def _load_regime() -> dict | None:
    return md.global_regime_score()


def _render_card(spec: dict, item):
    with st.container(border=True):
        st.markdown(f"**{spec['name']}**　`{spec['freq']}度` · {spec['source']}")
        if not item:
            st.warning("取不到（不臆造）")
            st.caption("口径：" + spec["desc"])
            return
        delta = (f"{item['change']:+.2f}"
                 if item.get("change") is not None else None)
        st.metric(
            "最新值",
            f"{item['value']}{item['unit']}",
            delta=delta,
            # A 股惯例：涨红跌绿 → inverse（正红负绿）
            delta_color="inverse",
        )
        st.caption(
            f"数据日期 {item['date']}　"
            f"前值 {item['prev'] if item['prev'] is not None else '—'}"
        )
        st.caption("口径：" + item["desc"])
        st.markdown(
            "**解读（规则）：** "
            + md.interpret(spec["key"], item["value"], item["prev"])
        )


def _render_section(title: str, emoji: str, specs, data):
    st.subheader(f"{emoji} {title}")
    specs = list(specs)
    for i in range(0, len(specs), 2):
        cols = st.columns(2)
        for j, spec in enumerate(specs[i:i + 2]):
            with cols[j]:
                _render_card(spec, data.get(spec["key"]))


def main() -> None:
    render_standard_page(title="宏观数据", icon="🌍", layout="wide")

    st.caption(
        "数据源：akshare（国家统计局 / 央行 / 美国劳工部 / 美联储 / 东方财富 / 外汇交易中心）。"
        "「通俗解读」与「全球风险评分」均为 **规则生成的确定性结论**，不是大模型输出，请勿当作 AI 洞见。"
    )

    data = _load()
    ok_n = sum(1 for v in data.values() if v)
    total_n = len(data)
    if ok_n == 0:
        st.error(
            "全部宏观指标都取不到（akshare 不可用或网络受限）。"
            "这里**不会**用示例数据填充——请检查 akshare 安装与网络后重试。"
        )
    else:
        st.info(f"成功取到 {ok_n}/{total_n} 个宏观指标；未取到的显示「取不到」，不臆造。")

    # ---- 全球风险偏好 / 流动性评分卡片 ----
    regime = _load_regime()
    if regime is not None:
        score = regime["score"]
        band = ("宽松·风险偏好高" if score >= 60 else
                "中性" if score >= 45 else "收紧·风险偏好低")
        st.success(
            f"🌐 **全球风险偏好 / 流动性评分：{score} / 100**（{band}）　"
            f"分项：DXY {regime['sub'].get('dxy')} · 美债10Y {regime['sub'].get('us_treasury_10y')} · "
            f"美国CPI {regime['sub'].get('us_cpi')} · USD/CNY {regime['sub'].get('usd_cny')}"
        )
        st.caption("评分规则化合成（弱美元+低美债+低通胀+人民币偏强→高分），详见 modules.macro_data.global_regime_score。")
    else:
        st.info("全球风险评分所需的分项（美元指数 / 美债 / 美国CPI / 汇率）暂时都取不到，不臆造评分。")

    # ---- 国内 / 全球 分组 ----
    domestic = [m for m in md.MACRO_INDICATORS if m.get("region") == "国内"]
    global_ = [m for m in md.MACRO_INDICATORS if m.get("region") == "全球"]

    _render_section("国内宏观", "🇨🇳", domestic, data)
    st.divider()
    _render_section("全球宏观（美股 / 美债 / 美元 / 汇率）", "🌐", global_, data)


main()
