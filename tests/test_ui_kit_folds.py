# -*- coding: utf-8 -*-
"""tests/test_ui_kit_folds.py — T-262 折叠原语守卫（三范式：有用型/悬停预览/细小化）。

背景（用户 2026-10-12）：折叠方式太单一——有用但内容多的折叠后仍要有用（标签即预览）、
用处不大的折叠后细小化（弱色小字+悬停显示），并引入「搜索 Ctrl K」式悬停浮层范式。

锁四条：
  1. 悬停浮层纯 CSS（无 JS，Streamlit 剥 <script> 不受影响），含 :hover 规则与 z-index；
  2. mini 变体存在（C 细小化触发样式）；
  3. ss_fold_useful 是 contextmanager（with 语法可用）；
  4. 91 页登录历史必须用 A 有用型折叠（标签带最近一条摘要）+ mini 口径说明悬停 chip。
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules import ui_kit  # noqa: E402


def test_hover_css_pure_css_with_hover_and_zindex():
    css = ui_kit._FOLD_CSS
    assert ":hover" in css, "必须有 :hover 规则（悬停浮出）"
    assert "z-index" in css, "浮层必须有 z-index（压过页面层叠）"
    assert "<script" not in css.lower(), "纯 CSS 实现，不得引入 JS"
    assert "ss-hint.mini" in css, "C 细小化变体样式缺失"


def test_fold_hover_html_structure():
    html = ui_kit._fold_hover_html("ⓘ 说明", "<b>内容</b>", mini=True)
    assert 'class="ss-hint mini"' in html
    assert 'class="ss-hint-t"' in html and "ⓘ 说明" in html
    assert 'class="ss-hint-p"' in html and "<b>内容</b>" in html
    plain = ui_kit._fold_hover_html("触发", "面板")
    assert 'class="ss-hint"' in plain and "ss-hint mini" not in plain


def test_fold_useful_is_contextmanager():
    import inspect

    assert isinstance(inspect.signature(ui_kit.ss_fold_useful),
                      inspect.Signature)
    src = inspect.getsource(ui_kit.ss_fold_useful)
    assert "with st.expander" in src, "必须以 st.expander 为折叠载体"
    # 标签拼接契约：summary 非空时进标签（折叠后仍有信息量）
    sig = inspect.signature(ui_kit.ss_fold_useful)
    assert "summary" in sig.parameters and "expanded" in sig.parameters


def test_mypage_login_history_uses_useful_fold():
    """91 页登录历史必须用 A 有用型折叠（标签带最近一条摘要）+ mini 口径 chip。"""
    page = os.path.join(_ROOT, "pages", "91_我的.py")
    src = open(page, encoding="utf-8").read()
    assert "ss_fold_useful(" in src, "登录历史必须用 A 有用型折叠"
    assert "最近：{_hist[0]['时间']}" in src, "折叠标签必须带最近一条摘要"
    assert 'ss_hover_preview("ⓘ 口径说明"' in src and "mini=True" in src, \
        "口径说明必须用 C 细小化悬停 chip（降低存在感）"