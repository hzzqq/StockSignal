# -*- coding: utf-8 -*-
"""pages/99_决策问答.py — T-327 方向C：自然语言决策端。

用户以自然语言问决策问题（今天仓位多少/为什么/该注意什么），本地决策问答引擎
（modules/decision_qa.py）确定性意图路由 → 归档数据取数 → 带溯源的可解释回答。

诚实边界：只引用归档数据（快照/荐股/归档链），无数据如实 unavailable 不实时臆算；
意图不明给引导不编造；建议≠交易；纯本地模板不依赖 LLM。
"""
from __future__ import annotations

import logging

import streamlit as st

from modules import decision_qa as qa
from modules.page_utils import render_standard_page

logger = logging.getLogger(__name__)

render_standard_page(
    "决策问答", "🗣️",
    caption="用一句话问决策：仓位多少 / 为什么 / 市场怎么样 / 该注意什么（本地引擎 · 只引用归档数据）")

st.caption("本页不调用外部大模型：回答由本地决策问答引擎从当日快照、荐股与归档数据直接生成，"
           "每条回答附数据溯源。想问开放式研究问题请用「星辰AI」。")

QUICK = [
    "今天仓位多少？",
    "为什么是这个仓位？",
    "市场温度/情绪周期怎么样？",
    "今日推荐有哪些？",
    "近期复盘怎么看？",
    "有什么要注意的风险？",
]


@st.fragment
def render_answer(question: str) -> None:
    result = qa.answer(question)
    if result.get("status") != "ok":
        st.warning(f"⚠️ {result.get('reason', '该问题暂不可答')}")
        st.caption("决策问答只引用已归档数据，无数据不臆算——生成当日快照后即可作答。")
        return
    st.markdown(result.get("answer") or "")
    sources = result.get("sources") or []
    if sources:
        st.caption("📎 溯源：" + "　|　".join(sources))
    if result.get("intent") == "fallback":
        st.info("💡 想问开放式问题（个股研究/事件影响/宏观）？去「星辰AI」页，"
                "那边支持多步工具调用与 [S#] 引用溯源。")


def main() -> None:
    if "qa_history" not in st.session_state:
        st.session_state["qa_history"] = []

    q = st.text_input("你的问题", placeholder="例：今天仓位多少？为什么？",
                      key="decision_qa_input")
    clicked = None
    cols = st.columns(3)
    for i, item in enumerate(QUICK):
        with cols[i % 3]:
            if st.button(item, key=f"qa_quick_{i}"):
                clicked = item

    question = (clicked or "").strip() or q.strip()
    if question:
        st.divider()
        st.markdown(f"**问：** {question}")
        render_answer(question)
        hist = st.session_state["qa_history"]
        if not hist or hist[-1] != question:
            hist.append(question)
            st.session_state["qa_history"] = hist[-5:]
    elif st.session_state["qa_history"]:
        st.caption("最近问过：" + " / ".join(reversed(st.session_state["qa_history"][-3:])))


main()
