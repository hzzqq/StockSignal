# -*- coding: utf-8 -*-
"""Streamlit API 卫生守卫（防回退）。

1. 禁止 ``use_container_width=``：Streamlit 1.5x 起废弃，且**会在页面上渲染成黄色
   deprecation 警告框** —— 用户侧表现为「页面莫名多出警告块 / 布局发虚」，
   属于真实的「前端渲染异常」。等价写法：True → ``width="stretch"``；
   False → ``width="content"``。
2. 未来可继续加：``width=`` 非法取值、``rerun(scope=)`` 使用规范等。

注：``modules/scroll_nav.py`` 的 ``back_to_top_button(use_container_width=...)`` 是
**自有参数名**（非 Streamlit kwarg），本守卫按「Call 的 keyword 名」判定，不误伤。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SKIP = ("__pycache__", "/tests/", "\\tests\\", ".venv", "site-packages", "/node_modules/")


def _iter_sources():
    for p in ROOT.rglob("*.py"):
        s = str(p)
        if any(x in s for x in _SKIP):
            continue
        yield p


def test_no_deprecated_use_container_width():
    """不得再用 use_container_width=（废弃，且会在页面渲染黄色警告框）。"""
    offenders = []
    for p in _iter_sources():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and any(
                k.arg == "use_container_width" for k in node.keywords
            ):
                offenders.append(f"{p.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        'use_container_width 已废弃（1.5x 起会在页面渲染黄色 deprecation 警告框）；'
        '请改为 width="stretch"(True) / width="content"(False)：\n  '
        + "\n  ".join(offenders)
    )
