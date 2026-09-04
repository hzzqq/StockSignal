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

# 直接消费 get_shepherd_indicators 的调用点。
# 历史事故发生在 scripts/daily_snapshot.py 与 app.py；页面侧此前「假定」经 _load_shepherd 包装后已正确解包，
# 但未纳入扫描——若将来有人在页面直接 `df = get_shepherd_indicators(...)` 漏解包，护栏会漏检。
# 故把 pages/ 下全部页面也纳入 AST 扫描（return 语句非 Assign，不会误判包装层）。
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
def test_callers_unpack_the_tuple():
    """所有直接消费点必须解包：写成 `df, meta = get_shepherd_indicators(...)`。

    漏解包不会报错、只会静默降级，靠肉眼看不出来，故用 AST 在测试期拦住。
    """
    root = _project_root()
    for path in _guarded_files():
        rel = os.path.relpath(path, root)
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            fn = node.value.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "get_shepherd_indicators":
                continue
            target = node.targets[0]
            assert isinstance(target, ast.Tuple), (
                f"{rel}:{node.lineno} 未解包：get_shepherd_indicators 返回 (df, meta)，"
                f"必须写成 `df, meta = ...`；否则 df 是元组、getattr(df,'empty',True) 恒为真"
            )
            assert len(target.elts) >= 2, f"{rel}:{node.lineno} 解包元素不足 2 个"
