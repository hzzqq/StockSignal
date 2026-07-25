"""format_helpers 新增 clamp / safe_delta / to_percent_str 纯函数测试（无网依赖）。"""
import math

import modules.format_helpers as FH


def test_clamp_normal():
    assert FH.clamp(50, 0, 100) == 50
    assert FH.clamp(150, 0, 100) == 100
    assert FH.clamp(-5, 0, 100) == 0


def test_clamp_nan_none_fallback():
    assert FH.clamp(float("nan"), 0, 100) == 0
    assert FH.clamp(None, 0, 100) == 0
    assert FH.clamp(float("inf"), 0, 100) == 100
    assert FH.clamp(float("-inf"), 0, 100) == 0


def test_safe_delta_basic():
    assert FH.safe_delta(10, 3) == 7
    assert FH.safe_delta(3, 10) == -7


def test_safe_delta_none_nan():
    assert FH.safe_delta(None, 5) == 0.0
    assert FH.safe_delta(5, None) == 0.0
    assert FH.safe_delta(float("nan"), 5) == 0.0
    assert FH.safe_delta(5, float("inf")) == 0.0


def test_to_percent_str():
    assert FH.to_percent_str(12.34) == "12.34%"
    assert FH.to_percent_str(0) == "0.00%"
    assert FH.to_percent_str(None) == "—"
    assert FH.to_percent_str(float("nan")) == "—"
    assert FH.to_percent_str(-3.1, dp=1) == "-3.1%"
