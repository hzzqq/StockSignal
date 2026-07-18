"""
modules/quantagent/agents/base.py
---------------------------------
所有投研智能体的抽象基类。

约定：
- 每个 Agent 是一个「角色」，在图中作为一个节点运行；
- run(state) 读取共享状态、产出自己的报告（写回 state 对应字段），并返回一行人类可读的 trace 日志；
- Agent 内部对 StockSignal 模块的全部调用必须 try/except，确保离线/无 Key 时骨架仍可跑通。
"""

from __future__ import annotations

from typing import Any

from modules.quantagent.state import ResearchState


class BaseAgent:
    #: 节点名（对应图中节点 id）
    name: str = "base"
    #: 角色说明（用于 prompt / 报告头）
    role: str = "基础智能体"

    def run(self, state: ResearchState) -> str:
        """执行本 Agent 的逻辑，返回 trace 日志字符串。子类必须实现。"""
        raise NotImplementedError

    # ---------- 通用工具 ----------
    @staticmethod
    def _safe_import(module: str, attr: str, state: ResearchState):
        """安全导入 StockSignal 模块属性；失败返回 None 并记录。"""
        try:
            import importlib
            mod = importlib.import_module(module)
            return getattr(mod, attr)
        except Exception as e:  # noqa: BLE001
            state.add_error(f"导入 {module}.{attr} 失败: {e}")
            return None

    @staticmethod
    def _num(v: Any, default: float = 0.0) -> float:
        try:
            if v is None or v == "":
                return default
            return float(v)
        except Exception:
            return default
