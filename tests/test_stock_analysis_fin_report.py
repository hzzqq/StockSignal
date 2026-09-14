"""个股分析页 · 财报区块结构守卫（v3 · 2026-09-13 改版）。

用 AST + 源码扫描锁定三件事，防止被后续改动静默回退：

1. **报告期选择区必须「折叠 + 两行」**（需求 3）
   旧实现是 6 项 `st.selectbox`（视觉上占一行但展开后 6 行长列表，用户嫌占位置）。
   新实现：两行 pill 按钮（4 个报告类型 + 3 个年度），其余期次收进 expander。
   守卫点：`fragment_financial_report` 内不得再出现"报告期 selectbox"；
   必须存在 2 个 `st.columns` 行 + "更多报告期" expander。

2. **必须存在横向历史对比区块**（需求 2）
   至少 3 年主要指标的柱状+折线图 + 下方「展开分析」模块。
   守卫点：`_build_perf_history_fig` 必须同时含 `go.Bar` 与 `go.Scatter`，
   且 `yaxis="y2"`（副轴同比）；`_build_perf_history_section` 必须含展开分析 expander。

3. **不得再把 `window.scrollTo` 当唯一回顶手段**（需求 1 连带）
   页内「回到顶部」按钮已移除（由全局悬浮 ▲ 承担），若重新引入需走 scroll_nav。
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_PAGE = pathlib.Path(__file__).resolve().parents[1] / "pages" / "20_个股分析.py"


@pytest.fixture(scope="module")
def src() -> str:
    return _PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tree(src: str) -> ast.Module:
    return ast.parse(src)


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"未找到函数 {name}")


def _func_source(src: str, tree: ast.Module, name: str) -> str:
    node = _func(tree, name)
    lines = src.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def _local_list_literal(tree: ast.Module, func_name: str, var_name: str) -> list:
    """取出函数体内的 ``var_name = [...]`` 字面量（仅字面量，不求值页面代码）。

    _MAIN_PERIODS / _YEARS 是 fragment 内的局部常量，故按函数体扫描。
    """
    fn = _func(tree, func_name)
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == var_name:
                    val = ast.literal_eval(node.value)
                    return list(val) if isinstance(val, (list, tuple)) else []
    raise AssertionError(f"未在 {func_name} 内找到列表常量 {var_name}")


# ───────────────────────── 需求 3：报告期选择区瘦身 ─────────────────────────

def test_period_selector_no_long_selectbox(src, tree):
    """报告期不得再用 st.selectbox（旧实现的长列表正是用户抱怨的「太占位置」）。"""
    body = _func_source(src, tree, "fragment_financial_report")
    # 财报「报告期」选择不得走 selectbox（披露日历/市场的 selectbox 属合理保留）
    assert 'st.selectbox(\n        "报告期"' not in body
    assert '"报告期", options=list(PERIODS_FIN' not in body
    # 更强的结构化断言：pill 按钮行必须存在
    assert "_MAIN_PERIODS" in body and "_YEARS" in body


def test_period_selector_is_two_rows_of_pills(src, tree):
    """必须是「两行」：一行报告类型 + 一行年度。"""
    body = _func_source(src, tree, "fragment_financial_report")
    # 报告类型行 4 列、年度行 3 列
    assert "_MAIN_PERIODS" in body
    assert "_YEARS" in body
    assert body.count("st.columns(") >= 2, "至少两行 pill 按钮组"

    # 4 个报告类型 + 3 个年度：从函数体内 AST 取局部字面量（不执行页面逻辑）
    main_periods = _local_list_literal(tree, "fragment_financial_report", "_MAIN_PERIODS")
    years = _local_list_literal(tree, "fragment_financial_report", "_YEARS")
    assert len(main_periods) == 4, f"第一行应为 4 个报告类型，实际 {main_periods}"
    assert len(years) == 3, f"第二行应为 3 个年度，实际 {years}"
    # 后缀须覆盖 4 种法定报告期
    assert {sfx for _lbl, sfx in main_periods} == {"0331", "0630", "0930", "1231"}


def test_period_selector_is_collapsible(src, tree):
    """其余历史期次必须收在 expander（折叠）。"""
    body = _func_source(src, tree, "fragment_financial_report")
    assert "更多报告期" in body, "缺少「更多报告期」折叠区"
    assert "st.expander(" in body, "折叠区必须用 st.expander"


def test_period_code_built_from_type_and_year(src, tree):
    """period 必须由「年度 + 报告类型后缀」拼接（而非硬编码 6 个常量）。"""
    body = _func_source(src, tree, "fragment_financial_report")
    assert '_sfx_map.get(_cur' in body
    assert "fr_period_label(period)" in body


# ───────────────────────── 需求 2：横向历史对比 ─────────────────────────

def test_history_fig_has_bar_and_secondary_axis_line(tree):
    """柱子（规模，主轴）+ 折线（同比，副轴 y2）。"""
    node = _func(tree, "_build_perf_history_fig")
    seg = ast.unparse(node)
    assert "Bar(" in seg, "必须有柱状（规模）"
    assert "Scatter(" in seg, "必须有折线（同比）"
    assert "yaxis2" in seg or "yaxis='y2'" in seg or 'yaxis="y2"' in seg, (
        "同比折线必须挂副轴 y2"
    )
    assert "overlaying" in seg, "副轴需 overlaying y"


def test_history_fig_uses_red_up_green_down(tree):
    """业绩域配色必须是红涨绿跌（_PERF_UP 红 / _PERF_DOWN 绿）。"""
    seg = ast.unparse(_func(tree, "_build_perf_history_fig"))
    assert "_PERF_UP" in seg and "_PERF_DOWN" in seg
    # 不得误用价格域的 RED/GREEN（20页价格域是绿涨红跌例外）
    assert "bar_colors" in seg


def test_history_fig_degrades_when_insufficient(tree):
    """数据不足 2 期必须返回 None（不合成假数据）。"""
    seg = ast.unparse(_func(tree, "_build_perf_history_fig"))
    assert "len(x) < 2" in seg
    assert "return None" in seg


def test_history_fig_units_are_yi(tree):
    """规模单位换算为亿元（元 / 1e8）。"""
    seg = ast.unparse(_func(tree, "_build_perf_history_fig"))
    assert ("1e8" in seg) or ("100000000" in seg), "必须把元换算成亿元再绘图"


def test_history_section_exists_with_expand_analysis(src, tree):
    """下方必须有「展开分析」功能模块，且与图同源。"""
    body = _func_source(src, tree, "_build_perf_history_section")
    assert "展开分析" in body, "缺少「展开分析」模块"
    assert "fr_expand_rows" in body, "展开分析必须复用 fr_expand_rows（与图同源）"
    assert "fr_yoy_column" in body, "同比取数须走登记表，避免列名拼接错误"


def test_history_section_honest_empty_state(src, tree):
    """无数据时必须给诚实兜底提示，不得静默空白。"""
    body = _func_source(src, tree, "_build_perf_history_section")
    assert "_empty_info" in body
    assert "return" in body


def test_history_section_called_in_fragment(src, tree):
    """横向对比区块必须真的被财报片段调用（否则是死代码）。"""
    body = _func_source(src, tree, "fragment_financial_report")
    assert "_build_perf_history_section(" in body


def test_history_history_fetch_covers_at_least_three_years(src):
    """横向数据必须覆盖 ≥3 年。"""
    assert "_HISTORY_YEARS" in src
    ns = {}
    for ln in src.splitlines():
        if ln.startswith("_HISTORY_YEARS"):
            exec(ln, ns)  # noqa: S102
            break
    years = ns.get("_HISTORY_YEARS", ())
    assert len(years) >= 3, f"横向历史必须覆盖 ≥3 年，实际 {years}"


# ───────────────────────── 需求 1 连带：回顶按钮 ─────────────────────────

def test_page_no_longer_injects_own_back_to_top_button(src):
    """页内「回到顶部」按钮已移除（改由全局悬浮 ▲ 承担，避免与右下角按钮重叠）。"""
    assert "analysis_back_to_top" not in src, (
        "页内回到顶部按钮应已移除；如需保留请改用 scroll_nav 的悬浮实现"
    )


def test_page_no_duplicate_inline_scroll_button_in_other_pages():
    """防止其它页面重新引入 st.markdown inline「回到顶部」（该写法会被 + 与悬浮按钮重叠）。"""
    pages_dir = _PAGE.parent
    offenders = []
    for p in pages_dir.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("st.markdown(") and "回到顶部</button>" in line:
                offenders.append(f"{p.name}: {line.strip()[:80]}")
    assert not offenders, "存在重复的 inline 回到顶部按钮：\n" + "\n".join(offenders)
