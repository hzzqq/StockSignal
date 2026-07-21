"""
pages/Q_QuantAgent投研.py
-------------------------
QuantAgent 多智能体投研 · StockSignal 新页面（精致版）

把 QuantAgent 框架接入 StockSignal 前端：输入股票代码，一键发起
「数据→基本面→技术面→舆情→风控→FinRAG复盘→首席决策（CrewAI 多首席辩论）」
多智能体投研，并以「实时协作进度条」可视化每个 Agent 的工作状态与日志流。

耗时推理走后端「任务提交 + 轮询」通道（POST /api/tasks → GET /api/tasks/<id>），
进度通过 task.progress / task.stage / task.logs 实时回传，不阻塞 UI。
同时保留本地直跑模式便于调试。

运行：streamlit run app.py  →  侧边栏「Q_QuantAgent投研」
"""

from __future__ import annotations

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None

# 多智能体阶段定义（与后端进度总线共用语义）
try:
    from modules.quantagent.progress import AGENT_FLOW, DEBATE_STAGES, label_for, stage_index
except Exception:  # pragma: no cover - fallback
    AGENT_FLOW = [
        ("data", "📡", "数据采集", "DataAgent"),
        ("fundamental", "🏢", "基本面分析", "FundamentalAgent"),
        ("technical", "📈", "技术面分析", "TechnicalAgent"),
        ("sentiment", "💬", "舆情分析", "SentimentAgent"),
        ("risk", "🛡️", "风控评估", "RiskAgent"),
        ("rag_inject", "🧠", "FinRAG 复盘记忆", "FinRAG"),
        ("chief", "🏁", "首席决策", "ChiefAgent"),
    ]
    DEBATE_STAGES = [
        ("debate_bull", "🐂", "牛派首席"),
        ("debate_bear", "🐻", "熊派首席"),
        ("debate_risk", "🛡️", "风控首席"),
        ("debate_mod", "⚖️", "主持合成"),
    ]

    def label_for(stage_key):
        for key, icon, name, cls in AGENT_FLOW:
            if key == stage_key:
                return icon, name, cls
        for key, icon, name in DEBATE_STAGES:
            if key == stage_key:
                return icon, name, ""
        return "⚙️", stage_key, ""

    def stage_index(stage_key):
        for i, (key, _, _, _) in enumerate(AGENT_FLOW):
            if key == stage_key:
                return i
        return -1


from modules.page_guard import safe_fragment

st.set_page_config(page_title="QuantAgent 多智能体投研", page_icon="🤖", layout="wide")

_VERDICT_COLOR = {"看多": "#dc2626", "看空": "#009e60", "持有": "#d97706"}
_TERM_CSS = """
<style>
.qa-card{border:1px solid #2a3340;border-radius:10px;padding:10px 12px;margin:6px 0;background:#11161d;}
.qa-row{display:flex;align-items:center;gap:10px;}
.qa-icon{font-size:20px;width:30px;text-align:center;}
.qa-name{font-weight:600;color:#e6edf3;min-width:120px;}
.qa-badge{font-size:12px;padding:2px 8px;border-radius:10px;margin-left:auto;}
.qa-bar{height:6px;border-radius:4px;background:#1f2730;margin-top:8px;overflow:hidden;}
.qa-bar > div{height:100%;transition:width .4s ease;}
.qa-log{max-height:240px;overflow-y:auto;background:#0b0f14;border:1px solid #1c2430;border-radius:8px;padding:8px 10px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;color:#9fb0c0;}
.qa-log div{padding:2px 0;border-bottom:1px solid #141b24;}
.qa-lean-bull{color:#dc2626;font-weight:700;}
.qa-lean-bear{color:#009e60;font-weight:700;}
.qa-lean-hold{color:#d97706;font-weight:700;}
</style>
"""


def _verdict_color(v: str) -> str:
    return _VERDICT_COLOR.get(v, "#d97706")


def _poll_once(task_id: str):
    """缓存 1 秒：避免 fragment 重跑时请求堆积。"""
    from modules.background_tasks import poll_task

    return poll_task(task_id, max_wait=0.5)


def _agent_status(agent_key: str, current_stage: str, status: str) -> str:
    """返回 done / running / waiting。"""
    if status == "success":
        return "done"
    if status in ("pending", "running") and not current_stage:
        return "waiting"
    cur = stage_index(current_stage) if current_stage else -1
    ai = stage_index(agent_key)
    if ai < cur or (current_stage or "").startswith("debate_") and agent_key == "chief":
        return "done"
    if ai == cur or (agent_key == "chief" and (current_stage or "").startswith("debate_")):
        return "running"
    return "waiting"


def _render_live_progress(task: dict):
    """渲染实时协作进度（进度条 + 每 Agent 状态 + 日志流 + 辩论面板）。"""
    st.markdown(_TERM_CSS, unsafe_allow_html=True)
    progress = int(task.get("progress", 0) or 0)
    stage = task.get("stage", "")
    status = task.get("status", "")
    st.progress(progress / 100.0, text=f"多智能体协作中… {progress}% ｜ 当前：{label_for(stage)[1] if stage else '排队中'}")

    cols = st.columns(2)
    for i, (key, icon, name, cls) in enumerate(AGENT_FLOW):
        stt = _agent_status(key, stage, status)
        color = {"done": "#009e60", "running": "#d97706", "waiting": "#3a4452"}[stt]
        badge = {"done": "✅ 完成", "running": "🔄 进行中", "waiting": "⏳ 等待"}[stt]
        pct = 100 if stt == "done" else (50 if stt == "running" else 0)
        card = f"""
        <div class="qa-card">
          <div class="qa-row">
            <div class="qa-icon">{icon}</div>
            <div class="qa-name">{name}</div>
            <div class="qa-badge" style="background:{color}22;color:{color}">{badge}</div>
          </div>
          <div class="qa-bar"><div style="width:{pct}%;background:{color}"></div></div>
        </div>"""
        (cols[0] if i % 2 == 0 else cols[1]).markdown(card, unsafe_allow_html=True)

    # CrewAI 辩论面板
    logs = task.get("logs", []) or []
    debate_logs = [l for l in logs if str(l.get("stage", "")).startswith("debate_")]
    if debate_logs:
        st.markdown("#### ⚖️ 多首席辩论实况")
        dcols = st.columns(2)
        for j, l in enumerate(debate_logs):
            icon, name, _ = label_for(l.get("stage", ""))
            dcols[j % 2].markdown(
                f"<div class='qa-card'><div class='qa-row'><div class='qa-icon'>{icon}</div>"
                f"<div class='qa-name'>{name}</div></div>"
                f"<div style='color:#c9d4e0;font-size:13px'>{l.get('message','')}</div></div>",
                unsafe_allow_html=True,
            )

    # 实时日志流
    with st.expander("🪵 实时协作日志", expanded=True):
        if logs:
            lines = "".join(
                f"<div><span style='color:#5b8def'>[{label_for(l.get('stage',''))[1]}]</span> {l.get('message','')}</div>"
                for l in logs[-40:]
            )
            st.markdown(f"<div class='qa-log'>{lines}</div>", unsafe_allow_html=True)
        else:
            st.caption("等待首个 Agent 启动…")


def _render_report(result: dict):
    """渲染一份 QuantAgent 投研结果（result 即 ResearchState.to_dict()）。"""
    c = result.get("chief_report", {}) or {}

    vc = _verdict_color(c.get("verdict", ""))
    st.markdown(
        f"<div style='padding:14px 18px;border-left:6px solid {vc};background:#11161d;border-radius:8px'>"
        f"<b style='font-size:20px;color:{vc}'>🏁 最终结论：{c.get('verdict','-')}</b> "
        f"&nbsp; 综合评分 <b>{c.get('composite','-')}</b>/100"
        + (f"<br>目标价 <b style='color:#e6edf3'>¥{c.get('target_price')}</b> ｜ 止损 <b style='color:#e6edf3'>¥{c.get('stop_price')}</b>" if c.get("target_price") else "")
        + f"<br><span style='color:#9fb0c0'>{c.get('rationale','')[:300]}</span></div>",
        unsafe_allow_html=True,
    )

    env = []
    env.append("真实数据" if result.get("used_real_data") else "合成数据(离线)")
    env.append("LLM" if result.get("used_llm") else "规则引擎")
    if result.get("used_browser"):
        env.append("FinBrowser")
    if result.get("used_rag"):
        env.append("FinRAG")
    if result.get("used_crewai"):
        env.append("CrewAI辩论")
    if result.get("approval"):
        env.append("已人工复核")
    st.caption("环境：" + " / ".join(env))

    st.divider()

    # CrewAI 辩论全程
    if result.get("debate"):
        st.subheader("⚖️ 多首席辩论全程")
        dcols = st.columns(2)
        for j, st_ in enumerate(result["debate"]):
            lean = st_.get("lean", "")
            lean_cls = {"看多": "qa-lean-bull", "看空": "qa-lean-bear", "持有": "qa-lean-hold"}.get(lean, "")
            dcols[j % 2].markdown(
                f"<div class='qa-card'><div class='qa-row'><div class='qa-icon'>{st_.get('icon','')}</div>"
                f"<div class='qa-name'>{st_.get('name','')} <span class='{lean_cls}'>[{lean}]</span></div></div>"
                f"<div style='color:#c9d4e0;font-size:13px'>{st_.get('text','')}</div></div>",
                unsafe_allow_html=True,
            )
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

    if result.get("rag_context"):
        with st.expander("🧠 FinRAG 复盘记忆 / 相关研报"):
            st.text(result["rag_context"])

    with st.expander("🪵 多智能体执行轨迹"):
        for t in result.get("trace", []) or []:
            st.markdown(f"- **{t.get('node')}**: {t.get('log')}")

    if result.get("errors"):
        with st.expander("⚠️ 运行提示"):
            for e in result["errors"]:
                st.warning(e)


@safe_fragment
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
            _render_live_progress(task)
            if st_autorefresh is not None:
                st_autorefresh(interval=1000, limit=240, key="quant_autorefresh")
            else:
                # fallback：不阻塞、不重跑整页；让用户手动刷新
                st.caption("⏳ 任务运行中，请稍后刷新页面查看结果。")
            return

    if st.session_state.get("quant_result") is not None:
        _render_report(st.session_state["quant_result"])


def main():
    st.title("🤖 QuantAgent · 多智能体 A股投研")
    st.caption("数据底座复用 StockSignal（StockFetcher/technical/signal/news/backtest）+ FinBrowser 采集外挂 + FinRAG 记忆/RAG + CrewAI 多首席辩论")

    ticker = st.text_input("股票代码", value="600519", help="6 位 A股代码，如 600519 / 000001")

    col1, col2 = st.columns([1, 3])
    with col1:
        mode = st.radio("运行模式", ["任务通道（推荐）", "本地直跑（调试）"], horizontal=True,
                        help="任务通道：提交到后端 5050 异步执行并轮询实时进度，不阻塞 UI；直跑：前端进程内同步执行。")
    with col2:
        engine = st.selectbox("编排引擎", ["auto", "crewai", "langgraph", "simple"],
                              help="auto=自动选最优；crewai=多首席辩论（牛/熊/风控派对抗+主持合成）；"
                                   "langgraph=真实 LangGraph（条件路由+人工审批）；simple=零依赖图。")
        use_browser = st.checkbox("启用 FinBrowser 采集外挂", value=True)
        use_rag = st.checkbox("启用 FinRAG 记忆/RAG", value=True)
        force_human = st.checkbox("强制人工复核（HITL 演示）", value=False,
                                  help="高风险或勾选时，LangGraph 编排会在风控后插入人工审批节点。")

    run = st.button("发起多智能体投研", type="primary", use_container_width=True)

    if not run:
        st.info("点击按钮，由 5 个分析智能体 + 多首席决策智能体协作产出投研报告，并以实时进度条展示每个 Agent 的工作状态。无 LLM Key 时自动走规则引擎，仍可完整演示。")
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
                st.info("📡 投研任务已提交到后台运行，可切到其他页面，进度会自动刷新。完成后展示报告。")
            else:
                st.error(f"提交失败：{err}（请确认后端 5050 已启动）")
        except Exception as e:
            st.error(f"任务通道不可用：{e}（请确认后端 5050 已启动，或改用本地直跑模式）")
    else:
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
            st.exception(e)

    _result_panel()


if __name__ == "__main__":
    main()
