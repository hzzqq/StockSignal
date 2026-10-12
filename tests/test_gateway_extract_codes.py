"""
tests/test_gateway_extract_codes.py
===================================
T-271 修复的单测补充：mcp_server.gateway._extract_codes 的 6 位 A 股代码抽取。

修复背景（期末考试 Bad Case #1）：原 ``\\b\\d{6}\\b`` 在**中文邻接**下永不命中
——``\\b`` 基于 \\w（中文字符属 \\w），"600667现在" 的 7→现 之间无词边界。
导致「600667现在多少钱」这类最常见的「代码+中文」提问抽不到代码、意图路由
整个失效。修复后用前后非数字断言 ``(?<!\\d)\\d{6}(?!\\d)``。

本测试直测正则本身（不经 detect_intent），逐场景钉死边界；并用 mutation
（回退 \\b）验证中文邻接用例确实变红——防修复被无声回退。
"""
import re

import pytest

from mcp_server.gateway import _extract_codes, detect_intent


def test_chinese_adjacency_after():
    """修复目标场景①：代码后紧跟中文（原 \\b 在此永不命中）。"""
    assert _extract_codes("600667现在多少钱") == ["600667"]
    assert _extract_codes("600667最近有什么消息") == ["600667"]
    assert _extract_codes("000001今天涨停了吗") == ["000001"]


def test_chinese_adjacency_both_sides():
    """修复目标场景②：代码两侧都是中文。"""
    assert _extract_codes("帮我看一下600667走势如何") == ["600667"]
    assert _extract_codes("对比600667和000001哪个好") == ["600667", "000001"]


def test_plain_and_space_separated_still_work():
    """原有能力不回退：纯代码 / 空格 / 标点分隔。"""
    assert _extract_codes("600667") == ["600667"]
    assert _extract_codes("600667 怎么样") == ["600667"]
    assert _extract_codes("600667,000001") == ["600667", "000001"]
    assert _extract_codes("SH600667") == ["600667"]  # 前缀后邻接（S 是非数字）


def test_no_partial_match_in_longer_digits():
    """负向：7/8/11 位连续数字不得抽出 6 位子串（前后非数字断言保证）。"""
    assert _extract_codes("1234567") == []          # 7 位
    assert _extract_codes("20261012 是日期") == []   # 8 位日期
    assert _extract_codes("13812345678 是手机号") == []  # 11 位手机号


def test_no_match_without_code():
    """负向：无数字 / 不足 6 位 → 空列表。"""
    assert _extract_codes("太极实业怎么样") == []
    assert _extract_codes("") == []
    assert _extract_codes("12345") == []


def test_order_preserved_for_multi_codes():
    """多代码按出现顺序返回（对比类提问依赖顺序）。"""
    assert _extract_codes("000001 和 600519 与 300750") == ["000001", "600519", "300750"]


@pytest.mark.parametrize("q,tool", [
    ("600667现在多少钱", "get_realtime_quote"),     # 修复前 fallback 的 Bad Case
    ("600667最近有什么消息", "stock_news"),
    ("600667风险怎么样", "risk_assess"),
])
def test_detect_intent_recovers_with_code(q, tool):
    """集成：代码抽取修复后，detect_intent 对「代码+中文」提问恢复高置信路由。"""
    r = detect_intent(q)
    assert r["tool"] == tool, f"意图路由仍失效: {r}"
    assert r["confidence"] >= 0.85
    assert r["params"].get("code") == "600667"


# ── mutation 锚点：修复回退 \\b 时，中文邻接用例必须集体变红 ──────────────
def test_regex_uses_lookaround_not_word_boundary():
    """正则实现契约：必须用前后非数字断言，不得回退 \\b（中文邻接下 \\b 失效）。"""
    import inspect
    from mcp_server import gateway
    src = inspect.getsource(gateway._extract_codes)
    assert "(?<!\\d)" in src and "(?!\\d)" in src, "非数字断言缺失（疑似回退 \\b）"
    assert "\\b\\d{6}\\b" not in src, "检测到已回退到 \\b 版本（中文邻接 Bad Case 复发）"
