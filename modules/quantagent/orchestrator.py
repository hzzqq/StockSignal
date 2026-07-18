"""
modules/quantagent/orchestrator.py
----------------------------------
多智能体编排器（LangGraph 风格的有向图，零外部依赖实现）。

为什么自己实现图运行时而不是硬依赖 langgraph：
  - 骨架必须能在「无网络 / 无 pip 安装」环境下跑通（实习/考研演示最怕环境问题）；
  - 自实现的图结构透明、易讲清，复试时能说清「状态图怎么编译、节点如何流转」；
  - 已与真实 LangGraph 对齐（见下方映射），生产可直接替换为 langgraph.graph.StateGraph。

图结构（线性）：
  START → data → fundamental → technical → sentiment → risk → rag_inject → chief → END

节点即 Agent，rag_inject 是 FinRAG 的上下文注入节点。每个节点读写共享 ResearchState。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from modules.quantagent.agents import (
    ChiefAgent,
    DataAgent,
    FundamentalAgent,
    RiskAgent,
    SentimentAgent,
    TechnicalAgent,
)
from modules.quantagent.rag_module import FinRAG
from modules.quantagent.state import ResearchState


class _Graph:
    """极简状态图：节点 + 边，拓扑顺序执行。等价于 LangGraph 的 StateGraph.compile().invoke()。"""

    def __init__(self):
        self._nodes: Dict[str, Callable[[ResearchState], str]] = {}
        self._edges: List[tuple] = []
        self._entry: Optional[str] = None
        self._finish: Optional[str] = None
        self.START = "__start__"
        self.END = "__end__"

    def add_node(self, name: str, fn: Callable[[ResearchState], str]):
        self._nodes[name] = fn
        return self

    def set_entrypoint(self, name: str):
        self._entry = name
        return self

    def set_finish(self, name: str):
        self._finish = name
        return self

    def add_edge(self, a: str, b: str):
        self._edges.append((a, b))
        return self

    def compile(self):
        return self

    def invoke(self, state: ResearchState) -> ResearchState:
        # 从 entry 沿边顺序执行（线性图）
        order: List[str] = []
        cur = self._entry
        guard = 0
        while cur and cur != self.END and cur in self._nodes and guard < 100:
            order.append(cur)
            nxt = None
            for a, b in self._edges:
                if a == cur:
                    nxt = b
                    break
            cur = nxt
            guard += 1
        for name in order:
            try:
                log = self._nodes[name](state)
                state.add_trace(name, log)
            except Exception as e:  # noqa: BLE001
                state.add_error(f"节点 {name} 执行异常: {e}")
                state.add_trace(name, f"[异常] {e}")
        return state


def build_graph(use_browser: bool = True, use_rag: bool = True) -> (_Graph, FinRAG | None):
    """
    组装 QuantAgent 状态图。

    与 LangGraph 的等价写法（供生产替换参考）：
        from langgraph.graph import StateGraph, END
        g = StateGraph(ResearchState)
        g.add_node("data", DataAgent().run);  ...
        g.add_edge("data", "fundamental");  ...
        g.set_entry_point("data"); g.add_edge("chief", END)
        app = g.compile()
    """
    finrag = FinRAG(use_chroma=True) if use_rag else None

    g = _Graph()
    g.add_node("data", DataAgent().run)
    g.add_node("fundamental", FundamentalAgent().run)
    g.add_node("technical", TechnicalAgent().run)
    g.add_node("sentiment", SentimentAgent(use_browser=use_browser).run)
    g.add_node("risk", RiskAgent().run)

    # FinRAG 上下文注入节点
    def rag_inject(state: ResearchState) -> str:
        if finrag is None:
            return "[rag] 未启用 FinRAG"
        query = f"{state.display_name or state.ticker} 投研决策"
        ctx = finrag.retrieve_context(state.ticker, query)
        state.rag_context = ctx.get("context", "")
        state.memory = ctx.get("memory", {})
        state.used_rag = True
        return f"[rag] 召回上下文 {len(state.rag_context)} 字符"

    g.add_node("rag_inject", rag_inject)
    g.add_node("chief", ChiefAgent(use_rag=use_rag, finrag=finrag).run)

    g.set_entrypoint("data")
    g.add_edge("data", "fundamental")
    g.add_edge("fundamental", "technical")
    g.add_edge("technical", "sentiment")
    g.add_edge("sentiment", "risk")
    g.add_edge("risk", "rag_inject")
    g.add_edge("rag_inject", "chief")
    g.set_finish("chief")
    return g.compile(), finrag


def run_research(
    ticker: str,
    display_name: str = "",
    use_browser: bool = True,
    use_rag: bool = True,
    engine: str = "auto",
    human_approval_enabled: bool = False,
    force_human_review: bool = False,
    risk_gate_threshold: int = 60,
    auto_resume_approval: Optional[Dict[str, Any]] = None,
) -> ResearchState:
    """
    端到端跑一次多智能体投研，返回完整 ResearchState。

    engine:
      - "simple"  ：走零依赖自实现状态图（orchestrator._Graph）；
      - "langgraph"：强制走真实 LangGraph 编排（未安装则抛错）；
      - "auto"（默认）：装了 langgraph 就用，否则自动回退 simple。

    人工审批（仅 LangGraph 生效）：
      - human_approval_enabled / force_human_review 控制是否进入 HITL 节点；
      - auto_resume_approval 用于无人值守场景（如后端任务），触发 interrupt 时自动以该决策恢复。
    """
    ticker = str(ticker).strip().zfill(6)
    if not display_name:
        try:
            from modules.fetcher import StockFetcher
            display_name = StockFetcher().get_stock_name(ticker) or ticker
        except Exception:
            display_name = ticker

    use_langgraph = False
    if engine in ("langgraph", "auto"):
        try:
            from modules.quantagent.langgraph_orchestrator import (
                _HAS_LANGGRAPH,
                run_research_langgraph,
            )

            if engine == "langgraph" or _HAS_LANGGRAPH:
                use_langgraph = True
        except Exception as e:  # noqa: BLE001
            if engine == "langgraph":
                raise
            display_name = display_name  # 保持变量；下面回退

    if use_langgraph:
        return run_research_langgraph(
            ticker,
            display_name=display_name,
            use_browser=use_browser,
            use_rag=use_rag,
            human_approval_enabled=human_approval_enabled,
            force_human_review=force_human_review,
            risk_gate_threshold=risk_gate_threshold,
            auto_resume_approval=auto_resume_approval
            or {"approved": True, "note": "（无人值守自动批准）"},
        )

    # 零依赖 fallback
    state = ResearchState(
        ticker=ticker,
        display_name=display_name,
        human_approval_enabled=human_approval_enabled,
    )
    graph, _ = build_graph(use_browser=use_browser, use_rag=use_rag)
    return graph.invoke(state)


def format_report(state: ResearchState) -> str:
    """把 ResearchState 渲染成可读的投研报告（终端/日志用）。"""
    c = state.chief_report
    lines = []
    lines.append("=" * 64)
    lines.append(f"📊 QuantAgent 多智能体投研报告 · {state.display_name or state.ticker}")
    lines.append("=" * 64)
    env = []
    env.append("真实数据" if state.used_real_data else "合成数据(离线演示)")
    env.append("LLM" if state.used_llm else "规则引擎")
    if state.used_browser:
        env.append("FinBrowser")
    if state.used_rag:
        env.append("FinRAG")
    lines.append("环境：" + " / ".join(env))
    lines.append("-" * 64)
    for key in ("data_report", "fundamental_report", "technical_report", "sentiment_report", "risk_report"):
        r = getattr(state, key, {})
        if r.get("text"):
            lines.append(r["text"])
    if state.rag_context:
        lines.append(f"[复盘记忆]\n{state.rag_context}")
    lines.append("-" * 64)
    lines.append(f"🏁 最终结论：{c.get('verdict','-')} | 综合 {c.get('composite','-')}/100")
    if c.get("target_price"):
        lines.append(f"   目标价 ¥{c['target_price']}   止损 ¥{c['stop_price']}")
    lines.append(f"   论证：{c.get('rationale','')}")
    if state.errors:
        lines.append("-" * 64)
        lines.append("⚠️ 运行提示：" + "；".join(state.errors[:3]))
    lines.append("=" * 64)
    return "\n".join(lines)
