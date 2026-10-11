"""Tier1.1 fetcher.py 安全拆分 pilot 守卫。

锁定范式：纯函数迁入 modules.fetcher_core，fetcher.py 仅 re-export：
- fetcher_core 包定义 _safe_json_loads 且行为等价；
- fetcher._safe_json_loads 与 fetcher_core._safe_json_loads 是同一对象（零行为变化）；
- fetcher.py 不得再本地定义 _safe_json_loads（防拆分回潮/重复）；
- fetcher.py 必须含 `from modules.fetcher_core import _safe_json_loads`。
"""
import ast
import pathlib

import modules.fetcher as fetcher
from modules import fetcher_core

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_fetcher_core_defines_and_behaves():
    assert hasattr(fetcher_core, "_safe_json_loads")
    assert fetcher_core._safe_json_loads('{"a":1}') == {"a": 1}
    assert fetcher_core._safe_json_loads('[1,2,3]') == [1, 2, 3]
    assert fetcher_core._safe_json_loads('{bad') is None
    assert fetcher_core._safe_json_loads(None, default=[]) == []
    assert fetcher_core._safe_json_loads(123) is None


def test_fetcher_reexport_identity():
    # 同一对象 → 内部 509/519/547/1174 行调用行为完全不变
    assert fetcher._safe_json_loads is fetcher_core._safe_json_loads
    assert fetcher._safe_json_loads('{"a":1}') == {"a": 1}
    assert fetcher._safe_json_loads('{bad') is None


def test_fetcher_no_local_def_of_safe_json_loads():
    tree = ast.parse((ROOT / "modules/fetcher.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_safe_json_loads":
            raise AssertionError("fetcher.py 仍本地定义 _safe_json_loads，应迁入 fetcher_core")


def test_fetcher_core_package_and_reexport_present():
    init = ROOT / "modules/fetcher_core/__init__.py"
    assert init.exists(), "fetcher_core 包需有 __init__.py"
    src = init.read_text(encoding="utf-8")
    assert "def _safe_json_loads" in src
    fsrc = (ROOT / "modules/fetcher.py").read_text(encoding="utf-8")
    assert "from modules.fetcher_core import _safe_json_loads" in fsrc
