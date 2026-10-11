"""T-239 守卫：连板晋级率信号合并失败不得静默吞（与 T-205 同族，R2/R7 数据静默丢失）。

背景：pages/50_市场情绪.py 在把「连板晋级率」(`_sl.current_promo_as_indicators()`)
并入当日情绪指标时，原代码用 `except Exception: pass` 把失败静默吞掉——晋级率维度
失败会**无任何日志地消失**，属 T-205 已修的「数据失败静默丢」同族缺陷。

本守卫用 AST 定点打击：凡是 try 体内含 `current_promo_as_indicators()` 调用，
其任一 except 分支若纯 `pass`（或只有 docstring）即判红。修复口径：至少 `logger.warning`
留痕（控制流不变，仍继续不含晋级率维度）。

负向验证：把修复改回 `except Exception: pass` 跑本测试应变红，还原后复绿。
"""
from __future__ import annotations

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "pages", "50_市场情绪.py")


def _call_is_promo_merge(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "current_promo_as_indicators"
    )


def _is_silent(body) -> bool:
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring
        return False
    return True


def test_promo_signal_merge_not_silently_swallowed():
    tree = ast.parse(open(TARGET, encoding="utf-8").read())
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_call_is_promo_merge(n) for n in ast.walk(node)):
            continue
        if any(_is_silent(h.body) for h in node.handlers):
            bad.append(node.lineno)
    assert not bad, (
        "50_市场情绪.py 连板晋级率信号合并被静默吞掉（行 "
        f"{bad}），数据失败将无人知晓——至少 logger.warning 留痕（T-239 口径）"
    )
