"""
modules/quantagent/llm.py
-------------------------
LLM 接入层：复用 StockSignal 既有的 modules.llm_client（OpenAI 兼容 + 自动回退链），
并封装一层「离线安全」接口——未配置 Key 或调用失败时返回 None，由调用方回退到规则引擎。

这是 QuantAgent 与 StockSignal 解耦的关键：所有 Agent 只依赖本文件，
不直接触碰 LLM 细节；是否真有 LLM 能力由 .env 决定，骨架永远可跑。
"""

from __future__ import annotations

from typing import Dict, List, Optional

# 延迟导入，避免对 StockSignal 模块形成硬依赖
try:
    from modules.llm_client import chat_completion, answer_with_llm, is_configured
except Exception:  # pragma: no cover
    chat_completion = None
    answer_with_llm = None
    is_configured = lambda: False


def llm_configured() -> bool:
    """当前是否配置了可用的 LLM Key。"""
    try:
        return bool(is_configured()) if callable(is_configured) else False
    except Exception:
        return False


def llm_complete(system: str, user: str, temperature: float = 0.4, max_tokens: int = 1400) -> Optional[str]:
    """
    带 system/user 的一次性补全。失败时返回 None（调用方需有规则兜底）。
    """
    if chat_completion is None:
        return None
    try:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return chat_completion(messages, temperature=temperature, max_tokens=max_tokens, timeout=40)
    except Exception:
        return None


def llm_chat(system: str, user: str, history: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    """带历史的对话补全。"""
    if answer_with_llm is None:
        return None
    try:
        return answer_with_llm(system, user, history=history, timeout=40)
    except Exception:
        return None
