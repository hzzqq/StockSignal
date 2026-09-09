# -*- coding: utf-8 -*-
"""
tests/test_daily_snapshot_wiring.py — 「牧羊人 (df, meta) 二元组解包」契约守卫

为什么必须有这个文件（这是一次真事故的事后加固）：
    modules/shepherd.get_shepherd_indicators() 返回的是 **(df, meta) 二元组**，
    但 scripts/daily_snapshot.py 与 app.py 曾写成：
        df = get_shepherd_indicators(days=60)
        if df is None or getattr(df, "empty", True): ...
    元组**没有 .empty 属性** → getattr 的默认值 True 恒定生效 → 100% 误判
    「牧羊人指标为空」→ 每日快照 return 1 永不落盘 → record_prediction 永不触发
    → 「预测 vs 实际回测」与「仓位刻度校准」的样本永远是 0，整条决策闭环被掐死在源头；
    app.py 那处更隐蔽：异常被 except 吞掉，首页温度/周期/方向永远显示兜底值。

    牧羊人数据本身一直是健康的（实测 60 行 × 19 列、unavailable 为空），
    纯粹是调用方漏解包造成的假警报。本文件用三重手段锁死该契约：
        1. 契约：函数确实返回 (df, meta)；
        2. 失败模式留档：元组无 .empty，守卫默认值必为 True（说明为何静默）；
        3. 静态 AST 守卫：所有直接消费点必须解包成二元组（防回归）。

运行：pytest tests/test_daily_snapshot_wiring.py -q（纯离线，不联网）
"""

from __future__ import annotations

import ast
import os

import pandas as pd

from modules import shepherd as _sh

# 直接消费 (df, meta) 二元组取数入口的所有调用点。
# 历史事故发生在 scripts/daily_snapshot.py 与 app.py；现已把 app.py + scripts/daily_snapshot.py
# + pages/ 下全部页面都纳入 AST 扫描（return 语句非 Assign，不会误判 _load_shepherd 这类包装层）。
# 守卫同时覆盖姊妹函数 get_shepherd_indicators_range（同为 (df, meta) 元组，同样会静默 footgun）。
def _guarded_files():
    root = _project_root()
    files = [
        os.path.join("scripts", "daily_snapshot.py"),
        "app.py",
    ]
    pages_dir = os.path.join(root, "pages")
    if os.path.isdir(pages_dir):
        for name in sorted(os.listdir(pages_dir)):
            if name.endswith(".py"):
                files.append(os.path.join("pages", name))
    return [os.path.join(root, f) for f in files]


def _project_root() -> str:
    """项目根（tests/ 的上一级）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fake_history(monkeypatch, n_keys: int = 3):
    """把取数换成离线假数据，避免单测触网。"""
    keys = list(_sh.THRESHOLDS)[:n_keys]
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-28", "2026-08-31"]),
        **{k: [1.0, 2.0] for k in keys},
    })
    monkeypatch.setattr(_sh, "get_shepherd_history", lambda days=None: df, raising=True)
    return df, keys


# ───────────────────────── 1. 契约 ─────────────────────────
def test_get_shepherd_indicators_returns_tuple(monkeypatch):
    """统一入口必须返回 (df, meta) 二元组，meta 含 available/unavailable。"""
    _, keys = _fake_history(monkeypatch)
    out = _sh.get_shepherd_indicators(days=60)
    assert isinstance(out, tuple) and len(out) == 2, "必须是 (df, meta) 二元组"
    df, meta = out
    assert isinstance(df, pd.DataFrame) and not df.empty
    assert {"available", "unavailable"} <= set(meta), "meta 缺失 available/unavailable"
    assert keys[0] in meta["available"], "存在的阈值列应出现在 available 里"


# ───────────────────────── 2. 失败模式留档 ─────────────────────────
def test_tuple_has_no_empty_attr_so_guard_defaults_true(monkeypatch):
    """元组无 .empty → getattr(x, 'empty', True) 恒为 True —— 这就是事故为何「静默」。"""
    _fake_history(monkeypatch)
    out = _sh.get_shepherd_indicators(days=60)  # 故意不解包，复现历史写法
    assert getattr(out, "empty", True) is True, "元组无 .empty，守卫默认值必为 True"


# ───────────────────────── 3. 静态 AST 守卫 ─────────────────────────
# 所有返回 (df, meta) 二元组的牧羊人取数入口，调用方都必须解包，否则静默降级。
_GUARDED_FUNCS = ("get_shepherd_indicators", "get_shepherd_indicators_range")


def _violations_in_source(src: str, func_names) -> list:
    """扫描源码：对任何 `x = <func>(...)` 单赋值（未解包成二元组）返回违规位置 (lineno, name)。

    - return 语句 / 多返回值包装层（如 `_load_shepherd` 直接 return 元组）不计入；
    - 仅 `Assign` 且目标是 `Call` 的节点才算「直接消费点」。
    """
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        fn = node.value.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name not in func_names:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Tuple) or len(target.elts) < 2:
            out.append((node.lineno, name))
    return out


def test_callers_unpack_the_tuple():
    """所有直接消费点必须解包：写成 `df, meta = get_shepherd_indicators(...)`。

    覆盖 app.py + scripts/daily_snapshot.py + pages/ 全部页面，以及返回 (df, meta) 的
    姊妹函数 get_shepherd_indicators_range。漏解包不会报错、只会静默降级，靠肉眼看不出来，
    故用 AST 在测试期拦住。
    """
    root = _project_root()
    for path in _guarded_files():
        rel = os.path.relpath(path, root)
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        violations = _violations_in_source(src, _GUARDED_FUNCS)
        assert not violations, (
            f"{rel} 存在未解包调用：{violations}。"
            f"这些函数返回 (df, meta)，必须写成 `df, meta = ...`；"
            f"否则 df 是元组、getattr(df,'empty',True) 恒为真，决策闭环被静默掐死。"
        )


def test_ast_guard_detects_single_assign_violation():
    """守卫必须能抓出 `df = get_shepherd_indicators(...)` 这类历史事故写法。"""
    bad = "def f():\n    df = get_shepherd_indicators(days=60)\n    return df\n"
    violations = _violations_in_source(bad, _GUARDED_FUNCS)
    assert violations, "守卫未能识别单赋值漏解包"
    assert violations[0][1] == "get_shepherd_indicators"


def test_ast_guard_detects_range_violation():
    """姊妹函数 get_shepherd_indicators_range 同样必须解包，守卫不能漏。"""
    bad = "def g():\n    df = get_shepherd_indicators_range(a, b)\n    return df\n"
    violations = _violations_in_source(bad, _GUARDED_FUNCS)
    assert violations and violations[0][1] == "get_shepherd_indicators_range"


def test_ast_guard_ignores_proper_unpack_and_return():
    """正确解包与 return 包装层不应误报。"""
    good = (
        "def h():\n"
        "    df, meta = get_shepherd_indicators(days=60)\n"
        "    return get_shepherd_indicators_range(s, e)\n"
        "    df, mm = get_shepherd_indicators_range(s, e)\n"
    )
    assert not _violations_in_source(good, _GUARDED_FUNCS)
