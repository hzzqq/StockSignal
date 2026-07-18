"""
modules/quantagent/progress.py
------------------------------
多智能体「实时协作进度」的共享定义。

前后端共用同一套 stage 语义，保证：
  - 后端编排器在 Agent 跑完时回调 progress_callback(stage_key, message)；
  - 后端任务通道把 stage → percent 并写入 task.progress / task.stage / task.logs；
  - 前端页面按 AGENT_FLOW 渲染每个 Agent 的独立进度条 + 日志流。

stage_key 与 ResearchState.trace 的 node 名保持一致（data/fundamental/.../chief），
CrewAI 多首席辩论模式会把 chief 展开为 debate_bull/debate_bear/debate_risk/debate_mod。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# 标准单链编排的 9 个阶段（顺序即执行顺序）
STAGE_ORDER: List[str] = [
    "data", "fundamental", "technical", "fundflow", "sentiment", "risk",
    "rag_inject", "chief", "backtest",
]

# 每个阶段的展示信息： (key, 图标, 中文名, Agent 类名)
AGENT_FLOW: List[Tuple[str, str, str, str]] = [
    ("data", "📡", "数据采集", "DataAgent"),
    ("fundamental", "🏢", "基本面分析", "FundamentalAgent"),
    ("technical", "📈", "技术面分析", "TechnicalAgent"),
    ("fundflow", "💰", "资金流分析", "FundFlowAgent"),
    ("sentiment", "💬", "舆情分析", "SentimentAgent"),
    ("risk", "🛡️", "风控评估", "RiskAgent"),
    ("rag_inject", "🧠", "FinRAG 复盘记忆", "FinRAG"),
    ("chief", "🏁", "首席决策", "ChiefAgent"),
    ("backtest", "🔬", "回测验证", "BacktestAgent"),
]

# CrewAI 多首席辩论模式：chief 阶段被展开为四个辩论/合成子阶段
DEBATE_STAGES: List[Tuple[str, str, str]] = [
    ("debate_bull", "🐂", "牛派首席"),
    ("debate_bear", "🐻", "熊派首席"),
    ("debate_risk", "🛡️", "风控首席"),
    ("debate_mod", "⚖️", "主持合成"),
]

# 每个 stage_key → 完成该阶段后建议的整体进度百分比
_PERCENT_MAP: Dict[str, int] = {
    "data": 8,
    "fundamental": 20,
    "technical": 32,
    "fundflow": 44,
    "sentiment": 56,
    "risk": 68,
    "rag_inject": 78,
    # crewai 辩论子阶段（chief 展开）
    "debate_bull": 82,
    "debate_bear": 86,
    "debate_risk": 90,
    "debate_mod": 94,
    "chief": 90,
    "backtest": 100,
}


def percent_for(stage_key: str) -> int:
    """把某个 stage 映射为 0-100 的整体进度（未知 stage 返回上一档）。"""
    return _PERCENT_MAP.get(stage_key, 80)


def label_for(stage_key: str) -> Tuple[str, str, str]:
    """返回 (图标, 中文名, 类名) 用于前端展示。"""
    for key, icon, name, cls in AGENT_FLOW:
        if key == stage_key:
            return icon, name, cls
    for key, icon, name in DEBATE_STAGES:
        if key == stage_key:
            return icon, name, ""
    return "⚙️", stage_key, ""


def stage_index(stage_key: str) -> int:
    """在 AGENT_FLOW 中的序号（用于标记「已完成/进行中/未开始」）。"""
    for i, (key, _, _, _) in enumerate(AGENT_FLOW):
        if key == stage_key:
            return i
    return -1
