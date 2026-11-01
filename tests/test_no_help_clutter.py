# -*- coding: utf-8 -*-
"""界面减负守卫：pages/ 禁止「使用说明 / 常见问题」与「快捷入口 / 快捷跳转」。

背景（2026-11-02 老板指令）：
  - 全项目堆积大量「💡 使用说明 / 常见问题」折叠块，正常人不需要看 →
    已从 14/23/33/42/47/52/53/91 八页清除；唯一豁免 96_新手教程.py
    （FAQ 是该教程页的核心功能本体，不是冗余帮助）。
  - 全项目的「快捷入口 / 快捷跳转」导航区一律删除，仅保留首页 app.py
    （不在 pages/ 目录，天然不在本守卫范围）与 50 页接收首页跳转聚焦的
    逻辑（其字符串不含「快捷入口」字样，注释除外）。

规则（AST 字符串常量扫描，注释/docstring 天然放行）：
  - Guard A：pages/*.py 的字符串常量含「使用说明」或「常见问题」→
    仅 96_新手教程.py 豁免，其余页 fail。
  - Guard B：pages/*.py 的字符串常量含「快捷入口」或「快捷跳转」→
    一律 fail（含 f-string；拼接逃逸不在防御范围——保守规则，宁误报不漏报）。

回归防什么：把已删的说明块/入口块当「优化」加回来，或新页面复制旧模板。
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages"
FAQ_EXEMPT = {"96_新手教程.py"}
FAQ_TERMS = ("使用说明", "常见问题")
JUMP_TERMS = ("快捷入口", "快捷跳转")


def _string_consts(tree: ast.AST):
    """yield 所有字符串常量（含 f-string 的 FormattedValue 内文本，取 JoinedStr 全文）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            parts = [
                v.value for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            ]
            if parts:
                yield "".join(parts)


def _collect(page: Path):
    tree = ast.parse(page.read_text(encoding="utf-8"))
    return list(_string_consts(tree))


@pytest.mark.parametrize("page", sorted(PAGES.glob("*.py")))
def test_no_help_faq_blocks_outside_tutorial(page):
    if page.name in FAQ_EXEMPT:
        pytest.skip("96_新手教程：FAQ 是教程页核心功能本体，豁免")
    hits = [
        (i, s) for i, s in enumerate(_collect(page))
        if any(t in s for t in FAQ_TERMS)
    ]
    assert not hits, (
        f"{page.name} 出现「使用说明/常见问题」字符串（界面减负守卫：帮助类内容"
        f"统一收敛到 96_新手教程，正常页面不放说明块）：\n  "
        + "\n  ".join(repr(s)[:160] for _, s in hits)
    )


@pytest.mark.parametrize("page", sorted(PAGES.glob("*.py")))
def test_no_quick_jump_blocks_anywhere_in_pages(page):
    hits = [
        s for s in _collect(page)
        if any(t in s for t in JUMP_TERMS)
    ]
    assert not hits, (
        f"{page.name} 出现「快捷入口/快捷跳转」字符串（全项目仅首页 app.py 保留"
        f"快捷入口，pages/ 一律禁止）：\n  "
        + "\n  ".join(repr(s)[:160] for s in hits)
    )
