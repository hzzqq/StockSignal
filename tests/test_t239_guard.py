"""tests/test_t239_guard.py

T-239 第一轮守卫：静默吞异常治理的防回退护栏（ast-invariant-guard 范式）。

背景：modules/ 存量宽口径静默吞异常 278 处（2026-10-11 AST 扫描），治理按
「一轮一批、负向验证、AST 守卫锁死」推进。第一轮收口：
- R-H1 record_health_observation：观测落盘失败必须有日志留痕（否则 detect_stall
  因无观测历史失明——健康观测器自己失明）
- 定性为「设计正确的合理容错」并登记豁免（扫描器误报样本）：
  atomic_io（清理后重抛非吞）、fetcher.clear_cache（warning 留痕）、
  chief_agent（state.add_error 留痕）
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULES = REPO / "modules"


def _handler_has_log(handler) -> bool:
    """handler body（含嵌套 if）里是否出现 logger*/print 调用或 raise（留痕=任何形式）。"""
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", "") or ""
            if "log" in name.lower():
                return True
            base = getattr(fn, "value", None)
            if base is not None and "log" in ast.dump(base).lower():
                return True
    return False


def _silent_handlers(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for h in node.handlers:
            body_calls = [n for n in ast.walk(h) if isinstance(n, ast.Call)]
            if len(body_calls) == 0 and not _handler_has_log(h):
                # handler 无任何调用：pass/continue/纯赋值——静默
                out.append(h.lineno)
    return out


def test_r_h1_health_observation_failure_must_log():
    """R-H1：健康观测落盘失败必须留痕（mutation 目标：删 logger 行 → 本测试红）。"""
    path = MODULES / "data_health.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name == "record_health_observation":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Try):
                    for h in sub.handlers:
                        assert _handler_has_log(h), (
                            f"data_health.py:{h.lineno} record_health_observation 的 except 分支"
                            "静默无留痕——观测写失败连续发生会让 detect_stall 失明（T-239 R-H1 回退）"
                        )
            return
    raise AssertionError("未找到 record_health_observation 函数")


def test_exemption_list_still_friendly():
    """豁免样本回归核验：这些「静默」是设计正确的合理容错（重抛/清理辅助），不得误改。"""
    atomic = MODULES / "atomic_io.py"
    src = atomic.read_text(encoding="utf-8")
    # atomic_* 主路径失败必须重抛（清理后 raise），不得改成吞掉
    assert src.count("raise") >= 3, "atomic_io 的失败重抛语义被破坏"
    assert "_safe_remove(tmp)" in src, "tmp 清理被移除"


def test_no_new_silent_handlers_in_data_health():
    """data_health.py 静默 except 冻结基线：第一轮存量 8 处（L48/59/69/97/121/131/144/432，
    多为 SQLite 观测/日期探测的容错），治理只减不增——总数超过 8 即视为新增回退。"""
    silent = _silent_handlers(MODULES / "data_health.py")
    assert len(silent) <= 8, (
        f"data_health.py 静默 except 数量 {len(silent)} 超过第一轮基线 8（T-239 渐进治理回退）；"
        f"行号 {silent}——新增处必须补日志留痕或 raise"
    )
    # R-H1 修复的那一处必须保持留痕（数量减少不影响本断言）
