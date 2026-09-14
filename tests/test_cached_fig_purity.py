"""cached_fig 纯函数性守卫（防回退）。

背景（真实缺陷，2026-09-14 修复）：
  `modules/chart_cache.cached_fig` 底层是 `st.cache_data`，**缓存键由入参决定**。
  若被装饰函数体内引用了模块级全局变量 `dark`（如 `template="plotly_dark" if dark else ...`），
  而 `dark` 不是其参数，则缓存键不含主题 → **用户切换主题后仍返回旧配色的图**
  （暗色 figure 留在亮色主题下），属「不崩溃但语义错」的静默失败家族。

修复方式：把 `dark` 提升为显式参数（`def f(..., dark: bool = False)`），
使缓存键包含主题；调用方传入页面级 `dark`。

本守卫用 AST 静态扫描，确保此后不再出现「cached_fig 装饰 + 引用非参数 dark」。
"""
import ast
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(ROOT, "pages")


def _cached_fig_violations(pages_dir=PAGES_DIR):
    """返回 [(文件名, 函数名, 行号)]：被 cached_fig 装饰且引用了非参数 dark 的函数。"""
    out = []
    if not os.path.isdir(pages_dir):
        return out
    for fname in sorted(os.listdir(pages_dir)):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(pages_dir, fname)
        src = io.open(path, encoding="utf-8", errors="ignore").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not any("cached_fig" in ast.unparse(d) for d in node.decorator_list):
                continue
            params = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
            uses_dark = any(
                isinstance(s, ast.Name) and s.id == "dark" and isinstance(s.ctx, ast.Load)
                for s in ast.walk(node)
            )
            if uses_dark and "dark" not in params:
                out.append((fname, node.name, node.lineno))
    return out


def _count_cached_fig_builders(pages_dir=PAGES_DIR):
    """统计被 cached_fig 装饰的函数总数（用于防空转断言）。"""
    n = 0
    for fname in sorted(os.listdir(pages_dir)):
        if not fname.endswith(".py"):
            continue
        src = io.open(os.path.join(pages_dir, fname), encoding="utf-8", errors="ignore").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and any(
                "cached_fig" in ast.unparse(d) for d in node.decorator_list
            ):
                n += 1
    return n


def test_no_cached_fig_uses_global_dark():
    """被 cached_fig 装饰的函数不得引用非参数 dark（否则主题切换后缓存返回错配色）。"""
    viol = _cached_fig_violations()
    assert not viol, (
        "cached_fig 装饰的函数引用了全局 dark，缓存键不含主题会导致切主题后返回旧配色: "
        + "; ".join(f"{f}:{name}@{ln}" for f, name, ln in viol)
    )


def test_scan_is_not_vacuous():
    """防空转：扫描必须真的覆盖到足够多的 cached_fig builder。

    若 PAGES_DIR 路径写错或解析全失败，上一条断言会「零违规」恒真而失去意义。
    """
    n = _count_cached_fig_builders()
    assert n >= 5, f"应至少扫描到 5 个 cached_fig builder，实际 {n}（扫描可能失效）"
