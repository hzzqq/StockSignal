"""针对 pages/9_价格预警.py 中纯函数 validate_alert_condition 的单元测试。

该页面在模块顶层会执行大量 Streamlit / akshare 相关逻辑，无法在 pytest 中
直接 import。这里通过 ast 仅抽取目标纯函数的源码并独立执行，从而既能测试
真实代码、又避免触发页面的副作用（网络/UI）。
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules.format_helpers import safe_float  # noqa: E402

PAGE_PATH = os.path.join(ROOT, "pages", "9_价格预警.py")


def _load_validator():
    with open(PAGE_PATH, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "validate_alert_condition":
            lines = src.splitlines()
            code = "\n".join(lines[node.lineno - 1: node.end_lineno])
            ns = {"safe_float": safe_float}
            exec(compile(code, PAGE_PATH, "exec"), ns)  # noqa: S102
            return ns["validate_alert_condition"]
    raise RuntimeError("validate_alert_condition not found in page file")


validate_alert_condition = _load_validator()


def test_valid_numeric_threshold():
    ok, err = validate_alert_condition("threshold", 10)
    assert ok is True and err is None


def test_nonnumeric_threshold():
    ok, err = validate_alert_condition("threshold", "abc")
    assert ok is False and err


def test_negative_threshold_invalid():
    ok, err = validate_alert_condition("threshold", -5)
    assert ok is False and err


def test_empty_threshold_invalid():
    ok, err = validate_alert_condition("threshold", "")
    assert ok is False and err


def test_cross_missing_value2():
    ok, err = validate_alert_condition("cross", 1.0)
    assert ok is False and err


def test_valid_cross_two_values():
    ok, err = validate_alert_condition("cross", 1.0, 2.0)
    assert ok is True and err is None


def test_percent_out_of_range():
    ok, err = validate_alert_condition("percent", 150)
    assert ok is False and err


def test_percent_valid():
    ok, err = validate_alert_condition("percent", 50)
    assert ok is True and err is None
