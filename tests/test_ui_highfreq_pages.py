# -*- coding: utf-8 -*-
"""tests/test_ui_highfreq_pages.py — 高频页提示/KPI 收敛守卫（T-147 批2）。

spec：``.workbuddy/specs/t145_ui_upgrade_contract.md`` AC2/AC3。

锁三条不变量：
1. AC3：高频 6 页（事件追踪/股票选取/策略回测/基本面分析/今日决策面板/模拟交易）
   原生 ``st.error/warning/info/success`` 必须归零——全部走 ui_kit xc 盒（统一视觉，
   消除「提示双轨：271 处原生 vs 281 处 xc 盒随页随机」）。
2. 页面用到的 xc_* 必须显式 import（防 NameError 静默崩页）。
3. AC2/C2：模拟交易页 KPI 必须走 canonical ``xc_kpi_grid``；高频页禁止
   ``c1.metric(...)`` 这类「变量.metric」逃逸形态（曾致 delta_color 守卫漏拦）。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages"

HIGHFREQ = [
    "23_事件追踪.py",
    "11_股票选取.py",
    "30_策略回测.py",
    "22_基本面分析.py",
    "54_今日决策面板.py",
    "42_模拟交易.py",
]

_RAW_ALERTS = {"error", "warning", "info", "success"}
_XC_BOXES = {"xc_error_box", "xc_warn_box", "xc_info_banner", "xc_success_box"}


def _tree_of(name: str):
    return ast.parse((PAGES / name).read_text(encoding="utf-8"))


def _st_alert_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in _RAW_ALERTS \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "st":
            yield node


def _var_metric_calls(tree):
    """``<var>.metric(...)``（接收变量上的 metric，如 c1.metric）——逃逸 st.metric 守卫的形态。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "metric" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id != "st":
            yield node


def _var_metric_delta_escapes(tree):
    """``<var>.metric(delta=...)`` 且未显式 delta_color——语义色失控形态。"""
    for node in _var_metric_calls(tree):
        has_delta = any(k.arg == "delta" for k in node.keywords) or len(node.args) >= 3
        has_color = any(k.arg == "delta_color" for k in node.keywords)
        if has_delta and not has_color:
            yield node


def _names_used(tree, names):
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names:
            used.add(node.func.id)
    return used


def test_highfreq_pages_no_raw_alerts():
    """AC3：高频页原生提示归零，统一走 ui_kit xc 盒。"""
    offenders = []
    for name in HIGHFREQ:
        tree = _tree_of(name)
        for call in _st_alert_calls(tree):
            offenders.append(f"{name}:{call.lineno} st.{call.func.attr}")
    assert not offenders, (
        "高频页仍存在原生 st.error/warning/info/success（应替换为 ui_kit xc 盒，spec AC3）：\n  "
        + "\n  ".join(offenders)
    )


def test_highfreq_pages_import_what_they_use():
    """页面用到的 xc_* 必须出现在 ui_kit import 行（防 NameError）。"""
    problems = []
    for name in HIGHFREQ:
        src = (PAGES / name).read_text(encoding="utf-8")
        tree = _tree_of(name)
        used = _names_used(tree, _XC_BOXES | {"xc_kpi_grid"})
        if not used:
            continue
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "modules.ui_kit":
                imported |= {a.name for a in node.names}
        missing = used - imported
        if missing:
            problems.append(f"{name}: 使用但未 import {sorted(missing)}")
    assert not problems, "xc_* 使用与 import 不一致：\n  " + "\n  ".join(problems)


def test_highfreq_pages_no_var_metric_escape():
    """AC2：高频页 ``<变量>.metric(delta=...)`` 必须显式 delta_color（曾逃逸 st.metric 守卫）。"""
    offenders = []
    for name in HIGHFREQ:
        for call in _var_metric_delta_escapes(_tree_of(name)):
            offenders.append(f"{name}:{call.lineno} {call.func.value.id}.metric")
    assert not offenders, (
        "高频页存在 <变量>.metric(delta=...) 未显式 delta_color（A股红涨绿跌语义失控）：\n  "
        + "\n  ".join(offenders)
    )


def test_42_paper_trading_kpi_uses_xc_grid():
    """C2：模拟交易页账户概览 KPI 走 canonical xc_kpi_grid（Bento 样板）。"""
    tree = _tree_of("42_模拟交易.py")
    used = _names_used(tree, {"xc_kpi_grid"})
    assert used, "42_模拟交易.py 未使用 xc_kpi_grid（账户概览 KPI 应收敛到 Bento 样板）"
