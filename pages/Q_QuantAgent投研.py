"""
pages/Q_QuantAgent投研.py
-------------------------
QuantAgent 多智能体投研 · StockSignal 新页面

把 QuantAgent 框架接入 StockSignal 前端：输入股票代码，一键发起
「数据→基本面→技术面→舆情→风控→(人工复核)→FinRAG复盘→首席决策」多智能体投研。
耗时推理走后端「任务提交 + 轮询」通道（POST /api/tasks → GET /api/tasks/<id>），
不阻塞 UI；同时保留本地直跑模式便于调试。

运行：streamlit run app.py  →  侧边栏「Q_QuantAgent投研」
"""

from __future__ import annotations

import time

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None

st.set_page_config(page_title="QuantAgent 多智能体投研", page_icon="🤖", layout="wide")

_VERDICT_COLOR = {"看多": "#009e60", "看空": "#dc2626"}


def _verdict_color(v: str) -> str:
    return _VERDICT_COLOR.get(v, "#d97706")


@st.cache_data(ttl=1)
def _poll_once(task_id: str):
    """缓存 1 秒：避免 fragment 重跑时请求堆积。"""
    from modules.background_tasks import poll_task

    return poll_task(task_id, max_wait=0.5)


def _render_report(result: dict):
    """渲染一份 QuantAgent 投研结果（result 即 ResearchState.to_dict()）。"""
    c = result.get("chief_report", {}) or {}

    # 首席结论（突出）
    vc = _verdict_color(c.get("verdict", ""))
    st.markdown(
        f"<div style='padding:14px 18px;border-left:6px solid {vc};background:#f6f8fc;border-radius:8px'>"
        f"<b style='font-size:20px;color:{vc}'>🏁 最终结论：{c.get('verdict','-')}</b> "
        f"&nbsp; 综合评分 <b>{c.get('composite','-')}</b>/100"
        + (f"<br>目标价 <b>¥{c.get('target_price')}</b> ｜ 止损 <b>¥{c.get('stop_price')}</b>" if c.get("target_price") else "")
        + f"<br><span style='color:#5b6472'>{c.get('rationale','')}</span></div>",
        unsafe_allow_html=True,
    )

    # 环境标签
    env = []
    env.append("真实数据" if result.get("used_real_data") else "合成数据(离线)")
    env.append("LLM" if result.get("used_llm") else "规则引擎")
    if result.get("used_browser"):
        env.append("FinBrowser")
    if result.get("used_rag"):
        env.append("FinRAG")
    if result.get("approval"):
        env.append("已人工复核")
    st.caption("环境：" + " / ".join(env))

    st.divider()

    # 各 Agent 报告
    cols = st.columns(2)
    with cols[0]:
        st.subheader("📈 技术面")
        st.write((result.get("technical_report") or {}).get("text", ""))
        st.subheader("💬 舆情")
        st.write((result.get("sentiment_report") or {}).get("text", ""))
    with cols[1]:
        st.subheader("🏢 基本面")
        st.write((result.get("fundamental_report") or {}).get("text", ""))
        st.subheader("🛡️ 风控")
        st.write((result.get("risk_report") or {}).get("text", ""))

    # 复盘记忆
    if result.get("rag_context"):
        with st.expander("🧠 FinRAG 复盘记忆 / 相关研报"):
            st.text(result["rag_context"])

    # 运行轨迹
    with st.expander("🪵 多智能体执行轨迹"):
        for t in result.get("trace", []) or []:
            st.markdown(f"- **{t.get('node')}**: {t.get('log')}")

    if result.get("errors"):
        with st.expander("⚠️ 运行提示"):
            for e in result["errors"]:
                st.warning(e)


@st.fragment
def _result_panel():
    """结果区：轮询后台任务 / 渲染本地直跑结果，独立 fragment 不阻塞整页。"""
    task_id = st.session_state.get("quant_task_id")
    if task_id:
        task = _poll_once(task_id)
        if task and task.get("status") == "success":
            st.session_state["quant_result"] = task.get("result")
            del st.session_state["quant_task_id"]
            st.toast("✅ 投研完成")
        elif task and task.get("status") == "error":
            st.error(f"投研失败：{task.get('error')}")
            del st.session_state["quant_task_id"]
            return
        elif task and task.get("status") in ("pending", "running"):
            st.warning("⏳ 多智能体后台协作中... 完成后会自动显示结果，无需切换页面。", icon="⏳")
            st.progress(0.0, text="多智能体推理中...")
            if st_autorefresh is not None:
                st_autorefresh(interval=1000, limit=180, key="quant_autorefresh")
            else:
                time.sleep(1.0)
                st.rerun()
            return

    if st.session_state.get("quant_result") is not None:
        _render_report(st.session_state["quant_result"])


def main():
    st.title("🤖 QuantAgent · 多智能体 A股投研")
    st.caption("数据底座复用 StockSignal（StockFetcher/technical/signal/news/backtest）+ FinBrowser 采集外挂 + FinRAG 记忆/RAG 模块")

    ticker = st.text_input("股票代码", value="600519", help="6 位 A股代码，如 600519 / 000001")

    col1, col2 = st.columns([1, 3])
    with col1:
        mode = st.radio("运行模式", ["任务通道（推荐）", "本地直跑（调试）"], horizontal=True,
                        help="任务通道：提交到后端 5050 异步执行并轮询，不阻塞 UI；直跑：前端进程内同步执行。")
    with col2:
        engine = st.selectbox("编排引擎", ["auto", "langgraph", "simple"],
                              help="auto=装了 LangGraph 用真实编排否则回退；langgraph=强制真实 LangGraph（条件路由+人工审批）；simple=零依赖图。")
        use_browser = st.checkbox("启用 FinBrowser 采集外挂", value=True)
        use_rag = st.checkbox("启用 FinRAG 记忆/RAG", value=True)
        force_human = st.checkbox("强制人工复核（HITL 演示）", value=False,
                                  help="高风险或勾选时，编排会在风控后插入人工审批节点（LangGraph interrupt）。")

    run = st.button("发起多智能体投研", type="primary", use_container_width=True)

    if not run:
        st.info("点击按钮，由 5 个分析智能体 + 1 个首席决策智能体协作产出投研报告。无 LLM Key 时自动走规则引擎，仍可完整演示。耗时推理走后端任务通道，不阻塞页面。")
        _result_panel()
        return

    if not ticker or len(ticker) != 6 or not ticker.isdigit():
        st.warning("请输入 6 位数字的 A股代码。")
        return

    payload = {
        "ticker": ticker,
        "use_browser": bool(use_browser),
        "use_rag": bool(use_rag),
        "engine": str(engine),
        "force_human_review": bool(force_human),
        "human_approval_enabled": bool(force_human),
    }

    if mode.startswith("任务"):
        try:
            from modules.background_tasks import submit_task_with_error

            task_id, err = submit_task_with_error("quant_research", payload)
            if task_id:
                st.session_state["quant_task_id"] = task_id
                st.session_state["quant_result"] = None
                st.info("📡 投研任务已提交到后台运行，可切到其他页面，完成后会自动显示结果。")
            else:
                st.error(f"提交失败：{err}（请确认后端 5050 已启动）")
        except Exception as e:
            st.error(f"任务通道不可用：{e}（请确认后端 5050 已启动，或改用本地直跑模式）")
    else:
        # 本地直跑（阻塞，仅调试）
        try:
            from modules.quantagent import run_research

            with st.spinner("多智能体协作中（本地直跑）..."):
                state = run_research(
                    ticker,
                    use_browser=bool(use_browser),
                    use_rag=bool(use_rag),
                    engine=str(engine),
                    force_human_review=bool(force_human),
                    human_approval_enabled=bool(force_human),
                )
            st.session_state["quant_result"] = state.to_dict()
        except Exception as e:
            import traceback

            st.exception(e)

    _result_panel()


if __name__ == "__main__":
    main()
