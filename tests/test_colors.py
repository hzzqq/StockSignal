"""R10：配色常量单一来源契约测试。

锁定 R8 的「modules/colors.py 为唯一配色来源」不变量：
1. colors.py 必须导出全部约定常量；
2. 消费方（visualizer / starfield_theme / analysis_engine / stock_analysis_helpers）
   必须从 modules.colors 导入，禁止在本地重复定义同义常量（值漂移防护）；
3. 跨模块使用的 UP_COLOR/DOWN_COLOR/RED/GREEN/AMBER 值必须一致。
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module_ast(rel_path):
    path = os.path.join(ROOT, rel_path)
    with open(path, "r", encoding="utf-8") as f:
        return ast.parse(f.read()), path


def _local_assign_values(tree, names):
    """收集模块顶层 `NAME = "..."` 的字面量值（用于检测本地重复定义）。"""
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id in names:
                if isinstance(node.value, ast.Constant):
                    found[tgt.id] = node.value.value
    return found


def test_colors_exports_all_constants():
    from modules.colors import (
        RED, GREEN, AMBER, UP_COLOR, DOWN_COLOR, HOLD_COLOR,
    )
    assert RED == "#009e60"
    assert GREEN == "#dc2626"
    assert AMBER == "#d97706"
    assert UP_COLOR == "#ff4d4f"
    assert DOWN_COLOR == "#00d486"
    assert HOLD_COLOR == "#ffa502"


def test_colors_is_zero_dependency():
    """colors.py 不应 import 任何业务/UI 模块，保证可被前后端安全复用。"""
    tree, _ = _load_module_ast("modules/colors.py")
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imported.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    # 允许标准库；禁止业务/UI 依赖
    forbidden = {"streamlit", "plotly", "modules", "backend", "pages"}
    assert not (imported & forbidden), f"colors.py 不应依赖: {imported & forbidden}"


def test_visualizer_imports_from_colors_not_local():
    from modules.visualizer import UP_COLOR, DOWN_COLOR
    from modules.colors import UP_COLOR as C_UP, DOWN_COLOR as C_DOWN
    assert UP_COLOR is C_UP and DOWN_COLOR is C_DOWN
    # 局部不得重复定义同值常量
    tree, _ = _load_module_ast("modules/visualizer.py")
    locals_ = _local_assign_values(tree, {"UP_COLOR", "DOWN_COLOR", "HOLD_COLOR"})
    assert not locals_, f"visualizer.py 不应本地定义配色常量: {locals_}"


def test_starfield_theme_imports_from_colors_not_local():
    from modules.starfield_theme import UP_COLOR, DOWN_COLOR
    from modules.colors import UP_COLOR as C_UP, DOWN_COLOR as C_DOWN
    assert UP_COLOR is C_UP and DOWN_COLOR is C_DOWN
    tree, _ = _load_module_ast("modules/starfield_theme.py")
    locals_ = _local_assign_values(tree, {"UP_COLOR", "DOWN_COLOR", "HOLD_COLOR"})
    assert not locals_, f"starfield_theme.py 不应本地定义配色常量: {locals_}"


def test_analysis_engine_imports_red_green_amber():
    from modules.analysis_engine import RED, GREEN, AMBER
    from modules.colors import RED as C_R, GREEN as C_G, AMBER as C_A
    assert (RED, GREEN, AMBER) == (C_R, C_G, C_A)
    tree, _ = _load_module_ast("modules/analysis_engine.py")
    locals_ = _local_assign_values(tree, {"RED", "GREEN", "AMBER"})
    assert not locals_, f"analysis_engine.py 不应本地定义配色常量: {locals_}"


def test_stock_analysis_helpers_imports_red_green_amber():
    from modules.stock_analysis_helpers import RED, GREEN, AMBER
    from modules.colors import RED as C_R, GREEN as C_G, AMBER as C_A
    assert (RED, GREEN, AMBER) == (C_R, C_G, C_A)
    tree, _ = _load_module_ast("modules/stock_analysis_helpers.py")
    locals_ = _local_assign_values(tree, {"RED", "GREEN", "AMBER"})
    assert not locals_, f"stock_analysis_helpers.py 不应本地定义配色常量: {locals_}"


@pytest.mark.parametrize("name", ["RED", "GREEN", "AMBER", "UP_COLOR", "DOWN_COLOR", "HOLD_COLOR"])
def test_no_other_module_redefines_colors(name):
    """全项目扫描：除 colors.py 外，任何 .py 都不得顶层定义这些常量名。"""
    offenders = []
    for dirpath, _, files in os.walk(ROOT):
        if ".git" in dirpath or ".workbuddy" in dirpath or "__pycache__" in dirpath:
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
            if rel == "modules/colors.py":
                continue
            try:
                tree, _ = _load_module_ast(rel)
            except SyntaxError:
                continue
            locals_ = _local_assign_values(tree, {name})
            if locals_:
                offenders.append(rel)
    assert not offenders, f"模块 {offenders} 重复定义了 {name}（应统一从 modules.colors 导入）"
