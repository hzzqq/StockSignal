"""
modules/llm_client.py
---------------------
星辰 AI 的 LLM 接入层：OpenAI 兼容接口。

读取环境变量：
  STARFIELD_LLM_API_KEY      LLM API Key（默认空）
  STARFIELD_LLM_BASE_URL     服务地址（默认 https://api.openai.com/v1）
  STARFIELD_LLM_MODEL        模型名（默认 gpt-4o-mini）

未配置 API Key 时返回 None，调用方应回退到规则引擎。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple


# 自动加载项目根目录 .env 文件（若存在），方便用户配置 LLM
_ENV_LOADED = False


def _load_dotenv_once() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from dotenv import load_dotenv

        # 项目根目录
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dotenv_path = os.path.join(root, ".env")
        if os.path.isfile(dotenv_path):
            load_dotenv(dotenv_path, override=False)
    except Exception:
        pass


def _env(key: str, default: str = "") -> str:
    _load_dotenv_once()
    return os.environ.get(key, default)


def is_configured() -> bool:
    return bool(_env("STARFIELD_LLM_API_KEY"))


def config() -> Tuple[str, str, str]:
    return (
        _env("STARFIELD_LLM_BASE_URL", "https://api.openai.com/v1"),
        _env("STARFIELD_LLM_MODEL", "gpt-4o-mini"),
        _env("STARFIELD_LLM_API_KEY"),
    )


# 免费档模型回退链：OpenRouter 免费模型经常触发 429 限流，
# 主模型失败（限流/超时）时依次尝试其它免费模型，提升成功率。
_DEFAULT_FALLBACK_MODELS = [
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "nvidia/nemotron-nano-9b-v2:free",
]


def fallback_models() -> List[str]:
    raw = _env("STARFIELD_LLM_FALLBACK_MODELS", "")
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(_DEFAULT_FALLBACK_MODELS)


def _model_chain() -> List[str]:
    """主模型 + 去重后的回退模型，按优先级排列。"""
    primary = _env("STARFIELD_LLM_MODEL", "gpt-4o-mini")
    chain = [primary]
    for m in fallback_models():
        if m and m not in chain:
            chain.append(m)
    return chain


def _extra_headers(base_url: str) -> Dict[str, str]:
    """OpenRouter 等兼容服务需要的额外头部。"""
    if "openrouter.ai" in base_url:
        return {
            "HTTP-Referer": "https://localhost:8501",
            "X-Title": "StockSignal",
        }
    return {}


def chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.5,
    max_tokens: int = 1200,
    timeout: int = 120,
) -> Optional[str]:
    """
    调用 OpenAI 兼容 Chat Completion。
    返回 assistant 内容，失败时（含主模型限流/超时）自动尝试回退模型链，
    全部失败则返回 None，由调用方回退到规则引擎。
    """
    if not is_configured():
        return None

    base_url, _model, api_key = config()
    extra_headers = _extra_headers(base_url)

    # 单模型尝试超时略短，避免整条链挂死；但 OpenRouter 免费模型经常排队，需留足时间
    per_timeout = min(timeout, 100)
    chain = _model_chain()
    last_err = ""
    try:
        import openai

        client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=per_timeout)
    except Exception as e:
        print(f"[llm_client] LLM client init failed: {e}")
        return None

    for model in chain:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=per_timeout,
            )
            content = resp.choices[0].message.content
            if content:
                return content
            last_err = f"{model}: empty content"
        except Exception as e:
            last_err = f"{model}: {e}"
            # 限流/超时/端点错误 -> 尝试下一个回退模型
            continue
    print(f"[llm_client] all models failed: {last_err}")
    return None


def answer_with_llm(
    system_prompt: str,
    user_prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.5,
    max_tokens: int = 1200,
) -> Optional[str]:
    """带历史记录的对话调用。history 元素为 {"role":"user"/"assistant", "content":...}。"""
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        # 只保留最近 6 轮，避免超出上下文
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": user_prompt})
    return chat_completion(messages, temperature=temperature, max_tokens=max_tokens)
