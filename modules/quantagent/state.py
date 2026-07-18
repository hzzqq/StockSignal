"""
modules/quantagent/state.py
---------------------------
多智能体投研的共享状态（State）。

设计原则：
- 状态是一个 dataclass，贯穿整个 LangGraph 风格的有向图；
- 每个 Agent 节点读取上游字段、写入自己的报告字段，并追加一行 trace 日志；
- df 等不可序列化对象允许留在内存态（仅 demo / Streamlit 进程内使用），
  对外交付的「投研报告」只取各 *_report 字典，可安全 JSON 序列化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---- DataFrame 注册表（仅内存态）----
# LangGraph 的 checkpointer 会把状态序列化，而 pandas DataFrame 无法被 msgpack 序列化。
# 因此 df 不进入 LangGraph 的通道/快照，而是暂存在这里，由各 Agent 通过 resolve_df 取用。
# 这样彻底规避了 DataFrame 的序列化问题（也消除了 pickle/Timestamp 安全告警）。
_DF_REGISTRY: Dict[str, Any] = {}


def store_df(key: str, df: Any) -> None:
    _DF_REGISTRY[key] = df


def fetch_df(key: str) -> Any:
    return _DF_REGISTRY.get(key)


def resolve_df(state: "ResearchState") -> Any:
    """优先用 state.df（同一进程内直接引用）；否则从注册表按 ticker 取（LangGraph 跨节点场景）。"""
    if state.df is not None:
        return state.df
    return fetch_df(state.ticker)


@dataclass
class ResearchState:
    # ---- 任务输入 ----
    ticker: str = ""                 # 股票代码（6 位）
    display_name: str = ""           # 显示名（代码+名称）

    # ---- 环境与数据源标记（用于报告透明化）----
    used_real_data: bool = False     # 是否拿到真实行情（否则用合成数据演示）
    used_llm: bool = False           # 首席 Agent 是否真的调用了 LLM
    used_browser: bool = False       # 是否启用 FinBrowser 采集外挂
    used_rag: bool = False           # 是否启用 FinRAG 记忆/RAG 模块

    # ---- 共享数据底座 ----
    df: Any = None                   # 清洗后的行情 DataFrame（仅内存）
    market_brief: Dict[str, Any] = field(default_factory=dict)   # 数据 Agent 产出的行情速览

    # ---- 各智能体产出（结构化 + 文本）----
    data_report: Dict[str, Any] = field(default_factory=dict)
    fundamental_report: Dict[str, Any] = field(default_factory=dict)
    technical_report: Dict[str, Any] = field(default_factory=dict)
    sentiment_report: Dict[str, Any] = field(default_factory=dict)
    risk_report: Dict[str, Any] = field(default_factory=dict)

    # ---- FinRAG 记忆/RAG 注入 ----
    rag_context: str = ""            # 召回的过往决策/研报片段
    memory: Dict[str, Any] = field(default_factory=dict)         # 该标的的记忆摘要

    # ---- 首席决策 ----
    chief_report: Dict[str, Any] = field(default_factory=dict)   # verdict/target/stop/rationale

    # ---- CrewAI 多首席辩论（engine="crewai"）----
    debate: List[Dict[str, Any]] = field(default_factory=list)   # 各首席立场 [{role,name,icon,lean,text}]
    used_crewai: bool = False      # 是否真正用 CrewAI 多智能体编排

    # ---- 运行轨迹（用于可视化 / 调试 / 复试讲解）----
    trace: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # ---- LangGraph 人工审批（HITL）----
    human_approval_enabled: bool = False   # 是否启用人工复核节点
    approval: Any = None                   # 人工复核的返回结果（Command(resume=...) 注入）

    # ---- 实时进度回调（仅内存；不进入任何序列化通道）----
    reporter: Optional[Callable[[str, str], None]] = None  # progress_callback(stage_key, message)

    def add_trace(self, node: str, log: str) -> None:
        self.trace.append({"node": node, "log": log})
        # 进度回调：后端任务通道借此把「哪个 Agent 跑完了」实时透传给前端
        if self.reporter is not None:
            try:
                self.reporter(node, log)
            except Exception:  # noqa: BLE001 - 回调失败绝不能影响主流程
                pass

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def to_dict(self, include_df: bool = False) -> Dict[str, Any]:
        """
        导出 JSON 安全的字典（用于后端任务结果回传 / 外部交付）。
        - 默认剔除 df（DataFrame，不可 JSON 序列化）；
        - reporter 是可调用对象，必须剔除，否则 JSON 序列化失败；
        - include_df=True 时保留 df 对象引用（仅进程内 / 内存 checkpointer 场景）。
        """
        from dataclasses import asdict

        d = _json_safe(asdict(self))
        if not include_df:
            d.pop("df", None)
        d.pop("reporter", None)
        # 确保嵌套结构均为普通 dict/list（asdict 已是，这里仅兜底类型）
        d.setdefault("market_brief", {})
        for k in ("data_report", "fundamental_report", "technical_report",
                  "sentiment_report", "risk_report", "chief_report", "memory"):
            d.setdefault(k, {})
        d.setdefault("trace", [])
        d.setdefault("errors", [])
        return d


def _json_safe(o: Any) -> Any:
    """
    递归把不可 JSON 序列化的对象（pandas Timestamp / numpy 类型 / datetime / DataFrame 等）
    转成字符串或原生类型，保证 to_dict() 产出严格 JSON 安全字典。

    背景：行情/报告字段里常混入 pandas.Timestamp（如最近交易日）、numpy 标量，
    asdict 只转换 dataclass 实例、不会递归处理 dict 内部的这些对象，必须手动净化。
    """
    import datetime as _dt

    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, (_dt.datetime, _dt.date)):
        return o.isoformat()
    try:
        import pandas as pd

        if isinstance(o, (pd.Timestamp,)):
            return o.isoformat()
    except Exception:  # pragma: no cover
        pass
    if hasattr(o, "isoformat"):
        try:
            return o.isoformat()
        except Exception:
            pass
    try:
        import numpy as np

        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return [_json_safe(x) for x in o.tolist()]
    except Exception:  # pragma: no cover
        pass
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return str(o)
