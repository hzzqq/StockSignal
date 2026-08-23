"""
tests/test_scroll_nav.py
======================
锁定 modules/scroll_nav.py 的悬浮导航组件行为（项目内零测试覆盖，272 行）。

该模块把 ▲回到顶部 / ▼回到底部 / C键清缓存拦截 合并进【单一 <script> IIFE】，
经 components.html 一次性注入。本测试验证：
  - _nav_script 所有占位符（__SHOW_TOP__/__THRESH__/__BTH__/__CLS__/__BOTTOM_MARKER__）无残留
  - 暗色 class 拼接、阈值落地、bottom_marker 驱动选择器、show_top 开关
  - inject_scroll_nav 调 markdown + components.html
  - 内嵌 HTML 生成（&#9650;/&#9660; 箭头实体、暗色 class、滚动目标）
  - chat_bottom_anchor 锚点元素

注意（latent issue，本轮仅锁行为不修）：
  _nav_script 仍计算 show_bottom_js 并 .replace("__SHOW_BOTTOM__", ...)，
  但脚本体内从未出现 __SHOW_BOTTOM__ -> show_bottom 参数是死代码（bottom 按钮由 bottom_marker 驱动）。
  后续可移除该参数或真正接上开关。
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
import modules.scroll_nav as sn


PLACEHOLDERS = (
    "__SHOW_TOP__",
    "__SHOW_BOTTOM__",
    "__THRESH__",
    "__BTH__",
    "__CLS__",
    "__BOTTOM_MARKER_JS__",
    "__BOTTOM_MARKER_SEL__",
)


def test_nav_script_replaces_all_placeholders():
    body = sn._nav_script(
        dark=True, threshold_px=300, bottom_threshold=150,
        show_top=True, show_bottom=True, bottom_marker="stChatInput",
    )
    for ph in PLACEHOLDERS:
        assert ph not in body, f"占位符 {ph} 未被替换"
    # 暗色 class 已拼接进按钮
    assert "sf-scroll-bottom-float dark" in body
    # 阈值已落地为数字字面量
    assert "300" in body and "150" in body
    # bottom_marker 驱动的选择器（R79：json.dumps 转义，仍保留双引号字面量）
    assert '[data-testid="stChatInput"]' in body
    # ▲ 启用：show_top=True -> if (true)
    assert "if (true)" in body


def test_nav_script_light_no_dark_class():
    body = sn._nav_script(
        dark=False, threshold_px=300, bottom_threshold=150,
        show_top=True, show_bottom=False, bottom_marker="",
    )
    assert "sf-scroll-bottom-float dark" not in body
    assert "sf-scroll-bottom-float" in body
    # 无 marker -> 比较变为 if ('' !== '')（恒 false，不创建 ▼）
    assert "'__BOTTOM_MARKER__' !== ''" not in body


def test_nav_script_show_top_false_disables_top_button():
    body = sn._nav_script(
        dark=False, threshold_px=300, bottom_threshold=150,
        show_top=False, show_bottom=False, bottom_marker="",
    )
    assert "if (false)" in body


def test_inject_scroll_nav_calls_markdown_and_html(monkeypatch):
    html_cap = {}

    def fake_html(script, height=0, **k):
        html_cap["script"] = script

    monkeypatch.setattr(components, "html", fake_html)

    sn.inject_scroll_nav(show_top=True, dark=True, bottom_marker="stChatInput")

    assert "script" in html_cap, "未通过 components.html 注入"
    payload = html_cap["script"]
    # CSS 与 JS 合并为单次注入（修复前曾拆分两次 markdown，bare mode 下 no-op）
    assert ".sf-scroll-top" in payload, "CSS 未注入"
    assert "<script>" in payload, "导航 JS 未注入"
    # 注入脚本内占位符已完全替换
    for ph in PLACEHOLDERS:
        assert ph not in payload


def test_scroll_bottom_inline_html():
    html = sn.scroll_bottom_inline_html(dark=True)
    assert "&#9660;" in html
    assert "sf-scroll-bottom-inline dark" in html
    assert "ai-chat-box" in html  # 点击滚动聊天框到底

    html2 = sn.scroll_bottom_inline_html(dark=False)
    assert "sf-scroll-bottom-inline dark" not in html2


def test_scroll_inline_button_up_and_down():
    up = sn.scroll_inline_button("up")
    assert "&#9650;" in up
    assert "top:0" in up
    assert "\u56de\u5230\u9876\u90e8" in up  # 回到顶部 title

    down = sn.scroll_inline_button("down")
    assert "&#9660;" in down
    assert "document.body.scrollHeight" in down
    assert "\u56de\u5230\u5e95\u90e8" in down

    # 自定义 label 透传
    lab = sn.scroll_inline_button("down", label="回底")
    assert "回底" in lab


def test_chat_bottom_anchor():
    assert 'id="sf-chat-end"' in sn.chat_bottom_anchor()


def test_nav_script_show_bottom_gate():
    """回归：show_bottom 现在是 ▼ 按钮块的真实开关（R66 修复死代码）。

    - show_bottom=False 时，即便给了 bottom_marker 也抑制 ▼ 块（if (false && ...）；
    - show_bottom=True + marker 才启用（if (true && ... 且选择器存在）。
    """
    body_off = sn._nav_script(
        dark=True, threshold_px=300, bottom_threshold=150,
        show_top=True, show_bottom=False, bottom_marker="stChatInput",
    )
    assert "if (false &&" in body_off, "show_bottom=False 应抑制 ▼ 按钮块"

    body_on = sn._nav_script(
        dark=True, threshold_px=300, bottom_threshold=150,
        show_top=True, show_bottom=True, bottom_marker="stChatInput",
    )
    # R79：json.dumps 转义后，空 marker 变为合法的 JS 空字符串字面量（'""'）
    assert 'if (true &&' in body_on
    assert "if (true &&" in body_on, "show_bottom=True 应启用 ▼ 按钮块"
    assert '[data-testid="stChatInput"]' in body_on


def test_nav_script_escapes_malicious_marker():
    """R79 回归：恶意 marker（含引号/反斜杠）不得破坏 JS 或 CSS 选择器语法。

    - JS 字符串比较上下文：json.dumps 转义，引号被编码为 \\\"，脚本仍合法；
    - CSS 选择器上下文：双引号转义为 \\\"，选择器不提前闭合。
    """
    evil = 'x"y\\z'
    body = sn._nav_script(
        dark=True, threshold_px=300, bottom_threshold=150,
        show_top=False, show_bottom=True, bottom_marker=evil,
    )
    # JS 上下文：转义后的双引号不得以裸 " 形式中断字符串（出现在脚本体内应为 \"）
    # 且原始 evil 作为连续 token 不应整体残留（被编码拆分）
    assert 'x"y' not in body
    # CSS 选择器上下文：转义双引号
    assert '[data-testid="x\\"y\\z"]' in body


def test_back_to_top_button_injects_components_html(monkeypatch):
    """回归：回到顶部按钮必须走 components.html（st.markdown 注入 <script> 会被过滤，点击无反应）。"""
    cap = {}

    def fake_html(script, height=0, **kw):
        cap["script"] = script
        cap["height"] = height

    monkeypatch.setattr(components, "html", fake_html)
    sn.back_to_top_button(label="↑ 回到顶部")
    assert "script" in cap, "未通过 components.html 注入"
    s = cap["script"]
    assert "window.parent" in s or "window.scrollTo" in s, "滚动必须作用在父窗口"
    assert "scrollTo" in s
    assert "回到顶部" in s, "label 透传"


def test_back_to_top_button_custom_label(monkeypatch):
    cap = {}

    def fake_html(script, height=0, **kw):
        cap["script"] = script

    monkeypatch.setattr(components, "html", fake_html)
    sn.back_to_top_button(label="回顶", use_container_width=False)
    assert "回顶" in cap["script"]
    assert "width:100%" not in cap["script"]
