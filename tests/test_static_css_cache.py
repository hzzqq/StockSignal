"""tests/test_static_css_cache.py — R88 静态 CSS 常量化 / 主题缓存守卫。

验证：
1. ``dashboard_sf_css()`` 按主题缓存（同主题两次调用返回同一对象），且内容含关键选择器。
2. ``widgets._sidebar_nav_css(dark)`` 按主题缓存，且与改造前的逐段拼接结果逐字节一致（无视觉回归）。
3. ``ui_kit._HERO_FALLBACK_CSS`` 为模块级常量（首帧兜底已无需每次重建）。
"""

from unittest.mock import patch

import modules.ui_theme as ui_theme
import modules.widgets as widgets
from modules.widgets import _nav_active_css


def setup_function(_fn):
    ui_theme._DASHBOARD_SF_CSS_CACHE.clear()
    widgets._SIDEBAR_NAV_CSS_CACHE.clear()


def teardown_function(_fn):
    ui_theme._DASHBOARD_SF_CSS_CACHE.clear()
    widgets._SIDEBAR_NAV_CSS_CACHE.clear()


def test_dashboard_sf_css_cached_per_theme():
    with patch.object(ui_theme, "_theme_is_dark", return_value=False):
        a = ui_theme.dashboard_sf_css()
        b = ui_theme.dashboard_sf_css()
    assert a is b  # 命中缓存：同一对象，未重建
    assert ".sf-card" in a and "</style>" in a
    # 暗色应为不同缓存项
    with patch.object(ui_theme, "_theme_is_dark", return_value=True):
        c = ui_theme.dashboard_sf_css()
    assert c is not a
    assert "--bg:#0f0f23" in c  # 暗色根变量


def _orig_sidebar_css(dark: bool) -> str:
    """改造前 render_sidebar_nav 的逐段拼接（用于回归比对，确保零视觉差异）。"""
    return (
        '<style>'
        '[data-testid="stSidebarNav"],[data-testid="stSidebarNavItems"]{display:none!important;}'
        '/* 强制侧边栏常驻：禁用折叠按钮，避免用户误关后找不到导航 */'
        '[data-testid="stSidebarCollapseButton"]{display:none!important;}'
        '/* 紧凑侧边栏导航：减少分组标题与链接间距，降低长导航的视觉负担 */'
        '[data-testid="stSidebar"] .stMarkdown [data-testid="stCaptionContainer"] {margin-top:4px!important;margin-bottom:2px!important;font-size:12px!important;}'
        '[data-testid="stSidebar"] [data-testid="stPageLink"] a {padding:4px 8px!important;margin:1px 0!important;border-radius:8px!important;}'
        '[data-testid="stSidebar"] [data-testid="stButton"] button {padding:4px 8px!important;min-height:28px!important;}'
        + _nav_active_css(dark) +
        '</style>'
    )


def test_sidebar_nav_css_cached_and_identical_to_original():
    for dark in (False, True):
        new_css = widgets._sidebar_nav_css(dark)
        assert new_css == _orig_sidebar_css(dark)  # 零视觉回归
        assert widgets._sidebar_nav_css(dark) is new_css  # 命中缓存


def test_hero_fallback_css_is_module_constant():
    import modules.ui_kit as ui_kit
    assert isinstance(ui_kit._HERO_FALLBACK_CSS, str)
    assert ".xc-hero" in ui_kit._HERO_FALLBACK_CSS
    # 常量身份稳定（非每次调用重建）
    assert ui_kit._HERO_FALLBACK_CSS is ui_kit._HERO_FALLBACK_CSS
