"""
tests/test_ui_kit_hint_fold.py
==============================
T-277 第三批：提示卡长文折叠基元守卫——短文案内联 / 长文案折叠（内容零删减）/
XSS 转义不回退 / 五处调用点接入。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.ui_kit import _hint_html, _info_banner_html, _HINT_COLLAPSE_THRESHOLD  # noqa: E402

_UI_KIT = (Path(__file__).resolve().parents[1] / "modules" / "ui_kit.py").read_text(encoding="utf-8")


def test_short_hint_inline():
    """短文案（≤阈值）保持内联，不折叠。"""
    out = _hint_html("这是一句简短提示")
    assert "<details" not in out
    assert "简短提示" in out


def test_long_hint_folded_and_content_preserved():
    """长文案（>阈值）折叠为 <details>，且全文零删减（诚实语义）。"""
    long_text = "长提示内容" * 40  # 200 字符
    assert len(long_text) > _HINT_COLLAPSE_THRESHOLD
    out = _hint_html(long_text)
    assert "<details" in out and "xc-hint-fold" in out, "长文案未折叠"
    assert "展开" in out
    # 全文必须在折叠体内（内容零删减）
    assert long_text in out, "折叠后内容被截断（诚实语义回退）"


def test_hint_xss_escaped():
    """XSS 转义不回退：<script> 不进 HTML。"""
    out = _hint_html("<script>alert(1)</script>" + "x" * 200)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_empty_hint_returns_empty():
    assert _hint_html(None) == "" and _hint_html("") == ""


def test_info_banner_long_text_folded():
    """info_banner 长文案同样折叠。"""
    html = _info_banner_html("很长的横幅文案" * 30, "info")
    assert "xc-hint-fold" in html and "很长的横幅文案" * 30 in html


def test_five_call_sites_use_primitive():
    """五处调用点接入 _hint_html（防绕回内联 str(hint) 拼接）。"""
    n = _UI_KIT.count("_hint_html(")
    assert n >= 5, f"接入点数 {n} < 5（有调用点未走基元）"
    assert "xc-hint-fold" in _UI_KIT, "折叠样式缺失"
