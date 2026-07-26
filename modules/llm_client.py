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

import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple


# 失败原因可观测性：chat_completion 把最近一次失败的「真因」写到这里，
# 调用方/监控可用 last_error() 读取，区分「未配置 Key」「客户端初始化失败」
# 「全部模型失败」「空内容」等，避免 LLM 静默失败时只能盲回退到规则引擎。
_LAST_ERR = ""


def last_error() -> str:
    """返回最近一次 chat_completion 失败的原因（可观测性）。

    调用前若从未失败过则为空字符串。用于日志/遥测，不影响主流程返回值。
    """
    return _LAST_ERR


def _set_last_err(msg: str) -> None:
    global _LAST_ERR
    _LAST_ERR = msg or ""


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
    timeout: int = 30,
) -> Optional[str]:
    """
    调用 OpenAI 兼容 Chat Completion。
    返回 assistant 内容，失败时（含主模型限流/超时）自动尝试回退模型链，
    全部失败则返回 None，由调用方回退到规则引擎。

    总预算守卫：免费模型（尤其 OpenRouter）常因限流排队，若放任整条回退链
    逐模型各等 100s，最坏可达 400s，超过调用方的前端超时。这里额外限制
    「整条链总耗时」上限，超时即停止尝试并返回 None，让调用方快速回退到
    规则引擎（瞬时），避免用户干等前端报「响应超时」。
    """
    if not is_configured():
        _set_last_err("未配置 STARFIELD_LLM_API_KEY，已回退规则引擎")
        return None

    base_url, _model, api_key = config()
    extra_headers = _extra_headers(base_url)

    # 单模型尝试：默认 30s，避免整条链挂死；调用方可按场景传入更短超时
    # 总预算也收紧，免费模型排队严重时快速失败，让调用方 fallback 规则引擎
    per_timeout = min(timeout, 30)
    # 整条链总预算：最多 2 个模型 × per_timeout，且不超过 60s，确保用户少等待
    total_cap = min(per_timeout * 2, 60)
    chain = _model_chain()
    last_err = ""
    _start = time.time()
    _set_last_err("")
    try:
        import openai

        client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=per_timeout)
    except Exception as e:
        _set_last_err(f"LLM client init failed: {e}")
        print(f"[llm_client] LLM client init failed: {e}")
        return None

    for model in chain:
        # 总预算耗尽：停止尝试，交回调用方回退到规则引擎
        if time.time() - _start > total_cap:
            last_err = f"{model}: 总预算 {total_cap:.0f}s 耗尽，放弃剩余模型"
            break
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
            # 空内容通常是模型主动拒答/截断，换模型也大概率同样空，立即终止回退链
            last_err = f"{model}: empty content"
            _set_last_err(last_err)
            break
        except Exception as e:
            last_err = f"{model}: {e}"
            _set_last_err(last_err)
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
    timeout: int = 30,
) -> Optional[str]:
    """带历史记录的对话调用。history 元素为 {"role":"user"/"assistant", "content":...}。"""
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        # 只保留最近 6 轮，避免超出上下文
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": user_prompt})
    return chat_completion(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)


# =====================================================================
# 结构化 JSON 输出（新增能力）
# =====================================================================
def _extract_json(text: str):
    """从模型自由文本中尽力抽取 JSON。

    策略（按收益递减）：
      1. 整段直接 json.loads；
      2. 剥离 ```json ... ``` / ``` ... ``` 围栏后解析；
      3. 截取首个 { / [ 到最后一个 } / ] 的子串再解析。
    全部失败返回 None（不抛异常，交给调用方按 default 兜底）。
    """
    if not text:
        return None
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except Exception:
            pass

    opens = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not opens:
        return None
    start = min(opens)
    end = max(text.rfind("}"), text.rfind("]"))
    if end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def chat_completion_json(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 1500,
    timeout: int = 30,
    default=None,
):
    """调用 LLM 并尝试把回复解析为结构化 JSON（dict / list）。

    适用于「输出 JSON 评分/标签/结构化结论」的场景。任何失败（未配置 Key、
    模型失败、无法解析为 JSON）一律返回 ``default``，由调用方兜底，绝不抛异常。
    """
    raw = chat_completion(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    if raw is None:
        return default
    parsed = _extract_json(raw)
    # 契约收紧：本函数承诺返回「结构化 JSON（dict / list）」。模型偶尔会吐出
    # 裸标量（如 "false" → False、"123" → 123、"\"x\"" → "x"），若原样返回，
    # 调用方对其做 .get()/下标会 AttributeError/TypeError 崩溃。这里只放行
    # 容器类型，其余一律回退 default，保证调用方拿到的永远是可安全解构的结构。
    if isinstance(parsed, (dict, list)):
        return parsed
    return default
