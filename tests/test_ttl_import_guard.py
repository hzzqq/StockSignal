# -*- coding: utf-8 -*-
"""R-14 复发守卫：源码引用 TTL_TIERS 的模块 import 后必须真有该名字。

背景（2026-11-01 事故）：`from modules.cache_utils import TTL_TIERS` 被写进
模块 docstring 内部——文本存在但从未执行，装饰器 `@st.cache_data(ttl=TTL_TIERS[...])`
在模块加载时求值即 NameError，页面炸（当时 11/20 页冒烟实锤）。
import 层面"看似健康"的守卫（test_page_import_health）抓不到这类雷，
必须用「导入后 hasattr」级别的运行时断言。

口径：
- 扫 modules/*.py 源码文本含 "TTL_TIERS" 的模块；
- 例外：cache_utils.py 是定义方，不 import 自己；
- 其余每个模块必须真实 import 成功且 hasattr(mod, "TTL_TIERS")。
"""
import ast
import importlib
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parents[1] / "modules"
EXEMPT = {"cache_utils"}  # TTL_TIERS 定义方


def _mentions_ttl(path: Path) -> bool:
    return "TTL_TIERS" in path.read_text(encoding="utf-8")


def _has_real_import(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(n, ast.ImportFrom)
        and n.module == "modules.cache_utils"
        and any(a.name == "TTL_TIERS" for a in n.names)
        for n in ast.walk(tree)
    )


def test_ttl_tiers_mentioning_modules_expose_name_at_runtime():
    targets = [
        p for p in sorted(MODULES_DIR.glob("*.py"))
        if p.stem not in EXEMPT and _mentions_ttl(p)
    ]
    assert targets, "扫描不到任何引用 TTL_TIERS 的模块，守卫口径可能失效"
    for p in targets:
        mod = importlib.import_module(f"modules.{p.stem}")
        assert hasattr(mod, "TTL_TIERS"), (
            f"modules/{p.name} 源码引用 TTL_TIERS 但 import 后没有该名字——"
            f"疑似 docstring 伪 import 复发（R-14 同款，装饰器求值时 NameError）"
        )


def test_ttl_tiers_mentioning_modules_have_real_ast_import():
    """静态层双保险：提及 TTL_TIERS 的模块（非定义方）AST 里必须有真 ImportFrom。

    与运行时断言互补：运行时抓「装饰器求值炸」的现行犯，
    静态抓「文本提及但未导入」的潜伏者（例如只在注释/字符串里引用的边缘形态）。
    """
    targets = [
        p for p in sorted(MODULES_DIR.glob("*.py"))
        if p.stem not in EXEMPT and _mentions_ttl(p)
    ]
    for p in targets:
        assert _has_real_import(p), (
            f"modules/{p.name} 文本提及 TTL_TIERS 但 AST 无真 import——"
            f"如需引用请补 from modules.cache_utils import TTL_TIERS，"
            f"如仅注释提及请改写措辞避免误伤本守卫"
        )
