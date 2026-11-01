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
# P0-1c（2026-10-30）：40 页渲染主体抽取至 modules/portfolio_views.py，
# 同 P0-1a/b 机制：清单条目保留（覆盖面不弱化），定位改指实现体内对应渲染函数。
_RELOCATED = {
    "20_个股分析.py": ("stock_research.py", "render_stock_analysis"),
    "11_股票选取.py": ("stock_research.py", "render_stock_picker"),
    "40_仓位管理.py": ("portfolio_views.py", "render_position_manager"),
}


def _guard_tree(fname: str) -> ast.AST:
    """守卫清单页名 → 实现体 AST 节点（函数体级）；未迁移页照常解析页面文件。"""
    reloc = _RELOCATED.get(fname)
    if reloc is None:
        return ast.parse((PAGES / fname).read_text(encoding="utf-8"))
    modname, fnname = reloc
    mod = ast.parse((MODULES / modname).read_text(encoding="utf-8"))
    for node in ast.walk(mod):
        if isinstance(node, ast.FunctionDef) and node.name == fnname:
            return node
    raise AssertionError(f"守卫清单文件缺失实现体: {modname}::{fnname}（{fname}）")
# 已完成 delta_color 全量补齐的页面（增量补齐时追加到此清单）
COMPLETED_FILES = [
    # "30_策略回测.py",  # P1-5 批3：7 组 27 处已迁 xc_kpi_grid/stat_tile（收益类补 tone 正红负绿），页内零 metric，移出
    "11_股票选取.py",
    # "22_基本面分析.py",  # P1-5 批3：全部 25 处已迁 xc_kpi_grid/stat_tile，页内零 metric，移出
    # "23_事件追踪.py",  # P1-5 批3：3 组 11 处已迁 xc_kpi_grid，页内零 metric，移出
    # "36_每日荐股.py",  # 2026-10-28 已迁移至 xc_kpi_grid（delta_dir 统一保证 A股红涨绿跌，另由 test_ui_design_system 守卫）；不再直接调用 st.metric，故移出裸 st.metric 守卫清单
    # "16_财报日历.py",  # P1-5 批2：两组 KPI 行已迁 xc_kpi_grid（help→meta），页内零 st.metric，移出
    # "35_资金流向.py",  # P1-5 批2：两融/主力净流入两组已迁 xc_kpi_grid（normal 美股语义一并修正为 delta_dir A股语义），移出
    "20_个股分析.py",
    "40_仓位管理.py",
    # "43_实盘交易.py",  # P1-5 批2：账户概览 5 卡已迁 xc_kpi_grid（help→meta），页内零 st.metric，移出
    # "50_市场情绪.py",  # P1-5 批1：预判准确率卡已迁 xc_kpi_grid（meta 承载 help），页内零 st.metric，移出裸 st.metric 守卫清单
    # "70_涨停复盘.py",  # P1-5 批1：「池内曾开板」已迁 stat_tile（同 .xc-card 视觉，delta_dir=flat），页内零 st.metric，移出
    # "94_消息中心.py",  # P1-5 批1：未读/总消息已迁 stat_tile（同 .xc-card 视觉），页内零 st.metric，移出（渲染仍由 test_94_message_center_unified 守卫）
    # "98_仓位落地.py",  # P1-5 批2：市场头部/分配两组已迁 xc_kpi_grid，页内零 st.metric，移出
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
    """mutation 自验：构造携带 delta_color 的 st.metric 片段，剥离后守卫逻辑必须能检出（防假绿）。

    批3 收官（2026）后 pages/ 已零 metric 调用（G6 封禁），文件级 mutation 种子
    （COMPLETED_FILES[0]）随之失效——改用合成片段做种子，守卫逻辑验证意图不变，
    且不再与任何页面文件的存量耦合。"""
    snippet = (
        "import streamlit as st\n"
        'st.metric("甲", "1", delta="+1.2%", delta_color="inverse")\n'
        'st.metric("乙", "2", delta_color="off")\n'
    )
    tree = ast.parse(snippet)
    seeds = list(_metric_calls(tree))
    assert seeds and all(_has_delta_color(c) for c in seeds), "合成种子本身不合法"
    mutated = re.sub(r',?\s*delta_color="(?:inverse|off)"', "", snippet)
    assert mutated != snippet, "mutation 种子失效"
    bad = [c.lineno for c in _metric_calls(ast.parse(mutated)) if not _has_delta_color(c)]
    assert bad, "mutation 未被检出——守卫逻辑假绿"
