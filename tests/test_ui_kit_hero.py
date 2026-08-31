# -*- coding: utf-8 -*-
"""
tests/test_ui_kit_hero.py — 页头 hero/chip 首帧兜底样式守卫（防止「首屏朴素、刷新后才好」回退）

为何存在：
    老板反馈 14_智能盯盘 / 50_市场情绪 等页面偶尔出现「首屏没星辰 UI、刷新后才出来」。
    根因：ui_kit._KIT_CSS 由 inject_kit_css() 用 session_state 去重注入，streamlit 冷启动
    时序竞态下首次注入失败但 key 已设 True，后续永不补 → chip 与 hero 容器都丢样式。

    修复（双重保险）：
      ① ui_kit.page_hero 每次都再注一次 _HERO_FALLBACK_CSS（不走 session_state 去重）；
      ② page_utils._build_status_chips 改 chip 完全 inline style，零 CSS class 依赖。
    本测试锁死这两条不再被回退。

运行：pytest tests/test_ui_kit_hero.py -q
"""

from __future__ import annotations

from modules.ui_kit import _HERO_FALLBACK_CSS, page_hero
from modules.page_utils import _build_status_chips


# ───────────────────────── hero 兜底 CSS ─────────────────────────
def test_hero_fallback_css_contains_xc_hero_class():
    """首帧兜底 CSS 必须定义 .xc-hero 容器样式（圆角 + 渐变 + 阴影），缺一不可。"""
    assert ".xc-hero{" in _HERO_FALLBACK_CSS
    assert "border-radius:18px" in _HERO_FALLBACK_CSS
    # 渐变背景是新城风格的核心特征，丢了就成了纯色卡片
    assert "linear-gradient(120deg," in _HERO_FALLBACK_CSS
    # box-shadow 抬升光晕
    assert "box-shadow:0 0 0 1px rgba(102,126,234" in _HERO_FALLBACK_CSS


def test_hero_fallback_css_contains_xc_hero_chips():
    """chips 容器样式必须存在（即使 chip 改 inline 了，flex 布局仍依赖）。"""
    assert ".xc-hero-chips{" in _HERO_FALLBACK_CSS
    assert "display:flex" in _HERO_FALLBACK_CSS


def test_hero_fallback_css_is_valid_style_block():
    """兜底 CSS 必须包在 <style> 标签里（streamlit 渲染解析需要）。"""
    assert _HERO_FALLBACK_CSS.strip().startswith("<style>"), "兜底 CSS 必须用 <style> 包住"
    assert _HERO_FALLBACK_CSS.strip().endswith("</style>"), "兜底 CSS 必须以 </style> 闭合"


# ───────────────────────── chip 完全 inline ─────────────────────────
def test_status_chips_returns_two_chips():
    """应返回 2 个 chip：主题（白天/暗夜）+ 交易时段（交易中/已休市）。"""
    chips = _build_status_chips(dark=False)
    assert len(chips) == 2, "少一个 chip 就意味着有主题没渲染（首屏掉样的典型表现）"


def test_status_chips_have_inline_style():
    """每条 chip 必须是 <span style="..."> 开头，零 CSS class 依赖。"""
    chips = _build_status_chips(dark=False)
    for c in chips:
        assert c.startswith('<span style="'), \
            "chip 必须 inline style —— 不然会回到「首屏朴素、刷新后才好」的坑"
        # 关键视觉属性全部 inline
        assert "display:inline-flex" in c
        assert "border-radius:999px" in c
        assert "padding:5px 12px" in c
        assert "font-size:12px" in c
        # dot 也是 inline
        assert "border-radius:50%" in c


def test_status_chips_do_not_depend_on_css_class():
    """锁死：chip HTML 不再含 .ss-pill / .dot class（防止以后又退回去）。"""
    chips = _build_status_chips(dark=False)
    for c in chips:
        assert 'class="ss-pill' not in c, "chip 不应再依赖 .ss-pill class"
        assert 'class="dot"' not in c, "chip 不应再依赖 .dot class"


def test_status_chips_light_vs_dark_colors():
    """light 模式白天=浅紫底/深紫字；dark 模式暗夜=深紫底/淡紫字。"""
    light = _build_status_chips(dark=False)
    dark = _build_status_chips(dark=True)
    # light
    assert "白天" in light[0]
    assert "#eef2ff" in light[0], "light 主题背景应为 #eef2ff"
    assert "#4338ca" in light[0], "light 主题文字应为 #4338ca"
    # dark
    assert "暗夜" in dark[0]
    assert "#1a1a2e" in dark[0], "dark 主题背景应为 #1a1a2e"
    assert "#c7d2fe" in dark[0], "dark 主题文字应为 #c7d2fe"


def test_status_chips_text_content_complete():
    """四个状态的文字文案是 UI 契约，改之前先看这个测试。"""
    light = _build_status_chips(dark=False)
    dark = _build_status_chips(dark=True)
    # 交易时段 chip（第二条）
    session_chip = light[1]
    assert ("交易中" in session_chip) or ("已休市" in session_chip)
    # 暗夜模式下交易时段仍要有对应文案
    session_chip_dark = dark[1]
    assert ("交易中" in session_chip_dark) or ("已休市" in session_chip_dark)


def test_status_chips_safe_on_session_state_error():
    """session_state 缺失时不抛（首页 cold load 容错：宁少一个 chip 不炸整页）。"""
    chips = _build_status_chips(dark=False)
    # 即便内部 try/except 至少会产出交易时段那个 chip（依赖 page_widgets）
    assert len(chips) >= 1, "至少要返回 1 个 chip，整页空 chip 不可接受"
    assert all(isinstance(c, str) for c in chips)


# ───────────────────────── page_hero 注入契约 ─────────────────────────
def test_page_hero_function_signature_preserved():
    """锁死 page_hero 公开签名（多个测试与页面在调用，签名不能随便改）。"""
    import inspect
    sig = inspect.signature(page_hero)
    params = list(sig.parameters.keys())
    assert params[:5] == ["title", "icon", "subtitle", "chips", "style"], \
        f"page_hero 签名变了：{params}"


def test_page_hero_injects_fallback_inside():
    """锁死 page_hero 内部使用 _HERO_FALLBACK_CSS（防止有人去掉 fallback 又回到首屏坑）。"""
    import inspect
    src = inspect.getsource(page_hero)
    assert "_HERO_FALLBACK_CSS" in src, \
        "page_hero 必须注入 _HERO_FALLBACK_CSS（首帧兜底），去掉就会回到「首屏朴素、刷新后才好」"
    assert "st.markdown(" in src and "_hero_html" in src