"""
utils/response.py
-----------------
所有 HTTP 响应都走这里，强制 JSON 封装，杜绝 HTML 泄露。
统一字段：
    {
      "status": "ok" | "error",
      "code":   业务码（字符串）,
      "message": 人类可读提示（已脱敏）,
      "data":   业务数据（任意 JSON 类型，没有时为 null）
    }
"""
from __future__ import annotations
from typing import Any, Optional
from flask import jsonify


def ok(data: Any = None, message: str = "success", code: str = "ok", http_status: int = 200):
    """成功响应。强制 content-type: application/json。"""
    payload = {
        "status": "ok",
        "code": code,
        "message": message,
        "data": data,
    }
    resp = jsonify(payload)
    resp.status_code = http_status
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


def fail(message: str = "error", code: str = "error", http_status: int = 400, data: Optional[Any] = None):
    """失败响应。"""
    payload = {
        "status": "error",
        "code": code,
        "message": message,
        "data": data,
    }
    resp = jsonify(payload)
    resp.status_code = http_status
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp
