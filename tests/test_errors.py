"""
tests/test_errors.py
===================
校验 backend.utils.errors 业务异常体系：
- 各子类默认 HTTP 状态码正确；
- to_dict 完整（含 status）；
- to_response 产出标准 JSON 错误信封且状态码正确（单一可信源）。
"""
from __future__ import annotations

from flask import Flask

from backend.utils.errors import (
    ApiError,
    AuthError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
    ConflictError,
)


def test_status_hierarchy():
    assert ApiError("x").status == 400
    assert AuthError().status == 401
    assert ForbiddenError().status == 403
    assert NotFoundError().status == 404
    assert ValidationError().status == 422
    assert ConflictError().status == 409


def test_to_dict_includes_status():
    e = NotFoundError("missing")
    d = e.to_dict()
    assert d == {"message": "missing", "code": "not_found", "status": 404}


def test_to_response_envelope():
    app = Flask(__name__)
    with app.app_context():
        resp = NotFoundError("missing").to_response()
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["code"] == "not_found"
    assert body["message"] == "missing"


def test_to_response_preserves_code_and_status():
    app = Flask(__name__)
    with app.app_context():
        resp = ValidationError("bad").to_response()
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["code"] == "validation_error"
    assert body["message"] == "bad"
