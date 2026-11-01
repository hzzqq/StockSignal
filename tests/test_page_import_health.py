# -*- coding: utf-8 -*-
"""tests/test_page_import_health.py — 全页 module 级导入健康守卫。

背景（2026-11-01 事故）：R-09 把 to_numeric_clean 下沉 page_utils + 4 页改 import，
用户运行中的 Streamlit 进程在「页面已换新 import / page_utils 仍旧」的窗口里加载
50 页 → ImportError 截图上报。本守卫用 AST 静态抽取每页全部 ``from modules.*``
导入名，逐一校验真实存在——把「下沉漏提交 / 改名没同步 / 拼错名」在测试层钉死。

口径：
- 只做 module 级名字校验（importlib + hasattr），不渲染页面（全页冒烟已覆盖渲染）；
- ``from modules import X``（子模块导入）→ 校验 import_module("modules.X") 成功；
- ``from modules.X import n1, n2`` → 校验 hasattr(mod, n)；
- 已知误报排除：包对象在子模块未加载时无其属性（2026-11-01 实录 37 条假阳性根因）。
"""
import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "pages"


def _iter_page_imports(tree):
    """抽出页内全部 modules.* 的 ImportFrom 节点（含函数内惰性导入）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("modules"):
            yield node


def test_all_page_module_imports_resolve():
    """73 页全部 modules.* 导入名必须真实存在（含惰性导入点）。"""
    bad: list[str] = []
    _mod_cache: dict[str, object] = {}
    for p in sorted(PAGES_DIR.rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            bad.append(f"{p.name}: 语法错误 {e}")
            continue
        for node in _iter_page_imports(tree):
            if node.module == "modules":
                for a in node.names:
                    sub = f"modules.{a.name}"
                    try:
                        importlib.import_module(sub)
                    except Exception as e:  # noqa: BLE001
                        bad.append(f"{p.name}: {sub} 导入失败 {type(e).__name__}")
                continue
            if node.module not in _mod_cache:
                try:
                    _mod_cache[node.module] = importlib.import_module(node.module)
                except Exception as e:  # noqa: BLE001
                    _mod_cache[node.module] = None
                    bad.append(f"{p.name}: import {node.module} 失败 {type(e).__name__}: {str(e)[:80]}")
                    continue
            mod = _mod_cache[node.module]
            if mod is None:
                continue
            for a in node.names:
                if a.name != "*" and not hasattr(mod, a.name):
                    bad.append(f"{p.name}: {node.module}.{a.name} 不存在")
    assert not bad, f"页面 modules 导入存在断点（下沉/改名未同步？）:\n" + "\n".join(f" - {b}" for b in bad)


def test_guard_covers_to_numeric_clean_regression():
    """事故回归钉：page_utils.to_numeric_clean 必须存在（R-09 下沉的公共取数助手）。"""
    mod = importlib.import_module("modules.page_utils")
    assert hasattr(mod, "to_numeric_clean"), (
        "page_utils.to_numeric_clean 消失——R-09 收敛的公共取数助手被误删/改名，"
        "至少 4 页顶层 import 会当场 ImportError"
    )
