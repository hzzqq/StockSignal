# -*- coding: utf-8 -*-
"""tests/test_fetcher_core_no_circular_import.py

T-247 红线守卫：fetcher_core 包**绝不 import modules.fetcher**（避免循环依赖）。

诚实语义：本包是 fetcher.py 的纯函数下沉层。若反向 import 既破「分层下沉」架构，
又会在 import 时触发 circular import 炸链。AST 锁死模块内任意 import 语句不得引用
modules.fetcher（无论顶层还是惰性，红线是绝对的）。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "modules" / "fetcher_core" / "__init__.py"


def test_fetcher_core_never_imports_fetcher():
    """模块内任意 import / from-import 均不得引用 modules.fetcher（循环依赖红线）。"""
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "modules.fetcher" or alias.name.startswith("modules.fetcher."):
                    offenders.append(f"L{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "modules.fetcher" or mod.startswith("modules.fetcher."):
                names = ", ".join(a.name for a in node.names)
                offenders.append(f"L{node.lineno}: from {mod} import {names}")
    assert not offenders, \
        "fetcher_core 违反了『绝不 import modules.fetcher』红线:\n  " + "\n  ".join(offenders)


def test_fetcher_core_module_docstring_states_red_line():
    """文档红线可见：模块 docstring 明确声明不 import modules.fetcher。"""
    src = CORE.read_text(encoding="utf-8")
    assert "绝不 import" in src and "modules.fetcher" in src, \
        "fetcher_core 模块 docstring 应保留『绝不 import modules.fetcher』红线声明"
