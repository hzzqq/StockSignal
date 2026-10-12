"""
tests/test_cache_key_single_source.py
=====================================
T-272②：引擎取数参数单源化守卫——cache_warmer 预热与 recommend_engine 引擎
共同引用 engine_fetch_params，键一致性从「文档约定」升级为「机器保证」。

根除 T-250 踩坑类：cache_key 由参数拼接，预热参数与引擎不同＝写引擎读不到的键
＝预热白拉。本守卫钉死：
  1) 两侧运行时输出逐字节一致；
  2) cache_warmer 源码不再自带 timedelta(days=260) 复刻（回潮即红）；
  3) 引擎 _fetch_one 确实走单源函数（AST 断言）。
"""
import ast
from datetime import datetime, timedelta
from pathlib import Path

import modules.cache_warmer as warmer
import modules.recommend_engine as engine

_PROJECT = Path(__file__).resolve().parents[1]


def test_params_consistent_between_warmer_and_engine():
    """预热端与引擎端取数参数逐字节一致（同进程秒内调用）。"""
    p1 = warmer._engine_params()
    p2 = engine.engine_fetch_params()
    assert p1 == p2, f"预热参数 {p1} 与引擎参数 {p2} 不一致——键漂移将导致预热白拉"
    assert len(p1) == 3


def test_param_shape_and_window():
    """参数形态：start=260 天前、end=今天、adjust=qfq。"""
    start, end, adjust = engine.engine_fetch_params()
    today = datetime.now().strftime("%Y-%m-%d")
    expect_start = (datetime.now() - timedelta(days=260)).strftime("%Y-%m-%d")
    assert start == expect_start
    assert end == today
    assert adjust == "qfq"


def test_warmer_no_longer_replicates_window():
    """源码契约：cache_warmer 不得再自带 260 天窗口复刻（单源化回潮即红）。"""
    src = (_PROJECT / "modules" / "cache_warmer.py").read_text(encoding="utf-8")
    assert "timedelta(days=260)" not in src, \
        "cache_warmer 又开始复刻窗口参数（T-272② 单源化回潮）——请改回引用 engine_fetch_params"
    assert "engine_fetch_params" in src, "cache_warmer 应引用 engine_fetch_params 单源"


def test_engine_fetch_one_uses_single_source():
    """AST 契约：引擎 _fetch_one 函数体内调用 engine_fetch_params（不手拼参数）。"""
    src = (_PROJECT / "modules" / "recommend_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch_one":
            body = node
            break
    assert body is not None, "_fetch_one 函数不存在"
    calls = [n for n in ast.walk(body) if isinstance(n, ast.Call)]
    names = []
    for c in calls:
        f = c.func
        if isinstance(f, ast.Name):
            names.append(f.id)
        elif isinstance(f, ast.Attribute):
            names.append(f.attr)
    assert "engine_fetch_params" in names, \
        "_fetch_one 不再引用 engine_fetch_params（键单源化回潮）——参数漂移将致预热白拉"
    assert "strftime" not in names, \
        "_fetch_one 内又出现手拼日期 strftime（应改由 engine_fetch_params 单源提供）"
