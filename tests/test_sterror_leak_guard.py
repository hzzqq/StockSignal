# -*- coding: utf-8 -*-
"""守卫：pages/ 全站 st.error 禁止拼接原始异常变量（{e}/{exc}/{err} 等）——防内部细节泄露。
规范路径：xc_handle_error（异常只进 logger，用户只见友好错误卡）。
AST 扫描 + mutation 自验（构造违规样本必须被检出，防假绿）。"""
import ast
from pathlib import Path

import pytest

PAGES = Path(__file__).resolve().parent.parent / "pages"
RISKY_NAMES = {"e", "exc", "err", "ex", "ie", "error"}


def _find_leaks(src: str, filename: str = "<src>"):
    """返回 [(file, line, snippet)]：st.error 的 f-string 参数拼接了异常变量名"""
    out = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "error"):
            continue
        base = node.func.value
        if not ((isinstance(base, ast.Attribute) and base.attr == "st")
                or (isinstance(base, ast.Name) and base.id == "st")):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.JoinedStr):
            for v in arg.values:
                if isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name) \
                        and v.value.id in RISKY_NAMES:
                    out.append((filename, node.lineno,
                                ast.get_source_segment(src, node) or ""))
                    break
    return out


def test_no_leaky_st_error_in_pages():
    leaks = []
    for f in sorted(PAGES.glob("*.py")):
        leaks += _find_leaks(f.read_text(encoding="utf-8"), f.name)
    assert not leaks, \
        f"发现 {len(leaks)} 处泄露型 st.error（异常细节禁止直出用户，请改用 xc_handle_error）: " \
        + "; ".join(f"{fn}:L{ln}" for fn, ln, _ in leaks[:5])


def test_mutation_leak_guard_detects_injected_sample():
    """mutation 自验：注入违规样本必须被检出（防假绿）"""
    bad = 'st.error(f"页面渲染失败：{e}")'
    assert _find_leaks(f"import streamlit as st\n{bad}\n", "mut"), "违规样本未被检出——守卫假绿"
    # 合规形态不得误伤：xc_handle_error 与普通消息
    assert not _find_leaks("import streamlit as st\nst.error('请先选择股票')\n")
    assert not _find_leaks("import streamlit as st\nxc_handle_error('渲染失败', e)\n")


def _find_leaks_v2(src: str, filename: str = "<src>"):
    """扩展泄漏检测：f-string（已有）+ ``"...".format(exc)`` + ``"..." + str(exc)`` 拼接。"""
    out = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "error"):
            continue
        base = node.func.value
        if not ((isinstance(base, ast.Attribute) and base.attr == "st")
                or (isinstance(base, ast.Name) and base.id == "st")):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.JoinedStr):
            for v in arg.values:
                if isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name) \
                        and v.value.id in RISKY_NAMES:
                    out.append((filename, node.lineno, ast.get_source_segment(src, node) or ""))
                    break
            continue
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) \
                and arg.func.attr == "format":
            for a in arg.args:
                if (isinstance(a, ast.Name) and a.id in RISKY_NAMES) or \
                   (isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "str"
                    and a.args and isinstance(a.args[0], ast.Name) and a.args[0].id in RISKY_NAMES):
                    out.append((filename, node.lineno, ast.get_source_segment(src, node) or ""))
                    break
            continue
        if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
            parts, cur = [], arg
            while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Add):
                parts.append(cur.right)
                cur = cur.left
            parts.append(cur)
            for p in parts:
                if (isinstance(p, ast.Name) and p.id in RISKY_NAMES) or \
                   (isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "str"
                    and p.args and isinstance(p.args[0], ast.Name) and p.args[0].id in RISKY_NAMES):
                    out.append((filename, node.lineno, ast.get_source_segment(src, node) or ""))
                    break
    return out


def test_no_format_or_concat_leaky_st_error_in_pages():
    leaks = []
    for f in sorted(PAGES.glob("*.py")):
        leaks += _find_leaks_v2(f.read_text(encoding="utf-8"), f.name)
    assert not leaks, \
        f"发现 {len(leaks)} 处泄露型 st.error（.format/拼接异常变量，禁止异常细节直出用户）：" \
        + "; ".join(f"{fn}:L{ln}" for fn, ln, _ in leaks[:5])


def test_mutation_format_and_concat_guard_detects_samples():
    """mutation 自验：注入 .format/拼接样本必须被检出（防假绿）"""
    assert _find_leaks_v2("import streamlit as st\nst.error('fail: {}'.format(e))\n")
    assert _find_leaks_v2("import streamlit as st\nst.error('fail: ' + str(e))\n")
    # 合规形态不得误伤
    assert not _find_leaks_v2("import streamlit as st\nst.error('请先选择股票')\n")
    assert not _find_leaks_v2("import streamlit as st\nxc_handle_error('渲染失败', e)\n")
