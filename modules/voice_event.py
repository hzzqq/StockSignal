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

import json
import logging
import os
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


def render_voice_event_block() -> None:
    """语音事件因子可复用渲染块（2026-11-02 抽离；2026-11-03 历史升级为持久化）。

    录音/上传 → ASR 转写 → 结构化因子卡（事件性质 / 时间敏感度 / 情绪倾向）→ 落盘存档。
    历史真理源 = data/voice_events.json（跨会话、跨页共享）；会话内存不再另存一份。
    诚实降级：未配置 key / 端点不支持 audio / 转写失败 → 精确文案，绝不编造、不落盘。
    """
    import streamlit as st
    from datetime import datetime
    from modules.ui_kit import xc_content_card, xc_warn_box
    from modules.voice_event import transcribe_audio_result, build_voice_event_card

    st.divider()
    st.subheader("🎙️ 语音事件因子")
    st.caption(
        "说一段市场事件（如「XX 公司中标大合同」「美联储加息利空成长股」「某行业突发停产」），"
        "自动转写并标注「硬逻辑 / 题材炒作 / 时间敏感度 / 情绪倾向」。"
        "需配置 STARFIELD_LLM_API_KEY 且 base_url 为支持 whisper 的端点；"
        "否则按具体原因诚实降级，绝不编造转写文本或事件结论。"
    )
    # 持久化历史（跨会话可复核）：真理源 = data/voice_events.json
    _ve_hist = load_voice_events(20)
    if _ve_hist:
        with st.expander(f"🕘 历史语音事件（已存档 {len(_ve_hist)} 条，跨会话可复核）", expanded=False):
            for _h in _ve_hist:
                st.caption(f"· {_h.get('ts', '')} ｜ {_h.get('text', '')}")
                _ve_meta = " ｜ ".join(str(_h.get(k)) for k in ("event", "urgency", "sentiment") if _h.get(k))
                if _ve_meta:
                    st.markdown(f"🏷️ {_ve_meta}")
            if st.button("🗑️ 清空历史语音事件", key="ve_clear_hist"):
                st.session_state["ve_clear_confirm"] = True
            if st.session_state.get("ve_clear_confirm"):
                st.warning("确认清空全部已存档语音事件？此操作不可恢复。")
                _c1, _c2 = st.columns(2)
                if _c1.button("确认清空", key="ve_clear_cfm"):
                    _n = clear_voice_events()
                    if _n < 0:
                        st.error("清空失败，请检查文件权限（未删除任何数据）。")
                    else:
                        st.session_state.pop("ve_clear_confirm", None)
                        st.rerun()
                if _c2.button("取消", key="ve_clear_cancel"):
                    st.session_state.pop("ve_clear_confirm", None)
                    st.rerun()
        st.caption("💾 语音事件存档于本机 data/voice_events.json（应用级共享，非按用户隔离）")
    _ve_audio = st.audio_input("🎙️ 录音或上传音频", key="ve_audio", help="支持浏览器录音或上传音频文件")
    if _ve_audio is not None:
        _ve_bytes = _ve_audio.getbuffer().tobytes()
        with st.spinner("转写中…"):
            _ve_res = transcribe_audio_result(_ve_bytes, filename=getattr(_ve_audio, "name", "audio.webm"))
        if not _ve_res["ok"]:
            # 诚实降级：按结构化 status 给出精确文案，不编造
            xc_warn_box(f"⚠️ {_ve_res.get('message') or '语音转写不可用'}（转写文本与事件结论均不编造）")
        else:
            _ve_card = build_voice_event_card(_ve_res["text"])
            st.success(f"转写：{_ve_card['text']}")
            _ve_hl = _ve_card["factors"].get("hard_logic", {})
            _ve_ur = _ve_card["urgency"]
            _ve_se = _ve_card["sentiment"]
            # 自包含因子卡：事件性质 + 时间敏感度 + 情绪倾向（全部确定性规则，如实标注）
            _ve_lines: list = []
            if _ve_hl.get("status") == "ok":
                _ve_lines.append(f"**事件性质**：{_ve_hl.get('hard_logic')}（透明规则，非 AI 洞见）")
                _ve_evd = "、".join(_ve_hl.get("evidence", []))
                if _ve_evd:
                    _ve_lines.append(f"命中证据：{_ve_evd}")
            else:
                _ve_lines.append(f"**事件性质**：{_ve_hl.get('reason', '无法判定（无明确硬逻辑/题材关键词）')}")
            if _ve_ur["level"] != "neutral":
                _ve_lines.append(f"**时间敏感度**：{_ve_ur['label']}（{ '、'.join(_ve_ur['keywords']) }）")
            if _ve_se["lean"] != "neutral":
                _ve_se_kw = "、".join(_ve_se.get("keywords", []))
                _ve_lines.append(f"**情绪倾向**：{_ve_se['label']}（{ _ve_se_kw }）")
            _ve_body = "  \n".join(_ve_lines) or "（无明确因子命中，转写文本已保留于上方）"
            xc_content_card(
                "🏷️ 语音事件标注",
                body=_ve_body,
                icon="🎙️",
            )
            # 持久化：标注成功才落盘（转写失败绝不写占位）；历史区即上方「历史语音事件」
            _ve_entry = {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "text": _ve_card["text"],
                "event": str(_ve_hl.get("hard_logic") or _ve_hl.get("reason") or ""),
                "urgency": str(_ve_ur.get("label") or ""),
                "sentiment": str(_ve_se.get("label") or ""),
            }
            if save_voice_event(_ve_entry):
                st.caption("💾 已存档（data/voice_events.json，跨会话可复核）")
            else:
                st.caption("⚠️ 本机存档失败，本次标注仅当前会话可见")


# ── 持久化（2026-11-03 新方向：语音事件跨会话沉淀，数据链闭环）────────────────
# 为什么补：语音→ASR→因子标注这条链此前走到「标注卡」就断了——ve_history 只存
# session_state，刷新即丢，语音事件无法沉淀为可复核的事件数据。
# 存储：data/voice_events.json（SS_DATA_DIR 隔离，与 nav_freq.json 同模式），
#       atomic_json_dump 原子写防并发损坏；本机共享存储（非按用户隔离），UI 已如实标注。
# 诚实红线：转写失败/空文本绝不落盘；读损坏文件→[] 不臆造；清空返回真实条数。
_VOICE_EVENTS_MAX = 200


def _voice_events_path() -> str:
    """语音事件持久化文件路径（SS_DATA_DIR 隔离）。"""
    _data_dir = os.environ.get("SS_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    return os.path.join(_data_dir, "voice_events.json")


def load_voice_events(limit: int = 20) -> list:
    """读取持久化语音事件（新的在前）。文件缺失/损坏 → []（不臆造）。"""
    try:
        _path = _voice_events_path()
        if not os.path.exists(_path):
            return []
        with open(_path, "r", encoding="utf-8") as _f:
            _data = json.load(_f)
        if not isinstance(_data, list):
            return []
        _items = [it for it in _data if isinstance(it, dict)]
        return _items[:limit] if isinstance(limit, int) and limit > 0 else _items
    except Exception as _e:
        logger.warning("[voice_event] 读取持久化语音事件失败: %s", _e)
        return []


def save_voice_event(entry: dict) -> bool:
    """追加一条语音事件到持久层（新的在前，截断至上限）。fail-safe：失败返回 False。

    诚实红线：entry 无有效 text 一律拒绝写入（转写失败绝不落占位数据）。
    旧文件损坏时重建而非中断（旧数据已不可靠，保留只会持续污染读取）。
    """
    try:
        if not isinstance(entry, dict) or not str(entry.get("text", "")).strip():
            return False
        _path = _voice_events_path()
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        _items: list = []
        if os.path.exists(_path):
            try:
                with open(_path, "r", encoding="utf-8") as _f:
                    _old = json.load(_f)
                if isinstance(_old, list):
                    _items = [it for it in _old if isinstance(it, dict)]
            except Exception:
                _items = []
        _items.insert(0, entry)
        _items = _items[:_VOICE_EVENTS_MAX]
        from modules.atomic_io import atomic_json_dump
        atomic_json_dump(_items, _path)
        return True
    except Exception as _e:
        logger.warning("[voice_event] 保存语音事件失败: %s", _e)
        return False


def clear_voice_events() -> int:
    """清空持久化语音事件，返回真实清除条数；文件缺失返回 0；失败返回 -1（诚实语义）。"""
    try:
        _path = _voice_events_path()
        if not os.path.exists(_path):
            return 0
        try:
            with open(_path, "r", encoding="utf-8") as _f:
                _old = json.load(_f)
            _n = len(_old) if isinstance(_old, list) else 0
        except Exception:
            _n = 0
        os.remove(_path)
        return _n
    except Exception as _e:
        logger.warning("[voice_event] 清空语音事件失败: %s", _e)
        return -1
