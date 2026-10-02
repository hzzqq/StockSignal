# -*- coding: utf-8 -*-
"""tests/test_drawer.py — T-198 右侧滑出详情抽屉组件守卫。

覆盖：js_escape 全转义面（防 onclick 注入/语法破坏）/ preview_button 结构与
转义透传 / drawer_js 全局接口完整性 / drawer_css 变量驱动 / widgets extra_js
接线不脱落。
"""
from __future__ import annotations

import inspect

from modules.drawer import drawer_css, drawer_js, js_escape, preview_button


# ───────────── js_escape ─────────────

def test_js_escape_backslash_and_quotes():
    """反斜杠/单双引号全转义（onclick 单引号串内不破坏语法）。"""
    out = js_escape("a\\b'c\"d")
    assert "\\'" in out      # 单引号带反斜杠前缀
    assert '\\"' in out      # 双引号带反斜杠前缀
    assert "\\\\" in out     # 反斜杠翻倍
    assert out.count("'") == out.count("\\'")  # 无裸单引号


def test_js_escape_newline_and_angle():
    """换行/回车转义为 \\n\\r 字面；尖括号实体化（防 </button> 注入闭合）。"""
    out = js_escape("a\nb\rc<scri</button>pt>")
    assert "\\n" in out and "\\r" in out
    assert "\n" not in out and "\r" not in out
    assert "&lt;" in out and "&gt;" in out
    assert "</button>" not in out


def test_js_escape_backslash_first():
    """转义顺序正确：反斜杠必须最先转义（否则后续转义的前缀被二次转义）。"""
    out = js_escape("\\")
    assert out == "\\\\"


# ───────────── preview_button ─────────────

def test_preview_button_structure():
    """结构：ss-preview-btn 类 + onclick 调 __ssDrawer.show + 三参透传。"""
    btn = preview_button("标题T", "正文B", "元信息M")
    assert 'class="ss-preview-btn"' in btn
    assert "__ssDrawer" in btn and ".show(" in btn
    assert "标题T" in btn and "正文B" in btn and "元信息M" in btn


def test_preview_button_escapes_hostile_title():
    """恶意标题（引号/尖括号/换行）不破坏 onclick 属性与 HTML 结构。"""
    hostile = "x'); alert(1); ('</button>"
    btn = preview_button(hostile, "body")
    # 裸的 ') 闭合序列不得出现（已被转义）；</button> 注入被实体化
    assert "alert(1)" not in btn.replace("\\'", "") or "\\'" in btn
    assert "</button>" not in btn[btn.index("onclick="):btn.index("👁")]
    assert btn.count("ss-preview-btn") == 1  # 按钮结构完整（未被注入劈开）


def test_preview_button_label_and_multiline_body():
    """自定义 label 透传；多行正文换行转义为 \\n 字面（抽屉内 pre-wrap 显示）。"""
    btn = preview_button("T", "line1\nline2", label="👁 快速看")
    assert "👁 快速看" in btn
    assert "\\n" in btn and "\n" not in btn.split('show(')[1].split("')")[0]


# ───────────── drawer_js / drawer_css ─────────────

def test_drawer_js_global_api():
    """JS 挂载 window.__ssDrawer（show/hide）+ 关闭交互 + backdrop 一次性挂载。"""
    js = drawer_js()
    assert "window.__ssDrawer" in js
    assert "show: function(title, html, meta)" in js
    assert "hide: ssDrawerHide" in js
    assert "ss-drawer-close" in js and "ss-drawer-backdrop" in js
    assert js.count("getElementById('ssDrawerRoot')") >= 1


def test_drawer_css_variable_driven():
    """CSS 全走风格变量（六套主题自动适配），含滑出动画与层级。"""
    css = drawer_css()
    assert "var(--card" in css and "var(--acc1" in css and "var(--border" in css
    assert "var(--txt" in css
    assert "right:-460px" in css and "right:0" in css   # 滑出/展开两态
    assert "z-index:100004" in css                       # 高于 mega(100000)/cmd(100002)
    assert ".ss-preview-btn" in css


def test_drawer_css_and_js_pair():
    """CSS 类名与 JS 创建的 DOM 类名一一对应（防样式漂移）。"""
    css, js = drawer_css(), drawer_js()
    for cls in ("ss-drawer-panel", "ss-drawer-head", "ss-drawer-title",
                "ss-drawer-meta", "ss-drawer-body", "ss-drawer-close"):
        assert cls in css and cls in js, cls


# ───────────── 接线不脱落 ─────────────

def test_widgets_extra_js_includes_drawer():
    """widgets.inject_global_widgets 必须把 drawer_js 并入 extra_js（接线防脱落）。"""
    from modules import widgets
    src = inspect.getsource(widgets.inject_global_widgets)
    assert "drawer_js" in src
    assert "topnav_extra_js() + drawer_js()" in src


def test_topnav_injects_drawer_css():
    """render_topnav 必须注入 drawer_css（预览按钮样式随顶栏加载）。"""
    from modules import top_nav
    src = inspect.getsource(top_nav.render_topnav)
    assert "drawer_css" in src
