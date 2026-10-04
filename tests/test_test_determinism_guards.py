# -*- coding: utf-8 -*-
"""tests/test_test_determinism_guards.py — 测试确定性守卫（T-207）。

防止两类已实证的「测试非确定性」复发（均造成「孤立跑绿、全量/隔日转红」的幽灵红）：

A. 时间炸弹：对「内部以 datetime.now()/date.today() 比较传入日期之滞后或窗口」的
   产品 API，测试若在**参与比较的那个实参**里传硬编码绝对日期（YYYY-MM-DD）且未显式
   注入时间锚（today=/as_of=/temp_as_of=/now=），用例会随真实时钟漂移由绿转恒红。
   T-202 实证：dual_factor_wiring 在 indicators 硬编码 2026-09-30 触发新鲜度封顶 60%、
   stock_risk 假解禁日 2026-10-01 掉出 90 日窗口。
   → 修正：用时钟相对日期（date.today() / _iso(days_ago)）或显式注入时间锚。

B. 进程随机 hash：测试夹具用 `hash(...)` 造数据，受 PYTHONHASHSEED 每进程随机化影响
   → 数据随进程变化 → 间歇红。T-204 实证：daily_picker 5 次全量复现 1 次（现改 crc32）。
   → 修正：改确定性种子（zlib.crc32 / sum(map(ord, ...)) 等）。

TIME_SENSITIVE_ARGSPEC 按函数精确指定「哪个实参参与 now() 比较」，避免误伤同类函数中
不参与比较的日期参数（如 build_snapshot 的快照 date 仅用于输出，新鲜度看 indicators["date"]）。
新增此类 API 请登记。
"""
from __future__ import annotations

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 函数名 → (参与 now() 比较的「位置实参索引」列表, 「关键字实参名」列表)
# 仅检查这些实参内的日期字面量；其余参数（如快照 date）不参与时间比较，不误伤。
TIME_SENSITIVE_ARGSPEC: dict[str, tuple[list[int], list[str]]] = {
    "assess_freshness": ([0], ["sources"]),      # sources 各值的日期 vs now
    "unlock_risk": ([0], ["queue"]),             # queue 各解禁日 vs now 的 90 日窗口
    "reduction_risk": ([0], ["rows"]),           # rows 各减持日 vs now 的窗口
    "_age_days": ([0], ["date"]),                # date vs now
    "build_snapshot": ([1], ["indicators"]),     # 仅 indicators["date"] 参与新鲜度
}
# 显式时间锚：调用方主动注入「当前时间」，则绝对日期只为构造历史数据，无害
TIME_ANCHOR_KW = {"today", "as_of", "temp_as_of", "now"}
_DATE_RE = re.compile(r"^20\d\d-\d\d-\d\d$")


def _test_files() -> list[str]:
    out: list[str] = []
    for base in ("tests", os.path.join("backend", "tests")):
        d = os.path.join(ROOT, base)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith("test_") and name.endswith(".py"):
                out.append(os.path.join(d, name))
    return out


def _parse(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError):
        return None


def _dates_in(node) -> list[str]:
    return [x.value for x in ast.walk(node)
            if isinstance(x, ast.Constant) and isinstance(x.value, str)
            and _DATE_RE.match(x.value)]


def _call_name(node: ast.Call):
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def test_no_hardcoded_dates_to_time_sensitive_args():
    """A：时间敏感实参不得是未锚定的硬编码绝对日期（时间炸弹，T-202）。"""
    violations: list[str] = []
    for path in _test_files():
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name not in TIME_SENSITIVE_ARGSPEC:
                continue
            if {k.arg for k in node.keywords} & TIME_ANCHOR_KW:
                continue
            pos_idx, kw_names = TIME_SENSITIVE_ARGSPEC[name]
            checked: list[ast.AST] = [a for i, a in enumerate(node.args) if i in pos_idx]
            checked += [k.value for k in node.keywords if k.arg in kw_names]
            ds: list[str] = []
            for a in checked:
                ds += _dates_in(a)
            if ds:
                violations.append(
                    f"{os.path.relpath(path, ROOT)}:{node.lineno} {name} 的时间敏感实参 "
                    f"收到硬编码日期 {ds[:3]}")
    assert not violations, (
        "时间敏感实参收到未锚定的硬编码绝对日期（会随真实时钟漂移成恒红，T-202）。"
        "请改用时钟相对日期（date.today()/_iso(days)）或注入 today=/as_of=/temp_as_of=：\n  "
        + "\n  ".join(violations))


def test_no_process_random_hash_in_test_fixtures():
    """B：测试不得使用 hash() 造数据（PYTHONHASHSEED 每进程随机 → 间歇红，T-204）。"""
    violations: list[str] = []
    for path in _test_files():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == "hash":
                violations.append(f"{os.path.relpath(path, ROOT)}:{node.lineno}")
    assert not violations, (
        "测试使用 hash()（进程随机化 → 间歇红，T-204）。请改确定性种子（zlib.crc32 等）：\n  "
        + "\n  ".join(violations))
