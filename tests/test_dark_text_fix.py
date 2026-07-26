"""
离线纯单元测试：验证 dark_text_fix 中数据派生文本已被 HTML 转义（防存储型 XSS）。

由于模块顶层 import streamlit，若环境中 streamlit 不可用会导致导入即崩溃，
因此在导入模块前用桩对象替掉 streamlit，保证测试可在无 streamlit 环境离线运行。
"""

import sys
import types

# 在导入被测模块之前替掉 streamlit，避免 import 失败
sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))

from modules.dark_text_fix import _esc, colored_text, highlight_value, chip_html


def test_esc_basic():
    assert _esc("<script>") == "&lt;script&gt;"
    assert _esc('"') == "&quot;"
    assert _esc("'") == "&#x27;"


def test_esc_malicious_stock_name_colored_text():
    evil = '<img src=x onerror=alert(1)>'
    out = colored_text(evil, layer="value", emphasis="up")
    # 关键 XSS 向量（`<` 起始的标签）必须被转义，使 onerror= 退化为惰性文本
    assert "<script>" not in out
    assert "<img" not in out
    assert "&lt;img" in out  # 证明 payload 已被转义


def test_esc_malicious_stock_name_highlight_value():
    evil = '<img src=x onerror=alert(1)>'
    out = highlight_value(evil)
    assert "<script>" not in out
    assert "<img" not in out
    assert "&lt;img" in out


def test_esc_malicious_stock_name_chip_html():
    evil = '<img src=x onerror=alert(1)>'
    out = chip_html(evil, state="active", icon="★")
    assert "<script>" not in out
    assert "<img" not in out
    assert "&lt;img" in out


def test_plain_text_passthrough():
    # 正常文本不应被加扰，且保留预期 class 结构
    out = colored_text("贵州茅台", layer="title")
    assert "贵州茅台" in out
    assert 'class="sf-text-title"' in out
    out2 = highlight_value(3.14, fmt=".2f", direction="up")
    assert "3.14" in out2
