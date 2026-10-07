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


def _panel_source() -> str:
    with open(SRC_PATH, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "fragment_market_alerts_panel":
            return ast.get_source_segment(open(SRC_PATH, encoding="utf-8").read(), node)
    raise AssertionError("fragment_market_alerts_panel 函数不存在（面板被移除？）")


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
    tree = ast.parse(open(SRC_PATH, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "fragment_market_alerts_panel")
    decs = [ast.unparse(d) for d in fn.decorator_list]
    assert any('safe_fragment' in d and "市场异动提醒面板" in d for d in decs), \
        f"面板必须保持 safe_fragment 局部刷新（禁整页 rerun，铁律 §一-3）；实际装饰器: {decs}"


def test_interaction_keys_preserved():
    """控件 key 是交互锚点，折叠重构不得改变（改动会丢用户已读操作状态）。"""
    src = _panel_source()
    for key in ('"panel_unread_only"', '"panel_mark_all"', 'f"panel_read_{it.get(\'id\')}"'):
        assert key in src, f"交互控件 key 丢失: {key}"
