"""modules/voice_event.py — 语音转写事件因子（真空白补全，2026-11-02 增强）。

为什么补这块：
- 项目焦点「事件因子适配器」已接 P1 真实信号源（modules/event_factor）；但「语音」
  这一输入通道一直缺位——用户口头/录音讲的市场事件无法进入事件因子体系。
- 这是 stock-partner / 功能版块 Skill 映射里反复标注、却始终未落地的空白。

管道（端到端）：
    音频 bytes → ASR 转写 → 事件因子提取（复用 event_factor 透明规则标注）

ASR 实现：复用 modules.llm_client 的 STARFIELD_LLM_API_KEY / base_url
    调 OpenAI Whisper（audio.transcriptions）。兼容端点（本地 vLLM / OpenRouter 等）
    大多不支持 audio 接口 → 捕获降级返回结构化诊断，由调用方诚实提示，不编造转写。

2026-11-02 增强（独立化 / 可发现性 / 诚实降级强化）：
- transcribe_audio_result：返回结构化诊断 {ok,text,status,message}，区分
  empty / no_key / unsupported(404 不支持 audio) / error / ok，让前端给出精确、
  诚实的降级文案，而非一刀切「不可用」。
- classify_urgency / classify_sentiment_lean：确定性词表分类（时间敏感度 /
  情绪倾向），与 event_factor 的「硬逻辑 vs 题材炒作」正交，纯规则、不臆造。
- build_voice_event_card：把转写文本 → 因子 + 紧急度 + 情绪倾向 汇总为一张
  结构化卡片数据，供前端统一渲染（独立、自包含）。

红线（来自 working memory / event_factor）：
- 无音频 / 未配置 key / 转写失败 / 端点不支持 audio → 返回 None / 结构化失败，
  **绝不**返回随机 / 占位 / 臆造的转写文本或事件结论。
- 所有分类都是确定性透明规则，不是模型生成；展示时必须如实标注。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from modules.event_factor import annotate_hard_logic
from modules.llm_client import config, is_configured

logger = logging.getLogger(__name__)


# ── 确定性词表（与 event_factor 的硬逻辑/题材炒作正交，纯规则、不臆造）──
# 时间敏感度：突发/已发生 vs 临近 vs 笼统
_URGENT_LExICON = (
    "突发", "刚刚", "昨晚", "今日", "今早", "盘后", "盘前", "已公告", "已中标", "已签约",
    "已批复", "已停产", "已减持", "已增持", "已回购", "已暴雷", "刚刚公告", "最新", "刚刚发布",
)
_SOON_LEXICON = (
    "即将", "下周", "本月", "下月", "预告", "拟", "计划", "将", "预期", "有望", "准备",
    "传将", "称拟", "预计", "即将发布", "待公告", "排队", "本周",
)
# 情绪倾向（利好 / 利空）
_POS_LEXICON = (
    "中标", "预增", "增长", "扩产", "签约", "获批", "利好", "回购", "增持", "盈利", "突破",
    "上涨", "超预期", "扭亏", "订单", "大单", "合作", "扩产", "上调", "景气", "复苏",
)
_NEG_LEXICON = (
    "减持", "预减", "亏损", "退市", "诉讼", "处罚", "下调", "暴雷", "违约", "停产", "下跌",
    "利空", "降级", "调查", "停牌", "商誉减值", "计提", "爆雷", "风险", "警示", "立案",
)


def transcribe_audio_result(
    audio_bytes: bytes,
    filename: str = "audio.webm",
    model: str = "whisper-1",
) -> Dict[str, Optional[str]]:
    """语音转写（结构化诊断版）。

    返回：
        {"ok": True,  "text": str, "status": "ok",          "message": "转写成功"}
        {"ok": False, "text": None, "status": "empty",        "message": "未检测到音频输入"}
        {"ok": False, "text": None, "status": "no_key",       "message": "未配置 STARFIELD_LLM_API_KEY…"}
        {"ok": False, "text": None, "status": "unsupported",  "message": "base_url 不支持 audio 接口…"}
        {"ok": False, "text": None, "status": "error",        "message": "转写失败：<具体异常>"}
    不编造转写文本；任何异常都降级并返回可读 message，绝不抛出未处理异常。
    """
    if not audio_bytes:
        return {"ok": False, "text": None, "status": "empty", "message": "未检测到音频输入"}
    if not is_configured():
        return {
            "ok": False, "text": None, "status": "no_key",
            "message": "未配置 STARFIELD_LLM_API_KEY，无法语音转写",
        }
    base_url, _model, api_key = config()
    try:
        import openai  # 局部导入，未安装时走 except 降级

        client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=60)
        resp = client.audio.transcriptions.create(
            model=model,
            file=(filename, audio_bytes),
        )
        text = getattr(resp, "text", None)
        if not text or not str(text).strip():
            return {"ok": False, "text": None, "status": "empty_result",
                    "message": "转写返回为空（音频可能无声或不可识别）"}
        return {"ok": True, "text": str(text).strip(), "status": "ok", "message": "转写成功"}
    except Exception as e:  # noqa: BLE001 - 任何 ASR 故障都降级，不臆造
        msg = str(e)
        # 区分「端点不支持 audio 接口」（兼容服务常返回 404 / audio 相关错误）
        # 与其余网络/SDK 异常，给出更诚实的具体文案。
        if "404" in msg or "not found" in msg.lower() or "audio" in msg.lower():
            status = "unsupported"
            message = (
                f"当前 base_url 不支持 whisper audio 接口（{msg[:120]}）；"
                "请改用 OpenAI 官方端点或支持 audio 的兼容服务。"
            )
        else:
            status = "error"
            message = f"语音转写失败（网络/SDK 异常）：{msg[:160]}"
        logger.warning("[voice_event] %s: %s", status, msg)
        return {"ok": False, "text": None, "status": status, "message": message}


def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.webm",
    model: str = "whisper-1",
) -> Optional[str]:
    """语音转写（兼容旧契约：成功返回文本、其余返回 None）。

    旧接口保留：原调用方与测试仍按 str | None 使用；新调用方请用
    transcribe_audio_result 拿结构化诊断。
    """
    return transcribe_audio_result(audio_bytes, filename, model).get("text")


def extract_event_factors(text: str) -> dict:
    """从转写文本提取事件因子（透明规则标注，复用 event_factor.annotate_hard_logic）。

    返回结构：
        {"available": True, "text": str, "hard_logic": {...}}
        {"available": False, "reason": "空文本"}
    绝不对空文本编造结论。
    """
    if not text or not str(text).strip():
        return {"available": False, "reason": "空文本"}
    hard = annotate_hard_logic([str(text)])
    return {"available": True, "text": str(text), "hard_logic": hard}


def classify_urgency(text: str) -> Dict[str, object]:
    """时间敏感度分类（确定性词表，与硬逻辑/题材炒作正交）。

    返回 {"level": "urgent"|"soon"|"neutral", "keywords": [...], "label": "已发生/临近/笼统"}。
    纯规则、不臆造；无命中即 neutral。
    """
    t = str(text)
    hit_urgent = [k for k in _URGENT_LExICON if k in t]
    hit_soon = [k for k in _SOON_LEXICON if k in t]
    if hit_urgent:
        return {"level": "urgent", "keywords": hit_urgent, "label": "已发生/突发"}
    if hit_soon:
        return {"level": "soon", "keywords": hit_soon, "label": "临近/预告"}
    return {"level": "neutral", "keywords": [], "label": "笼统"}


def classify_sentiment_lean(text: str) -> Dict[str, object]:
    """情绪倾向分类（确定性词表：利好 / 利空 / 中性）。

    返回 {"lean": "positive"|"negative"|"neutral", "keywords": [...],
          "label": "利好/利空/中性"}。命中多者胜；正负同现时标 "mixed" 并附双方关键词。
    纯规则、不臆造；无命中即 neutral。
    """
    t = str(text)
    hit_pos = [k for k in _POS_LEXICON if k in t]
    hit_neg = [k for k in _NEG_LEXICON if k in t]
    if hit_pos and hit_neg:
        return {"lean": "mixed", "keywords": hit_pos + hit_neg,
                "label": "多空交织", "pos": hit_pos, "neg": hit_neg}
    if hit_pos:
        return {"label": "利好", "lean": "positive", "keywords": hit_pos}
    if hit_neg:
        return {"label": "利空", "lean": "negative", "keywords": hit_neg}
    return {"label": "中性", "lean": "neutral", "keywords": []}


def build_voice_event_card(text: str) -> Dict[str, object]:
    """把转写文本汇总为一张结构化卡片数据（因子 + 紧急度 + 情绪倾向）。

    供前端统一渲染为「独立、自包含」的语音事件卡。所有字段均来自确定性规则，
    无命中即标注 neutral/na，绝不编造。
    """
    factors = extract_event_factors(text)
    urgency = classify_urgency(text)
    sentiment = classify_sentiment_lean(text)
    return {
        "text": str(text),
        "factors": factors,
        "urgency": urgency,
        "sentiment": sentiment,
    }
