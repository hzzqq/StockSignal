"""modules/voice_event.py — 语音转写事件因子（真空白补全，2026-11-02）。

为什么补这块：
- 项目焦点「事件因子适配器」已接 P1 真实信号源（modules/event_factor）；但「语音」
  这一输入通道一直缺位——用户口头/录音讲的市场事件无法进入事件因子体系。
- 这是 stock-partner / 功能版块 Skill 映射里反复标注、却始终未落地的空白。

管道（端到端）：
    音频 bytes → ASR 转写 → 事件因子提取（复用 event_factor 透明规则标注）

ASR 实现：复用 modules.llm_client 的 STARFIELD_LLM_API_KEY / base_url
    调 OpenAI Whisper（audio.transcriptions）。兼容端点（本地 vLLM / OpenRouter 等）
    大多不支持 audio 接口 → 捕获降级返回 None，由调用方诚实提示，不编造转写。

红线（来自 working memory / event_factor）：
- 无音频 / 未配置 key / 转写失败 / 端点不支持 audio → 返回 None，
  **绝不**返回随机 / 占位 / 臆造的转写文本或事件结论。
- 事件因子提取是 modules.event_factor 的确定性透明规则，不是模型生成；
  调用方展示时必须如实标注。
"""
from __future__ import annotations

import logging
from typing import Optional

from modules.event_factor import annotate_hard_logic
from modules.llm_client import config, is_configured

logger = logging.getLogger(__name__)


def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.webm",
    model: str = "whisper-1",
) -> Optional[str]:
    """用 OpenAI Whisper 把音频转写成文本。

    返回转写文本（已 strip）；以下情况返回 ``None``（**不编造**）：
      - ``audio_bytes`` 为空；
      - 未配置 ``STARFIELD_LLM_API_KEY``（llm_client.is_configured() 为 False）；
      - OpenAI SDK 不可用 / 调用异常 / ``base_url`` 非 OpenAI 不支持 audio 接口。

    注意：``base_url`` 若为 OpenAI 兼容服务（非 api.openai.com），其 audio 接口
    大概率 404/不支持，会被下方 ``except`` 捕获并降级为 ``None``。
    """
    if not audio_bytes:
        return None
    if not is_configured():
        logger.info("[voice_event] 未配置 STARFIELD_LLM_API_KEY，跳过语音转写")
        return None
    base_url, _model, api_key = config()
    try:
        import openai

        client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=60)
        # 新版 openai SDK 接受 (filename, bytes) 元组；失败时走 except 降级
        resp = client.audio.transcriptions.create(
            model=model,
            file=(filename, audio_bytes),
        )
        text = getattr(resp, "text", None)
        return text.strip() if text else None
    except Exception as e:  # noqa: BLE001 - 任何 ASR 故障都降级为 None，不臆造
        logger.warning(
            f"[voice_event] 语音转写失败（base_url 非 OpenAI / 不支持 audio / 网络异常）: {e}"
        )
        return None


def extract_event_factors(text: str) -> dict:
    """从转写文本提取事件因子（透明规则标注，复用 event_factor.annotate_hard_logic）。

    返回结构：
        {"available": True, "text": str, "hard_logic": {...}}
        {"available": False, "reason": "空文本"}

    绝不对空文本编造结论。下游据此向用户展示「硬逻辑 / 题材炒作」分类与命中证据。
    """
    if not text or not str(text).strip():
        return {"available": False, "reason": "空文本"}
    hard = annotate_hard_logic([str(text)])
    return {
        "available": True,
        "text": str(text),
        "hard_logic": hard,
    }
