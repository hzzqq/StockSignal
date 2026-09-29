# -*- coding: utf-8 -*-
"""
tests/test_ui_kit_nav_inject.py — T-180 导航丢样式守卫。

【事故】st.switch_page 导航进入新页面时，ui_kit 组件样式全部丢失（卡片裸文本），
F5 刷新后恢复。根因：inject_kit_css 用 st.session_state 去重（「全页面仅一次」），
但 Streamlit 导航会重建 DOM——旧页面的 <style> 元素随旧 DOM 消失，而
session_state 跨页面保留 → 去重标记让新页面跳过注入 → 组件样式全丢。
F5 新建 WebSocket session → session_state 重置 → 注入恢复（与现象完全吻合）。

【契约】CSS 注入必须每次调用都执行（幂等、无 session_state 去重标记）。
主题层 apply_theme 本就每次注入（所以侧边栏/hero 导航后正常），kit 层对齐。
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import ui_kit  # noqa: E402


def test_no_session_state_dedup_marker():
    """去重标记常量必须已移除（存在即导航丢样式 bug 回潮）。"""
    assert not hasattr(ui_kit, "_INJECTED_KEY"), (
        "_INJECTED_KEY 去重标记回潮——st.switch_page 导航重建 DOM 后"
        "新页面会跳过 CSS 注入（导航后组件裸奔事故 T-180）"
    )


def test_inject_kit_css_always_injects():
    """inject_kit_css 代码体不得访问 st.session_state（docstring 教训文字不算）；
    可重复调用不抛。"""
    import ast

    src = inspect.getsource(ui_kit.inject_kit_css)
    tree = ast.parse(src)
    accesses = [
        n for n in ast.walk(tree)
        if (isinstance(n, ast.Attribute) and n.attr == "session_state")
    ]
    assert not accesses, (
        "inject_kit_css 代码体访问 st.session_state——去重会导致导航后丢样式"
    )
    # 行为：连续调用两次均不抛异常（幂等）
    ui_kit.inject_kit_css()
    ui_kit.inject_kit_css()


def test_theme_layer_stays_always_inject():
    """对照：主题层（每次注入，导航后正常的那条路径）不得引入去重。"""
    from modules import ui_theme

    src = inspect.getsource(ui_theme.apply_theme)
    assert "session_state.get" not in src or "theme_mode" in src, (
        "apply_theme 引入去重会导致同样的导航丢样式"
    )
