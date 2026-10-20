# -*- coding: utf-8 -*-
"""守卫：30_策略回测.py 全部 st.metric 必须显式携带 delta_color（铁律 2：A 股红涨绿跌语义）。
AST 扫描（关键字级，非正则），防止增量回潮；配套 mutation 自验用例。"""
import ast
import re
from pathlib import Path

import pytest

PAGES = Path(__file__).resolve().parent.parent / "pages"
TARGET = PAGES / "30_策略回测.py"


def _metric_calls(tree: ast.AST):
    """yield 每个 st.metric(...) 调用节点（含 metric.xxx 变体过滤）"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "metric":
            base = f.value
            if isinstance(base, ast.Attribute) and base.attr == "st":
                yield node
            elif isinstance(base, ast.Name) and base.id == "st":
                yield node


def _has_delta_color(call: ast.Call) -> bool:
    return any(kw.arg == "delta_color" for kw in call.keywords)


def test_30_backtest_all_metrics_have_delta_color():
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    calls = list(_metric_calls(tree))
    assert calls, "未扫描到 st.metric 调用（文件结构变化需更新守卫）"
    bad = []
    for c in calls:
        if not _has_delta_color(c):
            bad.append(c.lineno)
    assert not bad, f"第 {bad} 行 st.metric 缺 delta_color（红涨绿跌铁律）"


def test_30_backtest_delta_values_are_a_share_semantics():
    """涨跌值必须 inverse（正红负绿），禁止 normal（美股绿涨语义）"""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    for c in _metric_calls(tree):
        for kw in c.keywords:
            if kw.arg == "delta_color" and isinstance(kw.value, ast.Constant):
                assert kw.value.value != "normal", \
                    f"第 {c.lineno} 行 delta_color='normal' 为美股语义，A 股须用 inverse/off"


def test_mutation_guard_catches_missing_delta_color(tmp_path):
    """mutation 自验：删掉一处 delta_color 后守卫逻辑必须报红（防假绿）"""
    src = TARGET.read_text(encoding="utf-8")
    mutated = src.replace('delta_color="inverse"', 'delta_color="off"', 1)
    assert mutated != src, "mutation 种子失效"
    # 模拟守卫核心逻辑：把全部 delta_color 移除后必须能检出
    stripped = re.sub(r',?\s*delta_color="(?:inverse|off)"', "", mutated)
    tree = ast.parse(stripped)
    bad = [c.lineno for c in _metric_calls(tree) if not _has_delta_color(c)]
    assert bad, "mutation 未被检出——守卫逻辑假绿"
