"""pages/84_宏观数据.py — 宏观指标看板（补 app.py 承诺已久的空白）。

``app.py`` 的功能表写着「宏观数据 | PMI、CPI、社融等关键宏观指标」，
但一直没有对应页面；投研圆桌的历史交付物也反复标注「宏观 PMI / 社融未取到，
下一轮需补宏观景气与政策变量」。本页把这块补上。

红线：
- 取不到的指标显示「取不到」，**不臆造数值**。
- 「通俗解读」是 modules.macro_data.interpret 的**规则生成**结论，不是大模型输出，
  页面上明确标注，避免把一行 if/else 当 AI 洞见。
"""
from __future__ import annotations

import streamlit as st

from modules.page_utils import render_standard_page
from modules import macro_data as md


@st.cache_data(ttl=3600, show_spinner="正在拉取宏观数据…")
def _load() -> dict:
    return md.fetch_all()


def main() -> None:
    render_standard_page(title="宏观数据", icon="🌍", layout="wide")

    st.caption(
        "数据源：akshare（国家统计局 / 央行）。"
        "「通俗解读」为 **规则生成的确定性结论**，不是大模型输出，请勿当作 AI 洞见。"
    )

    data = _load()
    ok_n = sum(1 for v in data.values() if v)
    if ok_n == 0:
        st.error(
            "全部宏观指标都取不到（akshare 不可用或网络受限）。"
            "这里**不会**用示例数据填充——请检查 akshare 安装与网络后重试。"
        )
    else:
        st.info(f"成功取到 {ok_n}/{len(data)} 个宏观指标；未取到的显示「取不到」，不臆造。")

    specs = md.MACRO_INDICATORS
    for i in range(0, len(specs), 2):
        cols = st.columns(2)
        for j, spec in enumerate(specs[i:i + 2]):
            item = data.get(spec["key"])
            with cols[j]:
                with st.container(border=True):
                    st.markdown(f"**{spec['name']}**　`{spec['freq']}度` · {spec['source']}")
                    if not item:
                        st.warning("取不到（不臆造）")
                        st.caption("口径：" + spec["desc"])
                        continue
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


main()
