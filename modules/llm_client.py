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
import logging

logger = logging.getLogger(__name__)

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
    except Exception as e:
        logger.warning(f"[llm_client] 未处理异常: {e}")
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


# =====================================================================
# 模型目录（T-314：真实 AI 模型接入的单一真理源）
# =====================================================================
# 2026-10-24 实测 DeepSeek 服务端可用模型：deepseek-flash / deepseek-v4-pro
# （旧 deepseek-chat 仍可调用，但已不在 /models 清单，随时可能下线）。
# 三者均为推理模型（响应带 reasoning_content）：推理过程与正文共享 max_tokens
# 预算，实测 max_tokens=400 时推理吃光预算、content 返回空串——因此必须给
# 推理模型设置 token 下限，否则会被误判为「模型空答」并静默降级到规则引擎。
MODEL_CATALOG: Dict[str, Dict[str, "object"]] = {
    "deepseek-flash": {
        "label": "DeepSeek Flash",
        "desc": "低延迟，日常问答 / 教学解释",
        "reasoning": True,
        "min_tokens": 1500,   # 实测推理 ~300 tokens + 正文，1500 留足余量
    },
    "deepseek-v4-pro": {
        "label": "DeepSeek V4 Pro",
        "desc": "质量优先，深度研报 / 多空辩论",
        "reasoning": True,
        "min_tokens": 1500,
    },
    "deepseek-reasoner": {
        "label": "DeepSeek Reasoner",
        "desc": "强推理，复杂归因与多步分析",
        "reasoning": True,
        "min_tokens": 2000,   # R1 类推理链更长
    },
}

# 回应方式 → 默认模型（分层路由；用户可在前端覆盖）
STYLE_MODEL_DEFAULTS: Dict[str, str] = {
    "quick": "deepseek-flash",
    "teach": "deepseek-flash",
    "report": "deepseek-v4-pro",
    "debate": "deepseek-v4-pro",
}

# 推理模型的最小 token 预算（目录未声明时的兜底）
REASONING_MIN_TOKENS = 1500


def provider_catalog(base_url: Optional[str] = None) -> Dict[str, Dict[str, object]]:
    """返回当前 provider 可用的模型目录。

    仅当 base_url 指向 DeepSeek 时返回目录——其它 provider（OpenRouter / OpenAI
    等）的模型名与这里完全不同，写死 deepseek 模型名会让所有调用 400 失败。
    """
    url = (base_url if base_url is not None else config()[0]) or ""
    if "deepseek" in url.lower():
        return dict(MODEL_CATALOG)
    return {}


def style_default_model(style: Optional[str]) -> Optional[str]:
    """回应方式的默认模型（未收录的 style 返回 None，交给 env 主模型）。"""
    return STYLE_MODEL_DEFAULTS.get(str(style or "").strip())


def resolve_model(choice: Optional[str] = None, style: Optional[str] = None) -> Optional[str]:
    """决定本次调用的模型：显式选择优先 → 回应方式默认 → None（用 env 主模型）。

    只有在当前 provider 目录内匹配成功才返回模型名；否则返回 None，避免跨
    provider 写死模型名。未知 choice 不原样下发，回落 style 默认。
    """
    cat = provider_catalog()
    if not cat:
        return None
    for cand in (choice, style_default_model(style)):
        name = str(cand or "").strip()
        if name and name in cat:
            return name
    return None


def effective_max_tokens(model: Optional[str], max_tokens: int) -> int:
    """按模型类型修正输出预算：推理模型抬到下限，普通模型原样返回。

    推理模型（如 deepseek-flash / v4-pro）先产出 reasoning_content 再产出正文，
    预算不足时正文为空串。这里只抬不压，调用方给的更大预算保持不变。
    """
    spec = MODEL_CATALOG.get(str(model or "").strip()) or {}
    try:
        mt = int(max_tokens)
    except (TypeError, ValueError):
        mt = 1200
    if spec.get("reasoning"):
        floor = int(spec.get("min_tokens") or REASONING_MIN_TOKENS)
        return max(mt, floor)
    return mt


def _model_chain(model: Optional[str] = None) -> List[str]:
    """主模型 + 回退模型链，按优先级排列。

    model 显式指定时置于链首（用户点名的模型优先尝试），其余按 env 主模型 +
    回退链去重后追加——点名模型失败时仍有机会拿到回答，而不是直接降级规则引擎。
    """
    primary = _env("STARFIELD_LLM_MODEL", "gpt-4o-mini")
    head = str(model or "").strip()
    chain: List[str] = [head] if head else []
    for m in [primary] + fallback_models():
        if m and m not in chain:
            chain.append(m)
    return chain


def _extra_headers(base_url: str) -> Dict[str, str]:
    """OpenRouter 等兼容服务需要的额外头部。"""
    if "openrouter.ai" in base_url:
        return {
            "HTTP-Referer": "https://localhost:8899",
            "X-Title": "StockSignal",
        }
    return {}


def chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.5,
    max_tokens: int = 1200,
    timeout: int = 30,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    调用 OpenAI 兼容 Chat Completion。
    返回 assistant 内容，失败时（含主模型限流/超时）自动尝试回退模型链，
    全部失败则返回 None，由调用方回退到规则引擎。

    model（T-314）：显式指定模型（用户在前端选择 / 回应方式分层路由解析结果）。
    指定后置于链首，其后仍追加 env 主模型与回退链，避免点名模型偶发失败就直接降级。
    推理模型的 max_tokens 会经 effective_max_tokens 抬到下限（否则推理吃光预算、
    正文为空）。

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

    # 单模型尝试：钳值 90s（T-308 研报扩大：2000 tokens 输出实测 40~70s，
    # 旧钳值 30s 会掐断长回答后静默回退规则模板）；调用方传更短超时不受影响
    per_timeout = min(timeout, 90)
    # 整条链总预算：最多 2 个模型 × per_timeout，且不超过 150s，确保用户少等待
    total_cap = min(per_timeout * 2, 150)
    chain = _model_chain(model)
    last_err = ""
    _start = time.time()
    _set_last_err("")
    try:
        import openai

        client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=per_timeout)
    except Exception as e:
        _set_last_err(f"LLM client init failed: {e}")
        logger.warning(f"[llm_client] LLM client init failed: {e}")
        return None

    for m in chain:
        # 总预算耗尽：停止尝试，交回调用方回退到规则引擎
        if time.time() - _start > total_cap:
            last_err = f"{m}: 总预算 {total_cap:.0f}s 耗尽，放弃剩余模型"
            break
        # T-314：推理模型预算下限（只抬不压）
        _mt = effective_max_tokens(m, max_tokens)
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=messages,
                temperature=temperature,
                max_tokens=_mt,
                extra_headers=extra_headers,
                timeout=per_timeout,
            )
            content = resp.choices[0].message.content
            if content:
                return content
            # 空内容通常是模型主动拒答/截断，换模型也大概率同样空，立即终止回退链
            _reason = getattr(resp.choices[0], "finish_reason", "") or ""
            last_err = f"{m}: empty content (finish={_reason}, max_tokens={_mt})"
            _set_last_err(last_err)
            break
        except Exception as e:
            logger.warning(f"[llm_client] 处理异常: {e}")
            last_err = f"{m}: {e}"
            _set_last_err(last_err)
            # 限流/超时/端点错误 -> 尝试下一个回退模型
            continue
    logger.warning(f"[llm_client] all models failed: {last_err}")
    return None


def answer_with_llm(
    system_prompt: str,
    user_prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.5,
    max_tokens: int = 1200,
    timeout: int = 30,
    model: Optional[str] = None,
) -> Optional[str]:
    """带历史记录的对话调用。history 元素为 {"role":"user"/"assistant", "content":...}。

    model（T-314）：显式模型名，透传给 chat_completion（置于回退链首）。
    """
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        # 只保留最近 6 轮，避免超出上下文
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": user_prompt})
    return chat_completion(
        messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout, model=model,
    )


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
    except Exception as e:
        logger.warning(f"[llm_client] 未处理异常: {e}")
        pass

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except Exception as e:
            logger.warning(f"[llm_client] 未处理异常: {e}")
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
    except Exception as e:
        logger.warning(f"[llm_client] 未处理异常: {e}")
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
