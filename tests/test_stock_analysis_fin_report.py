"""个股分析页 · 财报区块结构守卫（C 轮改版 · 2026-09-13 之后）。

用 AST + 源码扫描锁定几件事，防止被后续改动静默回退：

1. **报告期选择区 =「折叠 + selectbox + 多期 multiselect」**（C 轮用户要求「改回之前的报告模板」）
   v3 的「两行 pill 按钮」被用户反馈「巨丑且功能缺失」，故回退为更实用的
   折叠 expander 内：单期 `st.selectbox("单期报告期")` + 多期 `st.multiselect("多期对比")`。
   守卫点：`fragment_financial_report` 必须含 `st.expander("🗓️ 报告期选择")` +
   `st.selectbox("单期报告期")` + `st.multiselect("多期对比")`；
   且横向对比 `_build_perf_history_section` 必须出现在报告期选择区之前（用户要求放到下面）。

2. **必须存在横向历史对比区块**（需求 2）
   至少 3 年主要指标的柱状+折线图 + 下方「展开分析」模块。
   守卫点：`_build_perf_history_fig` 必须同时含 `go.Bar` 与 `go.Scatter`，
   且 `yaxis="y2"`（副轴同比）；`_build_perf_history_section` 必须含展开分析 expander。

3. **报告期选项必须动态生成（不硬编码）**
   `PERIODS_FIN = _build_periods_fin()`，按「当前年 + 前 5 年 × 4 个法定报告期」生成；
   业绩查询起点由 `_get_listing_year` 决定（上市年份，最多回看 10 年）。

4. **不得再把 `window.scrollTo` 当唯一回顶手段**（需求 1 连带）
   页内「回到顶部」按钮已移除（由全局悬浮 ▲ 承担，apply_theme 注入），若重新引入需走 scroll_nav。
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


# ───────────────────────── 需求 3：报告期选择区（折叠 + selectbox + 多期）─────────────────────────

def test_period_selector_is_collapsible_selectbox(src, tree):
    """报告期选择区必须是「折叠 expander + 单期 selectbox + 多期 multiselect」。

    C 轮用户明确要求「改回之前的报告模板（保留可折叠）」——即 v3 之前的
    selectbox 下拉模板，但保留可折叠，并追加上「多期对比」生成 Excel 式表格。
    """
    body = _func_source(src, tree, "fragment_financial_report")
    # 折叠容器
    assert "st.expander(" in body, "报告期选择必须收在 st.expander（可折叠）"
    assert "🗓️ 报告期选择" in body, "缺少「🗓️ 报告期选择」折叠区"
    # 单期 selectbox（用户要求改回之前的下拉模板）
    assert "单期报告期" in body and "st.selectbox(" in body, (
        "必须保留单期报告期 selectbox（C 轮回退到此前模板）"
    )
    # 多期对比（C 轮新增）
    assert "多期对比" in body and "st.multiselect(" in body, (
        "必须支持多期对比 multiselect"
    )


def test_period_selector_dynamic_not_hardcoded(src, tree):
    """报告期选项必须动态生成（PERIODS_FIN = _build_periods_fin()），不得硬编码常量。

    业绩查询起点由 _get_listing_year 决定（上市年份，最多回看 10 年）。
    """
    assert "def _build_periods_fin()" in src, "缺少 _build_periods_fin 动态生成函数"
    assert "PERIODS_FIN = _build_periods_fin()" in src, (
        "PERIODS_FIN 必须由 _build_periods_fin() 生成"
    )
    assert "def _get_listing_year(" in src, "缺少 _get_listing_year（上市年份推断）"
    assert "_get_listing_year(code)" in src, "_fr_cached_history 须用 _get_listing_year 决定起点"

    body = _func_source(src, tree, "_build_periods_fin")
    # 4 个法定报告期后缀齐全
    for sfx in ("0331", "0630", "0930", "1231"):
        assert sfx in body, f"_build_periods_fin 缺少报告期后缀 {sfx}"
    # 按年份区间循环生成（非硬编码枚举）
    assert "range(" in body, "_build_periods_fin 应按年份区间循环生成"


def test_period_history_called_before_selector(src, tree):
    """横向对比必须出现在报告期选择区之前（用户要求「放到业绩横向对比下面」）。"""
    body = _func_source(src, tree, "fragment_financial_report")
    pos_history = body.find("_build_perf_history_section(")
    pos_expander = body.find("🗓️ 报告期选择")
    assert pos_history != -1 and pos_expander != -1, (
        "横向对比与报告期选择区都必须存在"
    )
    assert pos_history < pos_expander, (
        "横向对比必须位于报告期选择区之前（用户要求放到下面）"
    )


def test_period_code_built_from_type_and_year(src, tree):
    """period 必须来自动态 PERIODS_FIN（年度 + 报告类型后缀拼接），且复用 fr_period_label。"""
    body = _func_source(src, tree, "fragment_financial_report")
    assert "PERIODS_FIN[period_label]" in body, (
        "单期 period 应取自动态 PERIODS_FIN"
    )
    assert "fr_period_label(" in body, (
        "报告期标签须走 fr_period_label（避免列名拼接错误）"
    )


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
    # 回到顶部必须走全局 inject_scroll_nav（apply_theme 注入），而非页内重复注入
    assert "sn.inject_scroll_nav(dark=dark)" not in src, (
        "不得再次页内注入 inject_scroll_nav：全局 apply_theme 已注入，"
        "重复调用会触发 components.html 仅首次可靠执行的限制"
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
