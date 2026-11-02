# -*- coding: utf-8 -*-
"""tests/test_market_alerts_panel_ui.py — T-224「近期异动提醒」面板可折叠契约守卫。

纯 AST/源码检查（不导入 streamlit / 不触网）：锁死
- 面板整体包 st.expander 且默认收起（expanded=False）；
- 未读数进折叠标签（收起时信息不丢）；
- 仍为 @safe_fragment 局部 fragment（禁整页 rerun）；
- 既有交互控件 key 不变（仅看未读 / 全部已读 / 逐条已读）。
"""
from __future__ import annotations

import ast
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(_ROOT, "modules", "session.py")


def _session_modules():
    """R-05 拆分（2026-11-02）后会话函数分散在 modules/session*.py。

    session.py 仅保留认证链/初始化/偏好与 re-export，用户区（提醒铃与面板）在
    session_user.py、接口封装在 session_api.py。守卫按前缀全量查找，函数缺失即 fail。
    """
    import glob
    return sorted(glob.glob(os.path.join(_ROOT, "modules", "session*.py")))


def _find_panel_fn():
    """返回 (源码文本, 函数 AST 节点)；跨 session*.py 查找。"""
    for path in _session_modules():
        text = open(path, encoding="utf-8").read()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.FunctionDef) and node.name == "fragment_market_alerts_panel":
                return text, node
    raise AssertionError("fragment_market_alerts_panel 函数不存在（面板被移除？）")


def _panel_source() -> str:
    text, node = _find_panel_fn()
    return ast.get_source_segment(text, node)


def test_panel_wrapped_in_collapsed_expander():
    src = _panel_source()
    assert "with st.expander(" in src, "面板未使用 st.expander（不可折叠）"
    assert "expanded=False" in src, "expander 应默认收起（expanded=False）"


def test_unread_count_in_expander_label():
    """未读数必须在折叠标签里——收起时用户仍能一眼看到有无新异动。"""
    src = _panel_source()
    assert "近期异动提醒（自动扫描 · 后台调度）" in src, "面板标题丢失"
    assert 'label += f" · 未读 {unread} 条"' in src, "未读数未进折叠标签"


def test_still_safe_fragment_not_full_rerun():
    _text, fn = _find_panel_fn()
    decs = [ast.unparse(d) for d in fn.decorator_list]
    assert any('safe_fragment' in d and "市场异动提醒面板" in d for d in decs), \
        f"面板必须保持 safe_fragment 局部刷新（禁整页 rerun，铁律 §一-3）；实际装饰器: {decs}"


def test_interaction_keys_preserved():
    """控件 key 是交互锚点，折叠重构不得改变（改动会丢用户已读操作状态）。"""
    src = _panel_source()
    for key in ('"panel_unread_only"', '"panel_mark_all"', 'f"panel_read_{it.get(\'id\')}"'):
        assert key in src, f"交互控件 key 丢失: {key}"
