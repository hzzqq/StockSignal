"""
tests/test_response.py
======================
校验 backend.utils.response：
- ok/fail 的纯 payload 构造（无需 Flask 上下文）；
- paginate 统一分页信封与各种边界（越界/0/负/NaN/空序列）。
"""
from __future__ import annotations

import math

from backend.utils.response import _ok_payload, _fail_payload, paginate


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
