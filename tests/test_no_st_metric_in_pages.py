# -*- coding: utf-8 -*-
"""G6 终态封禁守卫：pages/ 目录禁止任何 Streamlit metric 真实调用。

背景（P1-5 st.metric → xc_kpi_grid/stat_tile 渐进迁移，2026 收官）：
  - 批1 六轻页   7 处清零（50/60/70/84/94/97 部分，commit 386a871）
  - 批2 四中页  28 处清零（16/35/43/98 + 22/35 美股语义违规修正，commit ec800f5）
  - 批3 四重页  25+11+27+15=78 处清零（22/23/30/97，含 var.metric 形态）
    + 批次外漏网 4 页 16 处补迁（34/51/85/93，grep st\\.metric 口径漏网的 var.metric
      与 Phase3 统计遗漏页）→ pages/ 全目录 metric 调用归零，本守卫随即 hard 上线。

规则：
  - AST 扫描 pages/*.py，凡 Call 的 func 为 Attribute 且 attr == "metric"
    （涵盖 st.metric / col.metric / c1.metric 等一切接收者形态）即 fail——
    注释与字符串中的「st.metric」字样不是 AST 调用节点，天然放行
    （如 84/35 页迁移来源注释、本文件 docstring）。
  - KPI 统一走 ui_kit 的 canonical 家族：xc_kpi_grid（整组）/ stat_tile（窄列单卡），
    二者同为 _xc_card_html 渲染，A股红涨绿跌由 delta_dir/tone 语义色保证。
  - modules/ 下的实现体（stock_research/portfolio_views 等被 pages shim 委托的
    渲染函数）不在本守卫范围，由 test_metric_delta_color 的 _RELOCATED 机制继续锁。
  - hard fail 模式：存量已归零，无警告期必要。
"""
import ast
from pathlib import Path

import pytest

PAGES = Path(__file__).resolve().parent.parent / "pages"


def _metric_calls(tree: ast.AST):
    """yield 任何 ``<接收者>.metric(...)`` 调用节点（不限 st. 前缀，堵 var.metric 逃逸）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "metric":
            yield node


@pytest.mark.parametrize("page", sorted(PAGES.glob("*.py")))
def test_page_has_no_streamlit_metric_call(page):
    tree = ast.parse(page.read_text(encoding="utf-8"))
    calls = [(node.lineno, ast.unparse(node.func)) for node in _metric_calls(tree)]
    assert not calls, (
        f"{page.name} 出现 Streamlit metric 调用（G6 终态封禁，A股红涨绿跌由 "
        f"xc_kpi_grid/stat_tile 的 delta_dir/tone 保证）：\n  "
        + "\n  ".join(f"L{ln}: {fn}" for ln, fn in calls)
    )
