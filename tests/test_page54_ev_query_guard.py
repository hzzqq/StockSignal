"""T-258 页 54 个股事件因子查询分支守卫（AST，全离线）。

背景（2026-10-12 线上 UnboundLocalError）：fragment_p1_ev 的「无信号」提示原本挂在
``if _q`` 的 else 上——空输入时引用未绑定 ef → 页面模块被隔离；且查询无结果
（available=False）时提示从未显示。修复后契约：
  - 空输入分支（if _q 的 orelse）不得引用任何 ``ef`` 名字；
  - 无结果提示（xc_info_banner + "无事件因子信号"）必须位于
    ``if ef.get("available")`` 的 orelse 内；
  - 空输入分支必须给出「输入代码」引导文案。

mutation：把提示挪回 if _q 的 orelse → 本守卫变红。
"""
from __future__ import annotations

import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

PAGE = os.path.join(_ROOT, "pages", "54_今日决策面板.py")


def _fragment_tree():
    src = open(PAGE, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "fragment_p1_ev":
            return node
    raise AssertionError("fragment_p1_ev 函数不存在（页面结构变更需同步守卫）")


def _calls_in(nodes, func_name):
    """在节点（或节点列表）中找 func_name 调用。"""
    out = []
    for node in nodes:
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == func_name:
                out.append(n)
    return out


def _names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _walk_nodes(stmts):
    """ast.walk 的列表版：逐语句展开。"""
    for stmt in stmts:
        yield from ast.walk(stmt)


def _find_if_q(fragment):
    """定位 `if _q:` 的外层 If（test 为 Name '_q'）。"""
    for n in ast.walk(fragment):
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "_q":
            return n
    raise AssertionError("找不到 `if _q:` 查询分支（页面结构变更需同步守卫）")


def test_empty_input_branch_never_references_ef():
    """空输入分支不得引用 ef（线上 UnboundLocalError 根因，防回潮）。"""
    if_q = _find_if_q(_fragment_tree())
    for call in _calls_in(list(_walk_nodes(if_q.orelse)), "xc_info_banner"):
        assert "ef" not in _names_in(call), \
            "空输入分支的提示引用了 ef（未绑定 → UnboundLocalError 回潮）"


def test_empty_input_branch_has_guidance():
    if_q = _find_if_q(_fragment_tree())
    src_seg = ast.unparse(if_q.orelse) if if_q.orelse else ""
    assert "输入代码" in src_seg, "空输入分支必须给出「输入代码」引导文案"


def test_unavailable_banner_inside_available_check():
    """「无事件因子信号」提示必须在 `if ef.get("available")` 的 orelse 内
    （修复前该提示从未显示过——else 错挂在 if _q 上）。"""
    if_q = _find_if_q(_fragment_tree())
    inner = None
    for n in if_q.body:
        for sub in ast.walk(n):
            if isinstance(sub, ast.If) and isinstance(sub.test, ast.Call) \
                    and isinstance(sub.test.func, ast.Attribute) \
                    and sub.test.func.attr == "get":
                inner = sub
    assert inner is not None, "找不到 `if ef.get(...)` 成功/无结果分支"
    seg = ast.unparse(inner.orelse) if inner.orelse else ""
    assert "无事件因子信号" in seg, "无结果提示必须位于 available 检查的 else 内"


def test_banner_never_references_ef_outside_query_scope():
    """全函数级兜底：xc_info_banner 引用 ef 的调用只能出现在 `if _q` 体内。"""
    fragment = _fragment_tree()
    if_q = _find_if_q(fragment)
    in_body_ids = set()
    for n in if_q.body:
        for sub in ast.walk(n):
            in_body_ids.add(id(sub))
    for call in _calls_in([fragment], "xc_info_banner"):
        if "ef" in _names_in(call):
            assert id(call) in in_body_ids, \
                "发现 if _q 作用域之外引用 ef 的提示调用（回潮）"
