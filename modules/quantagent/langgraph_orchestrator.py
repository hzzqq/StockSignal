"""
modules/quantagent/langgraph_orchestrator.py
-------------------------------------------
真实 LangGraph 编排器（生产级）：用 langgraph.graph.StateGraph 实现多智能体有向图，
含：
  - 条件路由：风控门（risk_gate）—— 高风险标的自动转入「人工复核」节点，否则直达复盘；
  - 人工审批（HITL）：human_approval 节点通过 langgraph.types.interrupt() 暂停，
    等待外部 Command(resume=...) 注入决策后继续；配合 checkpointer 实现可恢复的人工介入。

与零依赖 fallback（orchestrator._Graph）保持同一套 Agent 与共享状态 ResearchState，
可一键切换：run_research(engine="langgraph"|"auto"|"simple")。

状态流：
  START → data → fundamental → technical → sentiment → risk
        → [条件路由] 高风险 → human_approval → rag_inject → chief → END
                             低风险 → rag_inject → chief → END

注：LangGraph 节点返回「状态全量快照」来跨节点传递（我们的 Agent 是「就地修改 state」风格，
而非 LangGraph 推荐的「返回增量 dict」风格；用 include_df=True 的快照在内存 checkpointer 下完全可行）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.quantagent.state import ResearchState
from modules.quantagent.agents import (
    ChiefAgent,
    DataAgent,
    FundamentalAgent,
    RiskAgent,
    SentimentAgent,
    TechnicalAgent,
)
from modules.quantagent.rag_module import FinRAG

# 延迟导入 langgraph，保证模块在无依赖环境仍可 import（仅使用真实编排时才会真正用到）
try:
    from langgraph.graph import StateGraph, END  # type: ignore
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
    from langgraph.types import interrupt, Command  # type: ignore
    _HAS_LANGGRAPH = True
except Exception:  # pragma: no cover - langgraph 未安装时
    _HAS_LANGGRAPH = False

import pickle  # noqa: E402  (用于 checkpointer 的 DataFrame 兜底序列化)

# 风控评分 >= 该阈值且启用人工审批时，路由到 human_approval 节点
DEFAULT_RISK_GATE = 60


class _SafeSerde:
    """
    LangGraph checkpointer 的容错序列化器。

    LangGraph 默认用 msgpack(JSON+) 序列化状态；但我们的共享状态里含 pandas DataFrame
    （仅内存态使用），msgpack 无法直接序列化 -> 会抛 TypeError 中断 checkpoint。

    这里用「委托 + 兜底」策略：优先走官方 JsonPlusSerializer；一旦遇到它处理不了的
    对象（DataFrame / numpy 特殊类型等），整体 pickle 兜底，保证 checkpoint 永不中断、
    df 跨节点/跨中断无损保留。
    """

    def __init__(self):
        try:
            from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # type: ignore

            self._base = JsonPlusSerializer()
        except Exception:  # pragma: no cover
            self._base = None

    def dumps_typed(self, obj):
        if self._base is not None:
            try:
                return self._base.dumps_typed(obj)
            except Exception:
                pass
        return "pickle_blob", pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    def loads_typed(self, typed):
        # LangGraph 以单参数 (type_str, data) 元组形式调用
        type_, data = typed
        if type_ == "pickle_blob":
            return pickle.loads(data)
        if self._base is not None:
            return self._base.loads_typed(typed)
        return data


def _snapshot(state: ResearchState) -> Dict[str, Any]:
    """
    节点返回的状态快照（**排除 df**：DataFrame 经注册表跨节点传递，不进 LangGraph 通道，
    从而彻底规避 checkpointer 的序列化问题）。
    """
    return state.to_dict(include_df=False)


def _wrap(node_name: str, agent_callable):
    """把「就地修改 state 并返回 trace 字符串」的 Agent 包装成 LangGraph 节点。"""

    def _node(state: ResearchState) -> Dict[str, Any]:
        try:
            log = agent_callable(state)
            state.add_trace(node_name, log)
        except Exception as e:  # noqa: BLE001
            state.add_error(f"节点 {node_name} 执行异常: {e}")
            state.add_trace(node_name, f"[异常] {e}")
        return _snapshot(state)

    return _node


def _rag_inject_node(finrag: Optional[FinRAG]):
    def _node(state: ResearchState) -> Dict[str, Any]:
        if finrag is None:
            state.add_trace("rag_inject", "[rag] 未启用 FinRAG")
            return _snapshot(state)
        try:
            query = f"{state.display_name or state.ticker} 投研决策"
            ctx = finrag.retrieve_context(state.ticker, query)
            state.rag_context = ctx.get("context", "")
            state.memory = ctx.get("memory", {})
            state.used_rag = True
            state.add_trace("rag_inject", f"[rag] 召回上下文 {len(state.rag_context)} 字符")
        except Exception as e:  # noqa: BLE001
            state.add_error(f"FinRAG 召回失败: {e}")
            state.add_trace("rag_inject", f"[rag] 召回失败 {e}")
        return _snapshot(state)

    return _node


def _risk_gate(state: ResearchState, threshold: int = DEFAULT_RISK_GATE,
               force_human_review: bool = False) -> str:
    """
    条件路由函数：根据风控评分决定是否需要人工复核。
    返回的边名对应 add_conditional_edges 的映射键。

    - force_human_review=True：无论风险高低都强制走人工复核（演示/合规用）；
    - 否则仅在 human_approval_enabled 且风险评分 >= 阈值时走人工复核。
    """
    if force_human_review:
        return "human"
    if not state.human_approval_enabled:
        return "auto"
    risk_score = float(state.risk_report.get("risk_score", 0) or 0)
    return "human" if risk_score >= threshold else "auto"


def _human_approval_node(state: ResearchState) -> Dict[str, Any]:
    """
    人工审批（HITL）节点：调用 langgraph 的 interrupt() 暂停执行，
    等待外部以 Command(resume={"approved": bool, "note": str}) 注入决策后继续。
    """
    risk = state.risk_report
    question = (
        f"标的 {state.display_name or state.ticker} 风险评分 {risk.get('risk_score')} "
        f"（{risk.get('verdict')}），是否批准进入首席决策？"
    )
    # interrupt 会暂停图执行；恢复时传入的值即为本调用的返回值
    decision = interrupt(
        {
            "type": "human_approval",
            "question": question,
            "risk_score": risk.get("risk_score"),
            "risk_verdict": risk.get("verdict"),
            "position_cap": risk.get("position_cap"),
        }
    )
    state.approval = decision or {"approved": True, "note": "（自动恢复，未提供意见）"}
    approved = bool(state.approval.get("approved")) if isinstance(state.approval, dict) else True
    note = state.approval.get("note", "") if isinstance(state.approval, dict) else ""
    state.add_trace(
        "human_approval",
        f"[HITL] {'批准' if approved else '驳回'} 进入首席决策" + (f"：{note}" if note else ""),
    )
    return _snapshot(state)


def build_langgraph(
    use_browser: bool = True,
    use_rag: bool = True,
    human_approval_enabled: bool = False,
    risk_gate_threshold: int = DEFAULT_RISK_GATE,
    force_human_review: bool = False,
):
    """
    组装真实 LangGraph 状态图。

    返回 (compiled_app, finrag)。app 已 compile()，调用方用 app.invoke(state, config) 运行。
    """
    if not _HAS_LANGGRAPH:
        raise RuntimeError(
            "未安装 langgraph，无法使用真实编排。请 `pip install langgraph`，"
            "或将 run_research 的 engine 参数设为 'simple'/'auto' 走零依赖 fallback。"
        )

    finrag = FinRAG(use_chroma=True) if use_rag else None

    g = StateGraph(ResearchState)
    g.add_node("data", _wrap("data", DataAgent().run))
    g.add_node("fundamental", _wrap("fundamental", FundamentalAgent().run))
    g.add_node("technical", _wrap("technical", TechnicalAgent().run))
    g.add_node("sentiment", _wrap("sentiment", SentimentAgent(use_browser=use_browser).run))
    g.add_node("risk", _wrap("risk", RiskAgent().run))
    g.add_node("human_approval", _human_approval_node)
    g.add_node("rag_inject", _rag_inject_node(finrag))
    g.add_node("chief", _wrap("chief", ChiefAgent(use_rag=use_rag, finrag=finrag).run))

    g.set_entry_point("data")
    g.add_edge("data", "fundamental")
    g.add_edge("fundamental", "technical")
    g.add_edge("technical", "sentiment")
    g.add_edge("sentiment", "risk")

    # 条件路由：risk 之后根据风控评分（或强制复核）分流
    g.add_conditional_edges(
        "risk",
        lambda s: _risk_gate(s, risk_gate_threshold, force_human_review),
        {"human": "human_approval", "auto": "rag_inject"},
    )
    g.add_edge("human_approval", "rag_inject")
    g.add_edge("rag_inject", "chief")
    g.add_edge("chief", END)

    checkpointer = MemorySaver(serde=_SafeSerde())
    app = g.compile(checkpointer=checkpointer)
    return app, finrag


def run_research_langgraph(
    ticker: str,
    display_name: str = "",
    use_browser: bool = True,
    use_rag: bool = True,
    human_approval_enabled: bool = False,
    force_human_review: bool = False,
    risk_gate_threshold: int = DEFAULT_RISK_GATE,
    thread_id: Optional[str] = None,
    auto_resume_approval: Optional[Dict[str, Any]] = None,
):
    """
    用真实 LangGraph 跑一次投研。

    参数：
      human_approval_enabled / force_human_review：是否（强制）启用人工复核节点；
      thread_id：LangGraph checkpointer 的会话线程 id（同线程可恢复中断）；
      auto_resume_approval：非交互场景（如后端任务）下，若触发 interrupt 自动以该决策恢复，
                           避免无人值守时图永久挂起。传 {"approved": True, "note": "自动批准"} 即可。

    返回：ResearchState。
    """
    ticker = str(ticker).strip().zfill(6)
    if not display_name:
        try:
            from modules.fetcher import StockFetcher

            display_name = StockFetcher().get_stock_name(ticker) or ticker
        except Exception:
            display_name = ticker

    state = ResearchState(
        ticker=ticker,
        display_name=display_name,
        human_approval_enabled=human_approval_enabled or force_human_review,
    )
    app, _ = build_langgraph(
        use_browser=use_browser,
        use_rag=use_rag,
        human_approval_enabled=human_approval_enabled,
        risk_gate_threshold=risk_gate_threshold,
        force_human_review=force_human_review,
    )
    cfg = {"configurable": {"thread_id": thread_id or f"quant_{ticker}"}}

    result = app.invoke(state, cfg)
    # 处理人工审批中断：interrupt() 暂停后，get_state(cfg).next 非空；
    # 此时以 Command(resume=decision) 恢复，图继续跑完 chief。
    try:
        snap = app.get_state(cfg)
        interrupted = bool(snap.next)
    except Exception:
        interrupted = False
    if interrupted:
        decision = auto_resume_approval or {"approved": True, "note": "（无人值守自动批准）"}
        result = app.invoke(Command(resume=decision), cfg)
    return _state_from_dict(result)


def _state_from_dict(obj) -> ResearchState:
    """把 LangGraph 返回的通道字典重建为 ResearchState（df 等对象经 pickle serde 已还原）。"""
    if isinstance(obj, ResearchState):
        return obj
    d = obj if isinstance(obj, dict) else getattr(obj, "__dict__", {})
    fields = ResearchState.__dataclass_fields__
    kwargs = {k: d[k] for k in fields if k in d}
    return ResearchState(**kwargs)
