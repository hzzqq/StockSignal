"""
tests/test_response.py
======================
校验 backend.utils.response：
- ok/fail 的纯 payload 构造（无需 Flask 上下文）；
- paginate 统一分页信封与各种边界（越界/0/负/NaN/空序列）。
"""
from __future__ import annotations

import datetime
import decimal
import json
import math

import pytest

from backend.utils.response import (
    _json_safe,
    _ok_payload,
    _fail_payload,
    error_from_exc,
    paginate,
)

try:  # numpy 为可选依赖：缺失时仅跳过涉及 numpy 的用例
    import numpy as np
except Exception:  # pragma: no cover
    np = None

needs_np = pytest.mark.skipif(np is None, reason="numpy 不可用")


def test_ok_payload_shape():
    p = _ok_payload(data={"a": 1}, message="ok", code="ok")
    assert p == {"status": "ok", "code": "ok", "message": "ok", "data": {"a": 1}}


def test_fail_payload_shape():
    p = _fail_payload(message="boom", code="err")
    assert p["status"] == "error"
    assert p["code"] == "err"
    assert p["message"] == "boom"
    assert p["data"] is None


def test_paginate_basic():
    items = list(range(25))
    r = paginate(items, page=1, per_page=10)
    assert r["items"] == list(range(10))
    assert r["page"] == 1
    assert r["per_page"] == 10
    assert r["total"] == 25
    assert r["pages"] == 3
    assert r["has_next"] is True
    assert r["has_prev"] is False


def test_paginate_last_page_partial():
    items = list(range(25))
    r = paginate(items, page=3, per_page=10)
    assert r["items"] == [20, 21, 22, 23, 24]
    assert r["has_next"] is False
    assert r["has_prev"] is True


def test_paginate_page_overflow_clamped():
    items = list(range(25))
    r = paginate(items, page=99, per_page=10)
    assert r["page"] == 3  # 收敛到最后一页
    assert r["items"] == [20, 21, 22, 23, 24]


def test_paginate_negative_and_zero_clamped():
    items = list(range(5))
    assert paginate(items, page=-3, per_page=10)["page"] == 1
    assert paginate(items, page=0, per_page=0)["per_page"] == 1
    assert paginate(items, page=1, per_page=1000)["per_page"] == 100  # 上限 100


def test_paginate_string_and_nan_inputs():
    items = list(range(20))
    # 来自请求参数的字符串
    assert paginate(items, page="2", per_page="5")["page"] == 2
    # NaN / None 安全收敛
    assert paginate(items, page=float("nan"), per_page=None)["page"] == 1
    assert paginate(items, page="abc", per_page="x")["page"] == 1


def test_paginate_empty():
    r = paginate([], page=1, per_page=10)
    assert r["items"] == []
    assert r["total"] == 0
    assert r["pages"] == 0
    assert r["has_next"] is False


def test_paginate_explicit_total():
    items = list(range(5))
    r = paginate(items, page=1, per_page=2, total=100)
    assert r["total"] == 100
    assert r["pages"] == 50
    assert r["has_next"] is True


# ---------------------------------------------------------------------------
# 响应体硬化：保证错误/成功响应永远是结构化、可 JSON 序列化的 dict，
# 即便输入里混入了 datetime / Decimal / numpy 标量 / Exception 也不崩。
# ---------------------------------------------------------------------------

def _is_dict_and_jsonable(payload) -> None:
    """断言：结果是 dict，且可被 json.dumps 序列化（捕获未处理异常）。"""
    assert isinstance(payload, dict)
    try:
        json.dumps(payload)
    except (TypeError, ValueError) as exc:  # 助手本应已缓解此情况
        pytest.fail(f"响应体仍不可 JSON 序列化: {exc}")


def test_json_safe_primitives_passthrough():
    assert _json_safe(None) is None
    assert _json_safe("x") == "x"
    assert _json_safe(3) == 3
    assert _json_safe(2.5) == 2.5
    assert _json_safe(True) is True


def test_json_safe_recursive_containers():
    dirty = {
        "ts": datetime.datetime(2024, 1, 2, 3, 4, 5),
        "day": datetime.date(2024, 1, 2),
        "amount": decimal.Decimal("12.34"),
        "nested": {"when": datetime.datetime(2023, 5, 6)},
    }
    clean = _json_safe(dirty)
    assert isinstance(clean, dict)
    assert clean["ts"] == "2024-01-02T03:04:05"
    assert clean["day"] == "2024-01-02"
    assert clean["amount"] == 12.34
    assert clean["nested"]["when"] == "2023-05-06T00:00:00"
    json.dumps(clean)  # 必须可序列化


@needs_np
def test_json_safe_numpy_scalars():
    assert _json_safe(np.int64(7)) == 7
    assert _json_safe(np.float64(1.5)) == 1.5
    assert _json_safe(np.bool_(True)) is True
    arr = _json_safe(np.array([np.int64(1), np.float64(2.0)]))
    assert arr == [1, 2.0]
    json.dumps(arr)


def test_ok_payload_with_nonserializable_data():
    # success 路径混入不可序列化数据，必须被静默净化
    payload = _ok_payload(
        data={
            "when": datetime.datetime(2024, 1, 1),
            "price": decimal.Decimal("99.99"),
            "exc": ValueError("boom"),
        }
    )
    _is_dict_and_jsonable(payload)
    # 成功指示器：status == "ok"
    assert payload["status"] == "ok"
    assert payload["data"]["when"] == "2024-01-01T00:00:00"
    assert payload["data"]["price"] == 99.99
    assert "ValueError" in payload["data"]["exc"]


def test_fail_payload_with_exception_message():
    # 把 Exception 直接当作 message 传入，也必须安全
    payload = _fail_payload(message=RuntimeError("kaboom"), code="E_TEST")
    _is_dict_and_jsonable(payload)
    # 错误指示器：status == "error"（本模块约定，等价于 'error' 键）
    assert payload["status"] == "error"
    assert "message" in payload
    assert "RuntimeError" in payload["message"]


def test_error_from_exc_never_raises():
    payload = error_from_exc(ValueError("bad input"), code="E_VAL")
    _is_dict_and_jsonable(payload)
    assert payload["status"] == "error"
    assert payload["code"] == "E_VAL"
    assert "ValueError" in payload["message"]

    # 即便 data 里也混入异常 / numpy 也绝不抛
    payload2 = error_from_exc(KeyError("missing"), data={"e": RuntimeError("x")})
    _is_dict_and_jsonable(payload2)
    assert "KeyError" in payload2["message"]


def test_helper_mitigates_raw_non_serializable():
    # 证明：原始数据本身确实会令 json 失败，而助手已缓解
    with pytest.raises(TypeError):
        json.dumps({"x": datetime.datetime(2024, 1, 1)})
    assert json.dumps(_json_safe({"x": datetime.datetime(2024, 1, 1)}))  # 已净化
