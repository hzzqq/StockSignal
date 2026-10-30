# -*- coding: utf-8 -*-
"""守卫：st.metric 必须显式携带 delta_color（铁律 2：A 股红涨绿跌语义）。
渐进清单机制：已完成补齐的页面纳入 COMPLETED_FILES，新增/修改这些文件时
任何 st.metric 缺 delta_color、或使用 normal（美股绿涨语义）都会被拦截。
AST 扫描（关键字级），配套 mutation 自验用例。"""
import ast
import re
from pathlib import Path

import pytest

PAGES = Path(__file__).resolve().parent.parent / "pages"
# P0-1a/P0-1b（2026-10-30）：20/11 页渲染主体抽取至 modules/stock_research.py
# （pages/20、pages/11 为独立入口 shim）。守卫清单条目保留（覆盖面不弱化），
# 定位改指实现体内对应渲染函数（函数体级，防同模块跨子页内容互相污染）；
# 断言本体零改动（spec §1.6 预授权）。
MODULES = Path(__file__).resolve().parent.parent / "modules"
_RELOCATED = {
    "20_个股分析.py": "render_stock_analysis",
    "11_股票选取.py": "render_stock_picker",
}


def _guard_tree(fname: str) -> ast.AST:
    """守卫清单页名 → 实现体 AST 节点（函数体级）；未迁移页照常解析页面文件。"""
    fnname = _RELOCATED.get(fname)
    if fnname is None:
        return ast.parse((PAGES / fname).read_text(encoding="utf-8"))
    mod = ast.parse((MODULES / "stock_research.py").read_text(encoding="utf-8"))
    for node in ast.walk(mod):
        if isinstance(node, ast.FunctionDef) and node.name == fnname:
            return node
    raise AssertionError(f"守卫清单文件缺失实现体: stock_research.py::{fnname}（{fname}）")
# 已完成 delta_color 全量补齐的页面（增量补齐时追加到此清单）
COMPLETED_FILES = [
    "30_策略回测.py",
    "11_股票选取.py",
    "22_基本面分析.py",
    "23_事件追踪.py",
    # "36_每日荐股.py",  # 2026-10-28 已迁移至 xc_kpi_grid（delta_dir 统一保证 A股红涨绿跌，另由 test_ui_design_system 守卫）；不再直接调用 st.metric，故移出裸 st.metric 守卫清单
    "16_财报日历.py",
    "35_资金流向.py",
    "20_个股分析.py",
    "40_仓位管理.py",
    "43_实盘交易.py",
    "50_市场情绪.py",
    "70_涨停复盘.py",
    "94_消息中心.py",
    "98_仓位落地.py",
]


def _metric_calls(tree: ast.AST):
    """yield 每个 st.metric(...) 调用节点"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "metric":
            base = f.value
            if (isinstance(base, ast.Attribute) and base.attr == "st") or \
               (isinstance(base, ast.Name) and base.id == "st"):
                yield node


def _has_delta_color(call: ast.Call) -> bool:
    return any(kw.arg == "delta_color" for kw in call.keywords)


@pytest.mark.parametrize("fname", COMPLETED_FILES)
def test_completed_pages_all_metrics_have_delta_color(fname):
    tree = _guard_tree(fname)
    calls = list(_metric_calls(tree))
    assert calls, f"{fname} 未扫描到 st.metric 调用（文件结构变化需更新守卫）"
    bad = [c.lineno for c in calls if not _has_delta_color(c)]
    assert not bad, f"{fname} 第 {bad} 行 st.metric 缺 delta_color（红涨绿跌铁律）"


@pytest.mark.parametrize("fname", COMPLETED_FILES)
def test_completed_pages_no_us_semantics(fname):
    """禁止 normal（美股绿涨语义），A 股只允许 inverse/off"""
    tree = _guard_tree(fname)
    for c in _metric_calls(tree):
        for kw in c.keywords:
            if kw.arg == "delta_color" and isinstance(kw.value, ast.Constant):
                assert kw.value.value != "normal", \
                    f"{fname} 第 {c.lineno} 行 delta_color='normal' 为美股语义，A 股须用 inverse/off"


def test_mutation_guard_catches_missing_delta_color():
    """mutation 自验：把已完成文件的 delta_color 全部剥离后，守卫逻辑必须能检出（防假绿）"""
    target = PAGES / COMPLETED_FILES[0]
    src = target.read_text(encoding="utf-8")
    mutated = re.sub(r',?\s*delta_color="(?:inverse|off)"', "", src)
    assert mutated != src, "mutation 种子失效"
    tree = ast.parse(mutated)
    bad = [c.lineno for c in _metric_calls(tree) if not _has_delta_color(c)]
    assert bad, "mutation 未被检出——守卫逻辑假绿"
