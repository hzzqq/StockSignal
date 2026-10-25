# -*- coding: utf-8 -*-
"""T-324 ①牧羊人增量刷新管线退出行为守卫。

背景：全量拉取路径偶发「工作完成后进程驻留不退出」（T-323 实测两批挂起、
CPU 归零仍驻留；缓存命中/offline 路径不可复现，最小复现排除 bpo-39812）。
修复=双防线：头部 faulthandler.dump_traceback_later(900, exit=True) 兜底强退+留栈；
成功路径产出原子落盘校验后 os._exit(0) 绕过解释器退出阶段。

守卫：
- 行为：subprocess 实跑 --offline --dry-run 必须在时限内自行退出且 exit 0
  （挂起即 timeout 击杀 exit!=0 → 红）；
- 结构（AST）：faulthandler 兜底必须存在（exit=True、上限≥600s）；
  os._exit(0) 必须存在于 main 内、且位于最后一次 atomic_to_csv 之后
  （防「产出未落盘就强退」的假快）。

skipif 仅限环境不具备（v2 缓存缺失 = offline 模式无数据可聚合）。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, "scripts", "refresh_shepherd_history_recent.py")
_CACHE_V2 = os.path.join(_ROOT, "data", "shepherd_cache_v2")

import pytest  # noqa: E402


def test_refresh_offline_exits_promptly():
    """行为守卫：offline dry-run 必须自行退出（挂起进程会被 timeout 击杀而变红）。"""
    if not (os.path.isdir(_CACHE_V2) and os.listdir(_CACHE_V2)):
        pytest.skip("data/shepherd_cache_v2 缺失（环境不具备 offline 聚合前提）")
    r = subprocess.run(
        [sys.executable, "-m", "scripts.refresh_shepherd_history_recent",
         "--offline", "--dry-run"],
        cwd=_ROOT, timeout=150, capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    assert r.returncode == 0, (
        f"刷新进程未正常退出（exit={r.returncode}，timeout 前被击杀=挂起回退）：\n"
        f"stdout_tail={r.stdout[-500:]}\nstderr_tail={r.stderr[-500:]}")


def test_refresh_hang_guard_ast():
    """结构守卫：双防线必须在位，且 os._exit 必须在最后一次写盘之后。"""
    src = open(_SCRIPT, encoding="utf-8").read()
    tree = ast.parse(src)

    # 1) faulthandler 兜底：dump_traceback_later(>=600, exit=True)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    dumps = [n for n in calls
             if isinstance(n.func, ast.Attribute)
             and n.func.attr == "dump_traceback_later"]
    assert dumps, "缺少 faulthandler.dump_traceback_later 挂起兜底"
    ok = False
    for n in dumps:
        args = n.args
        limit = args[0].value if args and isinstance(args[0], ast.Constant) else None
        kw_exit = any(k.arg == "exit" and getattr(k.value, "value", None) is True
                      for k in n.keywords)
        if isinstance(limit, int) and limit >= 600 and kw_exit:
            ok = True
    assert ok, "faulthandler 兜底参数不合规（需上限>=600 且 exit=True）"

    # 2) os._exit(0) 在 main 内、位于最后一次 atomic_to_csv 调用之后
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    main = funcs["main"]
    exits = [n for n in ast.walk(main)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "os" and n.func.attr == "_exit"
             and getattr(n.args[0], "value", None) == 0] if main else []
    assert exits, "main 成功路径缺少 os._exit(0)（挂起防护回退）"
    writes = [n for n in ast.walk(main)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "atomic_to_csv"]
    assert writes, "main 内应有 atomic_to_csv 写盘"
    assert max(e.lineno for e in exits) > max(w.lineno for w in writes), \
        "os._exit(0) 必须位于最后一次 atomic_to_csv 之后（防产出未落盘即强退）"
