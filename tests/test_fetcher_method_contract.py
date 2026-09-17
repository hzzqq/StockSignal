# -*- coding: utf-8 -*-
"""tests/test_fetcher_method_contract.py — fetcher 方法调用契约守卫。

背景（本轮真实缺陷，2026-09-17）：
``pages/22_基本面分析.py::_industry_pe_median`` 调用了 ``fetcher.get_basic_info()``，
而 ``StockFetcher`` **根本没有这个方法**。异常被内层 ``except Exception`` 吞掉，
于是样本恒为空 →「同行业 PE 中位数」卡片**永远显示「暂不可用」**，
而且不报错、不告警，没有任何测试能发现——典型的「静默失败」。

这类缺陷的共性：**调用方与实现方的方法名不一致，且被宽泛 try/except 掩盖**。
静态检查是唯一能稳定拦住它的手段，因此本守卫用 AST 扫描所有页面/模块里
对本地 fetcher 对象的方法调用，逐一核对 ``StockFetcher`` 是否真有该方法。

守卫范围（精确优先，避免误伤）：
- 只检查被**显式绑定为 fetcher** 的标识符：``fetcher`` / ``_fetcher`` /
  ``self.fetcher``，且该文件里确实存在 ``X = StockFetcher()`` / ``X = get_fetcher()``
  之类的绑定语句（否则该名字可能是别的东西，跳过）。
- 只检查**函数调用**形态 ``X.method(...)``，不检查属性读取。
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SCAN_DIRS = ("pages", "modules")
_FETCHER_NAMES = {"fetcher", "_fetcher"}
_BIND_FUNCS = {"StockFetcher", "get_fetcher"}


def _fetcher_methods() -> set[str]:
    """StockFetcher 的真实方法名（含继承）。"""
    from modules.fetcher import StockFetcher
    return {n for n in dir(StockFetcher) if not n.startswith("__")}


def _iter_py():
    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in ("__pycache__",)]
            for fn in files:
                if fn.endswith(".py"):
                    yield os.path.join(dirpath, fn)


def _binds_fetcher(tree: ast.AST) -> bool:
    """该文件是否把某个名字绑定成了 fetcher 实例。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            val = node.value
            fname = None
            if isinstance(val, ast.Call):
                f = val.func
                fname = getattr(f, "id", None) or getattr(f, "attr", None)
            if fname in _BIND_FUNCS:
                for t in node.targets:
                    nm = getattr(t, "id", None) or getattr(t, "attr", None)
                    if nm in _FETCHER_NAMES:
                        return True
    return False


def _fetcher_calls(tree: ast.AST) -> list[tuple[str, int]]:
    """收集 ``<fetcher>.<method>(...)`` 形态的调用 → [(method, lineno), ...]。"""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not isinstance(f, ast.Attribute):
            continue
        base = f.value
        nm = getattr(base, "id", None) or getattr(base, "attr", None)
        if nm in _FETCHER_NAMES:
            out.append((f.attr, node.lineno))
    return out


def test_every_fetcher_call_exists_on_stockfetcher():
    """所有页面/模块里对 fetcher 的方法调用，必须真实存在于 StockFetcher。"""
    methods = _fetcher_methods()
    assert "get_fundamentals" in methods and "get_daily" in methods, "未取到 StockFetcher 方法表，守卫失效"
    bad: list[str] = []
    checked_files = 0
    checked_calls = 0
    for path in _iter_py():
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read())
        except SyntaxError:
            continue
        if not _binds_fetcher(tree):
            continue
        checked_files += 1
        calls = _fetcher_calls(tree)
        checked_calls += len(calls)
        for meth, ln in calls:
            if meth not in methods:
                rel = os.path.relpath(path, ROOT)
                bad.append(f"{rel}:{ln} → fetcher.{meth}()")
    assert checked_calls > 0, "未扫到任何 fetcher 调用，守卫失效"
    assert not bad, (
        "以下位置调用了 StockFetcher 上不存在的方法（会被宽泛 except 吞成静默失败）：\n  "
        + "\n  ".join(sorted(set(bad)))
        + f"\n（本次扫描 {checked_files} 个文件 / {checked_calls} 处调用）"
    )


def test_guard_would_have_caught_the_real_defect():
    """证非假绿：确认 ``get_basic_info`` 确实不在 StockFetcher 上。

    若哪天有人真的加了 ``get_basic_info``，本测试会失败并提醒复核上面那条守卫的必要性。
    """
    methods = _fetcher_methods()
    assert "get_basic_info" not in methods, (
        "StockFetcher 现在有了 get_basic_info —— 请复核 test_every_fetcher_call_exists_on_stockfetcher "
        "的守卫前提是否仍成立（2026-09-17 该方法是页面误调用并不存在的方法）"
    )
