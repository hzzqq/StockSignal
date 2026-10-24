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
    """结构：ss-preview-btn 类 + 三个 textarea 承载三参（T-315 事件委托范式）。

    T-315：不再用内联 onclick（Streamlit markdown 会剥离 → 抽屉永不弹出），
    改为 data 承载 + drawer_js 的 click 委托。
    """
    btn = preview_button("标题T", "正文B", "元信息M")
    assert 'class="ss-preview-btn"' in btn
    assert "onclick=" not in btn, "内联 onclick 会被 Streamlit 剥离（T-315 缺陷回潮）"
    assert "__ssDrawer" not in btn, "触发逻辑不应内联在 HTML 里（应走事件委托）"
    for kind in ("title", "body", "meta"):
        assert f'data-k="{kind}"' in btn, f"缺少 {kind} 承载 textarea"
    assert btn.count('class="ss-preview-src"') == 3
    assert "标题T" in btn and "正文B" in btn and "元信息M" in btn


def test_preview_button_escapes_hostile_title():
    """恶意标题（引号/尖括号/换行）不得破坏 HTML 结构或注入标签。"""
    hostile = "x'); alert(1); ('</button><script>bad()</script>"
    btn = preview_button(hostile, "body")
    assert "</button>" not in btn.split('class="ss-preview-btn"')[0], "textarea 内出现了裸闭合标签"
    assert "<script>" not in btn, "注入的 script 标签必须被实体化"
    assert btn.count('class="ss-preview-btn"') == 1, "按钮结构被劈开"
    assert btn.count("</textarea>") == 3


def test_preview_button_label_and_multiline_body():
    """自定义 label 透传；多行正文原样留在 textarea（保留换行，不被压成空格）。"""
    btn = preview_button("T", "line1\nline2", label="👁 快速看")
    assert "👁 快速看" in btn
    assert "line1\nline2" in btn, "多行正文换行必须保留（textarea 承载的意义所在）"


# ───────────── drawer_js / drawer_css ─────────────

def test_drawer_js_global_api():
    """JS 挂载 __ssDrawer（show/hide）+ 关闭交互 + backdrop 一次性挂载。

    T-315 修正：本段 JS 运行在 components.html 的组件 iframe 内，句柄必须挂到
    父窗口 P（= window.parent），否则业务侧 window.parent.__ssDrawer 取不到；
    历史断言 window.__ssDrawer 实为缺陷形态（抽屉建在 iframe 里，用户不可见）。
    """
    js = drawer_js()
    assert "P.__ssDrawer" in js, "抽屉句柄必须挂父窗口（P），否则业务调用取不到"
    assert "window.__ssDrawer" not in js, "不得再挂到 iframe 自身 window（T-315 缺陷回潮）"
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


def test_drawer_js_click_delegation():
    """T-315 触发层：父文档 click 委托绑定 ss-preview-btn，读 textarea 调 show。

    历史缺陷：预览按钮靠内联 onclick，被 Streamlit markdown 剥离（React #231），
    抽屉容器虽正确注入却永不弹出——单测只查 HTML 字符串含 onclick，未能拦住。
    """
    js = drawer_js()
    assert "ss-preview-btn" in js, "缺少预览按钮点击委托"
    assert "ss-preview-src" in js, "委托未读取承载 textarea"
    assert "data-k" in js, "未按 data-k 区分 title/body/meta"
    assert "if (!P.__ssDrawerBound) {" in js, "缺少委托启用守卫（防止重复绑定 / 被禁用）"
    assert "P.document.addEventListener('click'" in js, "委托必须绑在父文档"
    assert "catch (eB)" in js, "触发段缺少自隔离 try（异常会阻断后续 extra_js）"
    css = drawer_css()
    assert ".ss-preview-wrap" in css, "缺少按钮包裹样式"


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
