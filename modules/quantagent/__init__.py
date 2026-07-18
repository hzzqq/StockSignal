"""
modules/quantagent/__init__.py
------------------------------
QuantAgent · 多智能体 A股投研框架（基于 StockSignal 数据/分析层构建）

对外导出：
  - run_research(ticker, ...)              端到端跑一次投研（引擎可切换 simple/auto/langgraph）
  - QuantAgentOrchestrator / build_graph  底层编排（零依赖 fallback）
  - run_research_langgraph                真实 LangGraph 编排（条件路由 + 人工审批 HITL）
  - HAS_LANGGRAPH                         运行时是否已安装 langgraph
  - ResearchState                         共享状态（含 to_dict 序列化）
  - FinRAG / ChromaRetriever              组件④记忆RAG（TF-IDF / chromadb 双检索）
  - BrowserAgent / BrowserCollector       组件⑤采集外挂（browser-use 真实 / requests 兜底）
"""

from modules.quantagent.state import ResearchState
from modules.quantagent.orchestrator import (
    build_graph,
    run_research,
    run_batch_research,
    format_report,
)
from modules.quantagent.rag_module import FinRAG, ChromaRetriever
from modules.quantagent.browser_plugin import BrowserAgent, BrowserCollector
from modules.quantagent import progress as progress

# LangGraph 真实编排（延迟导入，避免无依赖时报错）
try:
    from modules.quantagent.langgraph_orchestrator import (
        _HAS_LANGGRAPH as HAS_LANGGRAPH,
        run_research_langgraph,
        build_langgraph,
    )
except Exception:  # pragma: no cover
    HAS_LANGGRAPH = False
    run_research_langgraph = None
    build_langgraph = None

# CrewAI 多首席辩论编排（延迟导入，避免无依赖时报错）
try:
    from modules.quantagent.crewai_orchestrator import (
        _HAS_CREWAI as HAS_CREWAI,
        run_research_crewai,
    )
except Exception:  # pragma: no cover
    HAS_CREWAI = False
    run_research_crewai = None

__all__ = [
    "ResearchState",
    "build_graph",
    "run_research",
    "run_batch_research",
    "format_report",
    "FinRAG",
    "ChromaRetriever",
    "BrowserAgent",
    "BrowserCollector",
    "HAS_LANGGRAPH",
    "run_research_langgraph",
    "build_langgraph",
    "HAS_CREWAI",
    "run_research_crewai",
    "progress",
]
