"""
tests/test_errors.py
===================
ApiError 体系的结构化错误契约单测（纯离线，无需服务/网络）。

覆盖：
- 每个错误类的 to_dict() 都含 'error' 键且 code 正确；
- to_response() 返回 Flask Response，状态码与错误匹配，响应体可被 JSON 序列化；
- 即使 message 是一个 Exception 实例，也能安全序列化（不崩溃）。
"""
from __future__ import annotations

import json
import os
import sys

import pytest
from flask import Flask

# 把项目根目录（含 backend 包）加入 path，确保 `from backend.utils.errors` 可导入
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.utils.errors import (  # noqa: E402
    ApiError,
    AuthError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)

# 每个错误类 -> (默认业务 code, 期望 HTTP 状态码)
EXPECTED = {
    ApiError: ("bad_request", 400),
    AuthError: ("unauthorized", 401),
    ForbiddenError: ("forbidden", 403),
    NotFoundError: ("not_found", 404),
    ValidationError: ("validation_error", 422),
    ConflictError: ("conflict", 409),
}


@pytest.fixture
def app_ctx():
    """jsonify 需要应用上下文，这里离线提供一个，不涉及任何服务/网络。"""
    app = Flask(__name__)
    with app.app_context():
        yield


def test_to_dict_has_error_key_and_code():
    for cls, (code, _status) in EXPECTED.items():
        err = cls("测试消息")
        d = err.to_dict()
        assert isinstance(d, dict)
        assert "error" in d
        assert d["error"] == cls.__name__
        assert d["code"] == code
        assert "message" in d


def test_to_response_status_and_json(app_ctx):
    for cls, (_code, status) in EXPECTED.items():
        err = cls("测试消息")
        resp = err.to_response()
        # 返回的是 Flask Response
        assert resp.status_code == status
        # 响应体是合法 JSON（可被反序列化）
        body = json.loads(resp.get_data(as_text=True))
        assert isinstance(body, dict)
        assert body["code"] == _code
        assert body["status"] == "error"
        assert "message" in body
        assert "data" in body


def test_message_as_exception_is_safe(app_ctx):
    """message 传入 Exception 实例时，to_dict / to_response 必须不崩溃且可序列化。"""
    exc = ValueError("boom")
    err = ApiError(message=exc)

    d = err.to_dict()
    # 异常被安全地转换为字符串，而非保留不可序列化对象
    assert isinstance(d["message"], str)
    assert "ValueError" in d["message"]

    resp = err.to_response()
    body = json.loads(resp.get_data(as_text=True))
    # 整包可被 JSON 序列化，不会抛异常
    json.dumps(body)
    assert resp.status_code == 400
