"""
tests/test_scroll_nav.py
======================
锁定 modules/scroll_nav.py 的悬浮导航组件行为（v3 · 2026-09-13 重设计后）。

该模块把 ▲回到顶部 / ▼回到底部 / C键清缓存拦截 合并进【单一 <script> IIFE】，
经 components.html 一次性注入。本测试验证：
  - _nav_script 所有占位符（含 v3 新增 __SCROLL_CONTAINER_JS__/__TOPICON__/__TOPCLS__）无残留
  - 暗色 class 拼接、阈值落地、bottom_marker 驱动选择器、show_top 开关
  - inject_scroll_nav 调 components.html
  - 内嵌 HTML 生成（&#9650;/&#9660; 箭头实体、暗色 class、滚动目标）
  - chat_bottom_anchor 锚点元素

v3 新增断言（回归防护）：
  - 回到顶部按钮**不得**再用 top:50%（右侧中部）→ 改为右下角 bottom
  - 按钮必须为圆形（border-radius:50%）
  - 默认阈值降到 120（「首次下滑即现」）
  - 滚动目标必须是【探测出的 Streamlit 滚动容器】而非裸 window.scrollTo
    （v2 缺陷：window.scrollTo 对 Streamlit 主内容区无效 → 点击无反应）
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
    # v3 新增
    "__SCROLL_CONTAINER_JS__",
    "__TOPICON__",
    "__TOPCLS__",
    # T-197/T-201
    "__NAV_INDEX_JSON__",
    "__NAV_QS__",
    "__EXTRA_JS__",
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
    assert "sf-scroll-top dark" in body
    # 阈值已落地为数字字面量
    assert "300" in body and "150" in body
    # bottom_marker 驱动的选择器
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
    assert "sf-scroll-top dark" not in body


def test_nav_script_show_top_false_disables_top_button():
    body = sn._nav_script(
        dark=False, threshold_px=300, bottom_threshold=150,
        show_top=False, show_bottom=False, bottom_marker="",
    )
    assert "if (false)" in body


def test_inject_scroll_nav_calls_components_html(monkeypatch):
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
    assert "scrollHeight" in down
    assert "\u56de\u5230\u5e95\u90e8" in down

    # 自定义 label 透传
    lab = sn.scroll_inline_button("down", label="回底")
    assert "回底" in lab


def test_chat_bottom_anchor():
    assert 'id="sf-chat-end"' in sn.chat_bottom_anchor()


def test_nav_script_show_bottom_gate():
    """回归：show_bottom 是 ▼ 按钮块的真实开关（R66 修复死代码）。"""
    body_off = sn._nav_script(
        dark=True, threshold_px=300, bottom_threshold=150,
        show_top=True, show_bottom=False, bottom_marker="stChatInput",
    )
    assert "if (false &&" in body_off, "show_bottom=False 应抑制 ▼ 按钮块"

    body_on = sn._nav_script(
        dark=True, threshold_px=300, bottom_threshold=150,
        show_top=True, show_bottom=True, bottom_marker="stChatInput",
    )
    assert 'if (true &&' in body_on
    assert '[data-testid="stChatInput"]' in body_on


def test_nav_script_escapes_malicious_marker():
    """R79 回归：恶意 marker（含引号/反斜杠）不得破坏 JS 或 CSS 选择器语法。"""
    evil = 'x"y\\z'
    body = sn._nav_script(
        dark=True, threshold_px=300, bottom_threshold=150,
        show_top=False, show_bottom=True, bottom_marker=evil,
    )
    assert 'x"y' not in body
    assert '[data-testid="x\\"y\\z"]' in body


# ══════════════════════════════════════════════════════════════════════════
# v3 重设计回归（2026-09-13）
# ══════════════════════════════════════════════════════════════════════════

def test_v3_top_button_is_bottom_right_round():
    """v3：▲ 按钮必须在【右下角】且为【圆形】。

    缺陷背景：v2 用 top:50% + translateY(-50%) 把按钮放在页面**右侧中部**，
    与需求「右下角」不符；且用户反馈「放在页面底部」不接受。
    """
    css = sn.SCROLL_NAV_CSS
    block_start = css.index(".sf-scroll-top{")
    block_end = css.index("}", block_start)
    block = css[block_start:block_end]
    assert "bottom:28px" in block, "▲ 按钮必须固定在右下角"
    assert "top:50%" not in block, "▲ 按钮不得使用 top:50%（v2 的右侧中部缺陷）"
    assert "top:auto" in block, "v2 遗留的 top:50% 必须以 top:auto 显式复位"
    assert "border-radius:50%" in block, "▲ 按钮必须是圆形"
    assert "right:24px" in block


def test_v3_default_threshold_is_low():
    """v3：默认阈值下调到 120，实现「用户第一次下滑就出现」。"""
    assert sn.DEFAULT_TOP_THRESHOLD == 120
    body = sn._nav_script(
        dark=False, threshold_px=sn.DEFAULT_TOP_THRESHOLD, bottom_threshold=150,
        show_top=True, show_bottom=False, bottom_marker="",
    )
    assert "120" in body


def test_v3_scrolls_real_container_not_bare_window():
    """v3 核心回归：滚动目标必须是【探测出的 Streamlit 滚动容器】。

    缺陷背景：v2 直接 `P.scrollTo({top:0})`；但 Streamlit 主内容区滚动发生在
    `[data-testid="stAppViewContainer"]` / `.stMain` / `.block-container` 等内部
    可滚动元素上，滚 window 完全无效 → 用户看到「按钮形态变化但页面不动」。
    """
    body = sn._nav_script(
        dark=False, threshold_px=120, bottom_threshold=150,
        show_top=True, show_bottom=False, bottom_marker="",
    )
    # 探测函数与容器候选选择器必须存在
    assert "C_get" in body, "未生成滚动容器探测函数"
    assert "stAppViewContainer" in body, "未包含 Streamlit 主容器候选选择器"
    assert "C_top" in body, "未生成回到顶部执行函数"
    # 执行函数内应优先滚容器（el.scrollTo），window 仅作兜底
    i = body.index("function C_top()")
    seg = body[i:i + 420]
    assert "el.scrollTo" in seg, "应优先滚动探测到的容器元素"
    assert "P.scrollTo" in seg, "window 应保留为兜底路径"

    # CSS 覆盖所有候选（含 .block-container 这种 padding 容器）
    assert "stMain" in body


def test_v3_container_selectors_cover_known_streamlit_dom():
    """候选选择器须覆盖 Streamlit 已知的几个滚动容器。"""
    sels = " ".join(sn._SCROLL_SELECTORS)
    for need in ("stAppViewContainer", "stMain", "block-container"):
        assert need in sels, f"滚动容器候选缺少 {need}"


def test_v3_appearance_is_fixed_not_repositioned():
    """「出现后位置固定不变」：visible 态只切透明度/指针事件，不得重设定位。

    若 visible 规则里出现 top/bottom/right/left，则按钮会在出现瞬间跳位。
    """
    css = sn.SCROLL_NAV_CSS
    i = css.index(".sf-scroll-top.visible")
    seg = css[i:i + 160]
    for prop in ("top:", "bottom:", "right:", "left:"):
        assert prop not in seg, f"visible 态不应重设定位属性 {prop}"


def test_back_to_top_button_is_noop_since_t193(monkeypatch):
    """T-193：页内回顶按钮停用——全局悬浮 ▲ 已覆盖，且页内 iframe 按钮
    实测 onclick JS 泄漏为可见文本（股吧页截图实证）。调用必须零注入。"""
    def boom(script, height=0, **kw):
        raise AssertionError("back_to_top_button 已停用，不得再注入 components.html")

    monkeypatch.setattr(components, "html", boom)
    sn.back_to_top_button(label="↑ 回到顶部")  # 不应抛错、不应注入


def test_back_to_top_button_noop_with_custom_label(monkeypatch):
    """no-op 对任意参数组合均静默（兼容既有 12 处调用点）。"""
    def boom(script, height=0, **kw):
        raise AssertionError("不得注入")

    monkeypatch.setattr(components, "html", boom)
    sn.back_to_top_button(label="回顶", use_container_width=False)
    sn.back_to_top_button()


def test_v3_top_icon_is_inline_svg():
    """v3：▲ 图标改为内联 SVG（随 currentColor 变色，无外部依赖）。"""
    body = sn._nav_script(
        dark=False, threshold_px=120, bottom_threshold=150,
        show_top=True, show_bottom=False, bottom_marker="",
    )
    assert "<svg" in body
    assert "currentColor" in body
    assert "aria-label" in body, "按钮须有无障碍标签"


# ───────────── T-201：命令面板跳转 / 父文档 CSS 管道 / 导航查询串 ─────────────

def test_palette_enter_uses_anchor_click_not_parent_location():
    """T-201：面板 Enter 必须点击面板内真实 <a>（父文档元素）——组件 iframe 脚本
    直接赋值 window.parent.location 会被 sandbox（无 allow-top-navigation）静默
    拦截，历史版本 Enter 跳转失效的根因。
    """
    body = sn._nav_script(dark=False, threshold_px=120, bottom_threshold=150,
                          show_top=True, show_bottom=False, bottom_marker="",
                          nav_index=[{"label": "x", "icon": "x", "href": "/x", "group": "g"}],
                          nav_qs="token%3Dtok")
    assert "as[idx].click()" in body
    assert "window.parent.location.href" not in body, \
        "脚本发起的父页导航会被 sandbox 拦截，必须走父文档锚点点击"


def test_palette_dynamic_stock_href_carries_nav_qs():
    """T-201：6 位股票代码直达 href 必须拼导航查询串（token+u+prefs），
    否则代码直达跳转后丢登录态/风格。
    """
    body = sn._nav_script(dark=False, threshold_px=120, bottom_threshold=150,
                          show_top=True, show_bottom=False, bottom_marker="",
                          nav_index=[{"label": "x", "icon": "x", "href": "/x", "group": "g"}],
                          nav_qs="token%3Dtok123")
    assert "pick_stock=' + kw + (SS_QS ? '&' + SS_QS : '')" in body
    assert "var SS_QS" in body


def test_inject_scroll_nav_emits_parent_css_pipe(monkeypatch):
    """T-201：SCROLL_NAV_CSS 必须同步经 st.markdown 注入【父文档】——组件 iframe
    内的 <style> 作用不到父文档，而命令面板/▲▼按钮 DOM 全部创建在父文档
    （历史版本面板样式实际缺失，搜索弹层裸 HTML 的根因）。
    """
    md_captured = []
    monkeypatch.setattr(st, "markdown",
                        lambda payload, **k: md_captured.append(payload))
    monkeypatch.setattr(components, "html", lambda payload, height=0, **k: None)
    sn.inject_scroll_nav(show_top=True, dark=True)
    assert any(".ss-cmd-box" in p and ".sf-scroll-top" in p for p in md_captured), \
        "父文档未收到面板/悬浮按钮 CSS"


def test_inject_scroll_nav_passes_nav_qs(monkeypatch):
    """T-201：inject_scroll_nav 的 nav_qs 参数必须落到脚本 SS_QS（动态 href 用）。"""
    html_cap = {}

    def fake_html(script, height=0, **k):
        html_cap["script"] = script

    monkeypatch.setattr(st, "markdown", lambda payload, **k: None)
    monkeypatch.setattr(components, "html", fake_html)
    sn.inject_scroll_nav(nav_index=[{"label": "x", "icon": "x",
                                     "href": "/x", "group": "g"}],
                         nav_qs="token%3Dtok123")
    assert "SS_QS" in html_cap["script"]
    assert "token%3Dtok123" in html_cap["script"]


def test_palette_display_gated_by_open_class():
    """T-201：面板必须默认 display:none、仅 .open 显示——面板 DOM 常驻父文档，
    缺门控时全屏 backdrop 永久可见（吞整页点击+打断 mega hover 链；T-197 潜伏
    缺陷，父文档 CSS 管道补齐后显形）。
    """
    css = sn.SCROLL_NAV_CSS
    assert "#ssCmdPalette{display:none}" in css
    assert "#ssCmdPalette.open{display:block}" in css
    # 门控规则必须先于/独立于 backdrop 规则存在（缺一即裸奔）
    assert ".ss-cmd-backdrop{position:fixed" in css
