"""
tests/test_backend_imports.py
=============================
导入健康回归测试：逐个导入 modules/ 与 backend/ 下所有源文件，
确保没有 import 期错误（NameError / 缺失导入 / 语法错误 等）。

背景：2026-07 一次多账号合并把实盘/条件单模型带进 models.py，却漏了 datetime
导入，导致 `backend.models` 整体无法 import（NameError），后端一重启即崩，
却未被任何单测直接覆盖。本测试把「全量 import」固化为回归网，防止同类合并回归复发。

说明：pytest 运行时 PYTEST_CURRENT_TEST 已置位，backend 的调度器有守卫不会起线程，
因此可安全导入 backend.app。
"""
from __future__ import annotations

import glob
import importlib
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _discover(pattern: str, *, exclude_parts=()):
    mods = []
    for f in sorted(glob.glob(os.path.join(_ROOT, pattern), recursive=True)):
        rel = os.path.relpath(f, _ROOT).replace("\\", "/")
        if rel.endswith("__init__.py"):
            continue
        if any(part in rel for part in exclude_parts):
            continue
        mods.append(rel[:-3].replace("/", "."))
    return mods


_MODULES = _discover("modules/*.py")
_BACKEND = _discover(
    "backend/**/*.py",
    exclude_parts=("/tests/", "/scripts/", "backend/scripts/", "backend/tests/"),
)


@pytest.mark.parametrize("mod", _MODULES + _BACKEND)
def test_module_imports(mod):
    """每个源模块都必须能干净地 import，不抛异常。"""
    importlib.import_module(mod)


def test_discovery_nonempty():
    """守护：确保发现逻辑真的扫到了文件（避免 glob 失效导致空跑假绿）。"""
    assert len(_MODULES) >= 20, f"modules 发现过少: {len(_MODULES)}"
    assert len(_BACKEND) >= 20, f"backend 发现过少: {len(_BACKEND)}"
