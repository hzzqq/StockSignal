"""
tests/test_ai_engine_style.py — T-308 回应方式（style）路由守卫

锁住 ai_answer 的 style → STYLE_PRESETS 路由契约：
- 4 种 style 的 system prompt 互不相同（quick 继承 SYSTEM_PROMPT 本体，其余为结构化变体）；
- max_tokens / timeout 按 preset 下发，研报预算显著大于快速（扩大研报回答的保障）；
- 非法 / 缺省 style 回落 quick（既有调用方零影响）；
- LLM 配置过但调用失败 → 规则回退回答头部带降级标注（诚实数据语义）。

全程离线：monkeypatch ai_engine.llm_client 为捕获型 fake、_resolve_multiple 恒空。
Mutation 目标：把 ai_answer 的 preset 路由改回单 SYSTEM_PROMPT / 定值预算 → 必红。
"""
import pytest

from modules import ai_engine


class _FakeLLM:
    """捕获型 fake llm_client：记录调用参数，可配置返回值。"""

    def __init__(self, answer="FAKE_LLM_ANSWER"):
        self.calls = []
        self._answer = answer

    def is_configured(self):
        return True

    def answer_with_llm(self, system, prompt, history=None, max_tokens=0, timeout=0):
        self.calls.append({
            "system": system, "prompt": prompt, "history": history,
            "max_tokens": max_tokens, "timeout": timeout,
        })
        return self._answer


_Q = "A股当前整体方向怎么看"  # 无股票名/无事件词 → 直达 LLM 路径的通用问题


@pytest.fixture()
def route_env(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(ai_engine, "llm_client", fake)
    monkeypatch.setattr(ai_engine, "_resolve_multiple", lambda q: [])
    return fake


def test_style_routes_four_different_prompts(route_env):
    fake = route_env
    for style in ("quick", "report", "debate", "teach"):
        out = ai_engine.ai_answer(_Q, None, style=style)
        assert out["answer"] == "FAKE_LLM_ANSWER"
    assert len(fake.calls) == 4
    systems = [c["system"] for c in fake.calls]
    # 4 个 system 互不相同（mutation：删掉 preset 路由 → 4 个全同 → 红）
    assert len(set(systems)) == 4
    assert systems[0] == ai_engine.SYSTEM_PROMPT
    assert "深度研报" in systems[1] and "核心结论" in systems[1]
    assert "多空辩论" in systems[2] and "裁判裁决" in systems[2]
    assert "教学解释" in systems[3] and "先说人话" in systems[3]


def test_style_budgets_follow_presets(route_env):
    fake = route_env
    for style in ("quick", "report", "debate", "teach"):
        ai_engine.ai_answer(_Q, None, style=style)
    for call, style in zip(fake.calls, ("quick", "report", "debate", "teach")):
        preset = ai_engine.STYLE_PRESETS[style]
        assert call["max_tokens"] == preset["max_tokens"]
        assert call["timeout"] == preset["timeout"]
    # 研报预算必须显著大于快速（「扩大研报回答」的核心保障）
    assert ai_engine.STYLE_PRESETS["report"]["max_tokens"] \
        > ai_engine.STYLE_PRESETS["quick"]["max_tokens"]
    # 超时预算不得超 llm_client 钳值（90s）
    assert all(p["timeout"] <= 90 for p in ai_engine.STYLE_PRESETS.values())


def test_invalid_or_missing_style_falls_back_to_quick(route_env):
    fake = route_env
    ai_engine.ai_answer(_Q, None, style="不存在的样式")
    ai_engine.ai_answer(_Q, None)  # 缺省（兼容既有调用方）
    assert [c["system"] for c in fake.calls] == \
        [ai_engine.SYSTEM_PROMPT, ai_engine.SYSTEM_PROMPT]
    assert fake.calls[0]["max_tokens"] == fake.calls[1]["max_tokens"]


def test_llm_failure_rule_fallback_is_labeled(monkeypatch):
    fake = _FakeLLM(answer=None)  # 模拟 LLM 调用失败 / 超时
    monkeypatch.setattr(ai_engine, "llm_client", fake)
    monkeypatch.setattr(ai_engine, "_resolve_multiple", lambda q: [])
    out = ai_engine.ai_answer(_Q, None, style="report")
    # 诚实语义：回退回答必须如实标注降级来源，防「看似研报实为模板」
    assert out["answer"].startswith("（LLM 暂不可用，以下为规则引擎精简版）")
    assert out["independent"] is True


def test_llm_not_configured_no_degraded_label(monkeypatch):
    # LLM 从未配置 → 规则回答是既有正常形态，不额外加降级标注
    class _OffLLM:
        @staticmethod
        def is_configured():
            return False

    monkeypatch.setattr(ai_engine, "llm_client", _OffLLM())
    monkeypatch.setattr(ai_engine, "_resolve_multiple", lambda q: [])
    out = ai_engine.ai_answer(_Q, None)
    assert not out["answer"].startswith("（LLM 暂不可用")
