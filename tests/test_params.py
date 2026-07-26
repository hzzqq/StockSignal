"""
tests/test_params.py
--------------------
parse_int_param 的纯逻辑测试，直接传入普通 dict 作为 source，
无需 Flask 应用上下文。
"""
from backend.utils.params import parse_int_param


def test_normal_value():
    assert parse_int_param("n", default=0, source={"n": "42"}) == 42


def test_non_numeric_returns_default():
    assert parse_int_param("n", default=7, source={"n": "abc"}) == 7


def test_below_lo_clamped():
    assert parse_int_param("n", default=0, lo=5, source={"n": "2"}) == 5


def test_above_hi_clamped():
    assert parse_int_param("n", default=0, hi=10, source={"n": "99"}) == 10


def test_missing_key_returns_default():
    assert parse_int_param("n", default=3, source={}) == 3


def test_negative_below_lo_clamped():
    assert parse_int_param("n", default=0, lo=1, source={"n": "-5"}) == 1
