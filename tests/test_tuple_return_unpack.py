# -*- coding: utf-8 -*-
"""
tests/test_tuple_return_unpack.py — 「(x, meta) 二元组返回函数必须解包」全仓契约守卫

背景（见 test_daily_snapshot_wiring.py 的事故复盘）：
    modules/shepherd.get_shepherd_indicators() 返回 **(df, meta) 二元组**，曾因调用方
    写成 `df = get_shepherd_indicators(...)` 单赋值 → df 实际是元组 → 元组无 .empty
    → getattr(df, "empty", True) 恒为 True → 100% 误判「指标为空」→ 决策闭环被静默掐死。

    该事故只锁了 get_shepherd_indicators 在 scripts/daily_snapshot.py + app.py 两处。
    本文件把契约**泛化到所有返回 (x, meta) 的函数**，覆盖全仓生产代码，防止同类
    footgun 在任何新函数/新调用点复发：

        - shepherd.get_shepherd_indicators            （决策闭环入口，最致命）
        - shepherd.get_shepherd_indicators_range
        - shepherd.get_shepherd_today
        - market_drivers.get_market_drivers
        - market_cache.get                            （限定 market_cache.get，避开 dict.get）
        - market_cache.load_drivers_from_cache
        - pages/50_市场情绪._load_shepherd            （透传元组的 wrapper）
        - pages/50_市场情绪._load_shepherd_range

守卫规则：任意一个上述函数出现在 `x = func(...)` 单赋值 RHS 上即失败；
          允许 `df, meta = func(...)` 解包 / `x = func(...)[0]` 下标 / `return func(...)` 透传。

运行：pytest tests/test_tuple_return_unpack.py -q（纯离线，不联网）
"""

from __future__ import annotations

import ast
import os

# (模块路径, 函数名, 匹配方式)
# 匹配方式:
#   "any"      —— 函数名全局唯一，attr 或裸名调用都算（避开 dict.get 这类靠限定名区分）
#   ("attr", "market_cache") —— 必须是 market_cache.get（排除 dict.get/client.get/...）
_TARGETS = [
    ("modules/shepherd.py", "get_shepherd_indicators", "any"),
    ("modules/shepherd.py", "get_shepherd_indicators_range", "any"),
    ("modules/shepherd.py", "get_shepherd_today", "any"),
    ("modules/market_drivers.py", "get_market_drivers", "any"),
    ("modules/market_cache.py", "get", ("attr", "market_cache")),
    ("modules/market_cache.py", "load_drivers_from_cache", "any"),
    ("pages/50_市场情绪.py", "_load_shepherd", "any"),
    ("pages/50_市场情绪.py", "_load_shepherd_range", "any"),
]

# 生产代码扫描范围（排除 tests/，以免与 test_daily_snapshot_wiring 的故意复现冲突）
_SCAN_DIRS = ["modules", "pages", "scripts"]
_SCAN_FILES = ["app.py"]


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iter_prod_files():
    root = _project_root()
    out = []
    for d in _SCAN_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for cur, _, fs in os.walk(base):
            if ".git" in cur:
                continue
            for fn in fs:
                if fn.endswith(".py"):
                    out.append(os.path.join(cur, fn))
    for f in _SCAN_FILES:
        p = os.path.join(root, f)
        if os.path.isfile(p):
            out.append(p)
    return out


def _is_target_call(node: ast.Call, func_name: str, mode) -> bool:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        if fn.attr != func_name:
            return False
        if mode == "any":
            return True
        # mode == ("attr", alias)
        _, alias = mode
        v = fn.value
        if isinstance(v, ast.Name) and v.id == alias:
            return True
        if isinstance(v, ast.Attribute) and v.attr == alias:
            return True
        return False
    if isinstance(fn, ast.Name):
        if fn.id != func_name:
            return False
        # 裸名调用：仅对 "any" 模式接受（同模块内 import 后裸名调用）
        return mode == "any"
    return False


def test_all_tuple_returning_callers_unpack():
    """所有 (x, meta) 返回函数的生产调用点必须解包，禁止单赋值。"""
    violations = []
    for path in _iter_prod_files():
        try:
            src = open(path, "r", encoding="utf-8").read()
            tree = ast.parse(src, path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, _project_root())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Call)):
                continue
            for _, func_name, mode in _TARGETS:
                if _is_target_call(node.value, func_name, mode):
                    violations.append(
                        f"{rel}:{node.lineno}  `{node.targets[0].id} = {func_name}(...)` "
                        f"未解包：该函数返回 (df, meta)，必须写成 `df, meta = ...`"
                    )
                    break
    assert not violations, (
        "发现 (x, meta) 返回函数被单赋值（静默 footgun，同 get_shepherd_indicators 事故）：\n"
        + "\n".join(violations)
    )
