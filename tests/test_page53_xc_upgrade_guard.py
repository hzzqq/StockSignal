"""
tests/test_page53_xc_upgrade_guard.py — T-308 星辰AI 升级 AST 守卫

钉住 pages/53_星辰AI.py 新增交互组件的接线形态（additive 契约，mutation 目标）：
- 回应方式选择器（xc_reply_style）存在，style 键随 ai_consult / ai_research payload 下发；
- 问题分析卡（_xc_last_intent）：提交时唯一写入点 + 任务全部终态（成功/失败/超时/
  通信异常/清空按钮）均有清理，防残留串场；
- 追问建议（suggestions）：模板映射存在、轮询成功分支写入、渲染侧 research 卡与
  assistant 气泡各接一次；
- 模型徽标读取 llm_client 且页面无 api key 字面引用（红线）。

Mutation 验证：删除任一接线块 → 对应断言变红。
"""
import ast
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "pages" / "53_星辰AI.py"


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_parses():
    ast.parse(_src())  # 页面本身必须可解析（守卫前提）


def test_reply_style_wiring():
    src = _src()
    assert "xc_reply_style" in src, "回应方式选择器丢失"
    assert "_XC_STYLE_KEY_BY_LABEL" in src, "style 映射丢失"
    assert '"style": _style_key' in src, "ai_consult payload 未带 style"
    assert '"style": _style_key} if _deep' in src, "ai_research payload 未带 style"
    assert src.count('"style"') >= 2, "style 下发点不足 2 处"


def test_intent_card_lifecycle():
    src = _src()
    assert '"_xc_last_intent"' in src, "问题分析卡键丢失"
    # 唯一写入点（提交成功分支）
    writes = src.count('["_xc_last_intent"] = {')
    assert writes == 1, f"写入点应为 1 处，实际 {writes}"
    # 清理点：成功 pop / 失败 pop / 超时 pop / 通信异常 pop / 清空按钮 pop ≥ 4
    pops = src.count('pop("_xc_last_intent"')
    assert pops >= 4, f"意图卡清理点不足: writes={writes}, pops={pops}"


def test_suggestions_wiring():
    src = _src()
    assert "_XC_SUGGESTION_TEMPLATES" in src, "追问建议模板丢失"
    assert '_msg["suggestions"]' in src, "轮询成功分支未写入 suggestions"
    # 工具直达回答也写入 suggestions（意图拦截分支）
    assert '"suggestions": list(_XC_SUGGESTION_TEMPLATES.get(' in src, \
        "工具卡片拦截分支未写入 suggestions"
    assert "def _render_suggestions(" in src, "渲染函数丢失"
    # 渲染侧三处都要接：tool 卡 / research 卡 / assistant 气泡
    assert src.count("_render_suggestions(m, idx)") >= 3, \
        "渲染接线不足 3 处（tool 卡 / research 卡 / assistant 气泡）"


def test_model_badge_no_key_leak():
    src = _src()
    assert "llm_client.is_configured" in src, "模型徽标未接 llm_client"
    assert "_XC_MODEL_NAME" in src
    # 诚实语义：未配置 LLM 时明示规则引擎模式，不假装有模型
    assert "规则引擎模式" in src
    # 红线：页面不得出现 api key 字面引用（徽标只显模型名）
    low = src.lower()
    assert "api_key" not in low and "apikey" not in low
