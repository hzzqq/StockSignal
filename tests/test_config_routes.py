"""
tests/test_config_routes.py
===========================
离线单测 backend.api.config_routes._validate_config_value。

纯函数，无 Flask 上下文依赖。覆盖：
- 合法 str / int / float -> (True, str(value))
- bool True / False -> (True, "true"/"false")（非 "True"/"False"）
- None -> (False, "值不能为空")
- 超长字符串 -> (False, "值过长或格式不支持")
- 非字符串垃圾（dict/list/object） -> (False, "值过长或格式不支持")
"""
from __future__ import annotations

import pytest

from backend.api.config_routes import _validate_config_value


def test_valid_str_passthrough():
    ok, val = _validate_config_value("hello")
    assert ok is True
    assert val == "hello"


def test_valid_int():
    ok, val = _validate_config_value(42)
    assert ok is True
    assert val == "42"


def test_valid_float():
    ok, val = _validate_config_value(3.14)
    assert ok is True
    assert val == "3.14"


def test_bool_true():
    ok, val = _validate_config_value(True)
    assert ok is True
    assert val == "true"  # 关键：不能是 "True"


def test_bool_false():
    ok, val = _validate_config_value(False)
    assert ok is True
    assert val == "false"  # 关键：不能是 "False"


def test_none_rejected():
    ok, val = _validate_config_value(None)
    assert ok is False
    assert val == "值不能为空"


def test_too_long_rejected():
    ok, val = _validate_config_value("x" * 4097)
    assert ok is False
    assert val == "值过长或格式不支持"


def test_boundary_length_4096_allowed():
    ok, val = _validate_config_value("x" * 4096)
    assert ok is True
    assert val == "x" * 4096


def test_non_str_garbage_dict_rejected():
    ok, val = _validate_config_value({"a": 1})
    assert ok is False
    assert val == "值过长或格式不支持"


def test_non_str_garbage_list_rejected():
    ok, val = _validate_config_value([1, 2, 3])
    assert ok is False
    assert val == "值过长或格式不支持"


def test_non_str_garbage_object_rejected():
    class _Weird:
        pass

    ok, val = _validate_config_value(_Weird())
    assert ok is False
    assert val == "值过长或格式不支持"


def test_tuple_shape():
    """所有可能路径都返回 (bool, str) 二元组。"""
    samples = ["s", 1, 2.5, True, False, None, "x" * 4097, {"k": "v"}, [1], object()]
    for raw in samples:
        result = _validate_config_value(raw)
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, val = result
        assert isinstance(ok, bool)
        assert isinstance(val, str)
