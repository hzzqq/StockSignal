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

设计调整（continue 迭代）：
- 把「构造 payload 字典」与「jsonify 包装」拆开，纯函数可单测（无需 Flask 上下文）；
- 新增 paginate() 统一分页信封，填补列表接口此前缺少标准分页能力的隐性缺口。
"""
from __future__ import annotations

import datetime
import decimal
import math
from typing import Any, Optional, Sequence

from flask import jsonify

try:  # numpy 在运行环境里通常可用，但允许缺省
    import numpy as np
except Exception:  # pragma: no cover - numpy 缺失时退化为纯 Python
    np = None


def _json_safe(obj: Any) -> Any:
    """递归地把常见「不可 JSON 序列化」类型转换为原生类型。

    作为响应构造的最后一道防线，保证 jsonify / 响应路径永不因
    datetime / Decimal / numpy 标量 / Exception 等而抛异常。
    任何无法识别的对象退化为 str(obj)，因此本函数自身也永不抛出。
    """
    # 原生可序列化类型直接透传
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    # 容器：递归净化
    if isinstance(obj, dict):
        return {_json_safe(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in obj]
    # 日期 / 时间
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    # Decimal
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    # numpy 标量 / 数组
    if np is not None:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return [_json_safe(v) for v in obj.tolist()]
    # 异常对象 -> 可读字符串
    if isinstance(obj, Exception):
        return f"{type(obj).__name__}: {obj}"
    # 兜底
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def _ok_payload(data: Any = None, message: Any = "success", code: str = "ok") -> dict:
    """构造成功响应的纯字典（可单测，不与 Flask 耦合）。"""
    return {"status": "ok", "code": code, "message": _json_safe(message), "data": _json_safe(data)}


def _fail_payload(message: Any = "error", code: str = "error", data: Any = None) -> dict:
    """构造失败响应的纯字典（可单测，不与 Flask 耦合）。"""
    return {"status": "error", "code": code, "message": _json_safe(message), "data": _json_safe(data)}


def error_from_exc(exc: BaseException, code: str = "error", data: Any = None) -> dict:
    """从异常构造一个「永不抛出」的错误体字典。

    即便 exc 本身是不可序列化对象也不会崩；用于 except 分支里
    安全地回传错误，避免二次异常覆盖原始错误。
    """
    try:
        msg = _json_safe(exc)
    except Exception:  # 理论上不会触发，双保险
        msg = f"{type(exc).__name__}: <unprintable>"
    return {"status": "error", "code": code, "message": msg, "data": _json_safe(data)}


def ok(data: Any = None, message: str = "success", code: str = "ok", http_status: int = 200):
    """成功响应。强制 content-type: application/json。"""
    resp = jsonify(_ok_payload(data, message, code))
    resp.status_code = http_status
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


def fail(message: str = "error", code: str = "error", http_status: int = 400, data: Any = None):
    """失败响应。"""
    resp = jsonify(_fail_payload(message, code, data))
    resp.status_code = http_status
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


def paginate(items: Sequence[Any], page: Any = 1, per_page: Any = 20, total: Optional[int] = None) -> dict:
    """把序列标准化为分页信封。

    入参 page / per_page 可能来自请求参数（字符串、缺失、0、负数、NaN），
    一律做安全收敛，绝不抛异常：
      - page 下限 1；per_page 下限 1、上限 100（防止一次拉爆内存）。
    返回：
      {items, page, per_page, total, pages, has_next, has_prev}
    """
    try:
        page = max(1, int(float(page)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(float(per_page))
    except (TypeError, ValueError):
        per_page = 20
    per_page = max(1, min(100, per_page))

    seq = list(items)
    if total is None:
        total = len(seq)
    total = max(0, int(total))

    pages = math.ceil(total / per_page) if per_page > 0 else 0
    # 越界页码收敛到有效范围
    if pages > 0 and page > pages:
        page = pages

    start = (page - 1) * per_page
    end = start + per_page
    page_items = seq[start:end]

    return {
        "items": page_items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }
