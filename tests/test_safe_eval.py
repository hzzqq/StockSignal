"""
tests/test_safe_eval.py
=======================
校验 modules.ai_engine._safe_eval：
- 简单四则运算正确求值；
- 任何非纯算术输入（含属性访问链沙箱逃逸 payload）一律返回 None，绝不执行代码。
"""
from __future__ import annotations

import pytest

from modules.ai_engine import _safe_eval


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("1+1", 2.0),
        ("2*(3+4)", 14.0),
        ("10/4", 2.5),
        ("-3+5", 2.0),
        ("1 + 1", 2.0),
        ("10-3-2", 5.0),
        ("2*3+4", 10.0),
        ("(2+3)*4", 20.0),
        ("0", 0.0),
        ("3.5*2", 7.0),
    ],
)
def test_arithmetic(expr, expected):
    assert _safe_eval(expr) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expr",
    [
        "",                       # 空
        "abc",                    # 非数字
        "1+",                     # 残缺
        "1/0",                    # 除零
        "2**3",                   # 不支持的幂运算
        "(1).__class__",          # 属性访问链（沙箱逃逸）
        "(1).__class__.__subclasses__()",  # 经典逃逸 payload
        "__import__('os')",       # 导入（被正则拦截）
        "1;import os",            # 语句注入（被正则拦截）
        "open('x')",              # 调用（被正则拦截）
    ],
)
def test_rejected(expr):
    assert _safe_eval(expr) is None
