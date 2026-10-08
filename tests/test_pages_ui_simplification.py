"""T-229 P1 页面精简守卫（AST 离线检查，无需起 Streamlit）。

钉住四页「次要模块收进折叠区 / 重复模块删除」的契约，防止后续改动把
主功能区重新撑爆或误删折叠结构：

- 91_我的：唯一设置入口（分区版），「设置一览」重复控件版不得回归；
  「账号绑定 / 系统通知」占位不得回归；我的收藏/快速查看收进「更多功能」折叠区；
- 30_策略回测：回撤带（与回撤曲线同源重复）不得回归；五个次要工具在
  「更多回测工具」折叠区内调用；
- 35_资金流向：三个走势对比 fragment 在「走势扩展对比」折叠区内调用，
  红涨绿跌语义（红=净流入）保留在页头 caption；
- 16_财报日历：个股财报查询在折叠区内调用（财务三表能力保留）。
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _src(page: str) -> str:
    return (REPO / "pages" / page).read_text(encoding="utf-8")


def _tree(page: str) -> ast.AST:
    return ast.parse(_src(page), filename=page)


def _expander_label(call: ast.Call) -> str | None:
    """安全提取 st.expander 第一个位置参数的静态文本（f-string 返回拼接的常量部分）。"""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant):
        return str(arg.value)
    if isinstance(arg, ast.JoinedStr):  # f-string：取其中的常量片段拼接
        return "".join(str(v.value) for v in arg.values if isinstance(v, ast.Constant))
    return None


def _top_level_expanders(page: str) -> list[str]:
    """收集模块顶层（缩进级）with st.expander 的标签。"""
    labels = []
    for node in ast.walk(_tree(page)):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    label = _expander_label(call)
                    if label is not None:
                        labels.append(label)
    return labels


# ───────────────────────── 91_我的 ─────────────────────────
def test_91_no_duplicate_settings_panel():
    src = _src("91_我的.py")
    assert "当前全部设置一览" not in src, "重复的设置一览控件版不得回归（与分区版写同一状态）"


def test_91_placeholders_removed():
    src = _src("91_我的.py")
    assert "账号绑定" not in src, "占位按钮（仅提示暂未启用）不得回归"
    assert "系统通知" not in src, "纯占位空态不得回归"
    assert "我的导读" not in src


def test_91_secondary_in_expander():
    labels = "\n".join(_top_level_expanders("91_我的.py"))
    assert "更多功能（我的收藏 · 快速查看股票）" in labels
    src = _src("91_我的.py")
    assert src.count("查看示例自选股") == 0, "编造示例数据面板不得回归（诚实语义）"


# ───────────────────────── 30_策略回测 ─────────────────────────
def test_30_no_duplicate_drawdown_band():
    src = _src("30_策略回测.py")
    assert "回撤带" not in src, "回撤带与回撤曲线同源重复，不得回归"
    assert "downsample" not in src


def test_30_secondary_fragments_wrapped():
    """五个次要回测工具的**调用**必须位于「更多回测工具」折叠区内部。"""
    tree = _tree("30_策略回测.py")
    wrapped: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    if call.args and "更多回测工具" in (_expander_label(call) or ""):
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                                fn = sub.value.func
                                if isinstance(fn, ast.Name):
                                    wrapped.add(fn.id)
    for fn in ("fragment_strong_bull", "fragment_param_scan",
               "fragment_batch_backtest", "fragment_walk_forward", "fragment_run_history"):
        assert fn in wrapped, f"{fn} 必须在「更多回测工具」折叠区内调用"


# ───────────────────────── 35_资金流向 ─────────────────────────
def test_35_trend_fragments_wrapped_and_semantics_kept():
    tree = _tree("35_资金流向.py")
    wrapped: set[str] = set()
    label_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    if call.args and "走势扩展对比" in (_expander_label(call) or ""):
                        label_found = True
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                                fn = sub.value.func
                                if isinstance(fn, ast.Name):
                                    wrapped.add(fn.id)
    assert label_found, "「走势扩展对比」折叠区不得移除"
    for fn in ("fragment_index_trend", "fragment_industry_trend", "fragment_etf_trend"):
        assert fn in wrapped, f"{fn} 必须在折叠区内调用"
    src = _src("35_资金流向.py")
    assert "红=净流入、绿=净流出" in src, "A股红涨绿跌全局语义不得丢失"


# ───────────────────────── 16_财报日历 ─────────────────────────
def test_16_stock_financials_wrapped():
    tree = _tree("16_财报日历.py")
    wrapped = False
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "expander":
                    if call.args and "个股财报查询" in (_expander_label(call) or ""):
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                                if getattr(sub.value.func, "id", "") == "fragment_stock_financials":
                                    wrapped = True
    assert wrapped, "个股财报查询必须在折叠区内调用（财务三表能力保留）"
