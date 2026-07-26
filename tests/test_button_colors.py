"""
离线测试：modules.button_colors 的 XSS 转义修复。

模块顶部 import streamlit，故在导入前 stub streamlit 模块。
"""
import sys
import types

if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = types.ModuleType("streamlit")

from modules.button_colors import _esc, btn_html


def test_esc_escapes_script():
    assert _esc("<script>") == "&lt;script&gt;"


def test_btn_html_escapes_malicious_label():
    out = btn_html('<img src=x onerror=alert(1)>', kind="primary")
    # 标签被转义为纯文本，不再构成活动 HTML 属性
    assert "<img" not in out
    assert "&lt;img" in out
    assert "onerror=alert(1)&gt;" in out


def test_btn_html_preserves_normal_label():
    out = btn_html("提交", kind="primary")
    assert "提交" in out
    assert "<button" in out


def test_btn_html_escapes_icon():
    out = btn_html("保存", icon='<script>x</script>', kind="success")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "保存" in out
