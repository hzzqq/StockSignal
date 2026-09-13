"""
backend/tests/test_params_helpers_contract.py
--------------------------------------------
SDD + TDD pilot（task_id=params_helpers_contract）：补齐 backend/utils/params.py 中
validate_stock_code / json_body / sanitize_text / parse_str_param 的**真实行为契约测试**。

这 4 个 helper 此前零测试覆盖，是 API 安全边界（股票代码校验、JSON 体类型校验、控制字符清洗、
字符串参数解析）。回归会静默漏过。本文件把它们锁成可观测契约。

约定：复用 test_pagination_bounds.py 的 sys.path 注入；json_body 用最小 Flask 实例 +
test_request_context 注入请求体，不引入 backend.app/DB，保持单测轻量。
纯函数测试一律传 source= 字典，避免依赖实时请求上下文。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from flask import Flask  # noqa: E402

from backend.utils.errors import ValidationError  # noqa: E402
from backend.utils.params import (  # noqa: E402
    json_body,
    parse_int_param,
    parse_str_param,
    sanitize_text,
    validate_stock_code,
)

_FLASK_APP = Flask(__name__)


# ============================================================ validate_stock_code
class TestValidateStockCode:
    @pytest.mark.parametrize("code,ok", [
        ("600519", True), ("000001", True), ("300750", True), ("688981", True),
    ])
    def test_valid_six_digit(self, code, ok):
        assert validate_stock_code(code) == (ok, code)

    @pytest.mark.parametrize("code", ["60051", "6005199", "60a519", "AB0001", ""])
    def test_invalid_format_rejected(self, code):
        assert validate_stock_code(code) == (False, "")

    def test_surrounding_whitespace_stripped(self):
        assert validate_stock_code("  600519  ") == (True, "600519")

    @pytest.mark.parametrize("code", [123, None, 600519, ["600519"]])
    def test_non_string_rejected(self, code):
        # 非 str（含恰好等于数字的整数）一律拒绝，避免类型穿透
        assert validate_stock_code(code) == (False, "")


# ============================================================ json_body
class TestJsonBody:
    def test_none_returns_empty_dict(self):
        with _FLASK_APP.test_request_context():
            assert json_body() == {}

    def test_dict_passthrough(self):
        with _FLASK_APP.test_request_context(method="POST", json={"a": 1, "b": [2, 3]}):
            assert json_body() == {"a": 1, "b": [2, 3]}

    @pytest.mark.parametrize("payload", [[1, 2], "str", 123, 1.5])
    def test_non_dict_raises_validation_error(self, payload):
        with _FLASK_APP.test_request_context(method="POST", json=payload):
            with pytest.raises(ValidationError):
                json_body()


# ============================================================ sanitize_text
class TestSanitizeText:
    def test_strips_zero_width(self):
        assert sanitize_text("a\u200bb") == "ab"

    def test_strips_nul(self):
        assert sanitize_text("a\x00b") == "ab"

    def test_strips_other_control_chars(self):
        assert sanitize_text("a" + chr(0x1F) + "b") == "ab"

    def test_keeps_newline_tab_cr(self):
        assert sanitize_text("a\tb\nc\rd") == "a\tb\nc\rd"

    def test_truncates_to_max_len(self):
        assert len(sanitize_text("x" * 50, max_len=10)) == 10

    def test_non_string_returns_empty(self):
        assert sanitize_text(123) == ""
        assert sanitize_text(None) == ""


# ============================================================ parse_str_param
class TestParseStrParam:
    def test_strips_and_returns(self):
        assert parse_str_param("q", default="", max_len=128, source={"q": "  hello  "}) == "hello"

    def test_truncates_over_max_len(self):
        assert parse_str_param("q", default="", max_len=3, source={"q": "abcdef"}) == "abc"

    def test_missing_uses_default(self):
        assert parse_str_param("q", default="X", source={}) == "X"

    def test_non_string_uses_default(self):
        assert parse_str_param("q", default="X", source={"q": 123}) == "X"

    def test_very_long_truncated(self):
        assert len(parse_str_param("q", default="", max_len=128, source={"q": "a" * 500})) == 128


# ============================================================ parse_int_param (通用钳位)
class TestParseIntParam:
    def test_above_hi_clamped(self):
        assert parse_int_param("x", default=0, lo=0, hi=10, source={"x": "15"}) == 10

    def test_below_lo_clamped(self):
        assert parse_int_param("x", default=0, lo=0, hi=10, source={"x": "-5"}) == 0

    def test_garbage_falls_back_to_default(self):
        assert parse_int_param("x", default=7, source={"x": "abc"}) == 7

    def test_missing_uses_default(self):
        assert parse_int_param("x", default=7, source={}) == 7

    def test_zero_clamped_to_positive_lo(self):
        assert parse_int_param("x", default=7, lo=1, source={"x": "0"}) == 1
