"""
backend/api/task_routes.py
--------------------------
后台任务 REST API：提交 / 查询 / 获取结果。
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import ok, fail
from ..utils.params import parse_int_param, parse_limit_param
from ..tasks.worker import task_worker

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


def _validate_task_payload(task_type: str, payload: Any) -> tuple[bool, Any]:
    """校验任务 payload 的顶层结构，拦截明显畸形的提交，避免进入 worker 线程后抛出未捕获异常。

    返回 (ok, payload_or_error):
      - ok=True  时，payload_or_error 为合法的 payload（dict，或 None 表示空负载）。
      - ok=False 时，payload_or_error 为错误描述字符串。

    已知任务类型可按需在此追加 required key 检查；当前各 handler 均使用
    payload.get(...) 并设置默认值，因此统一仅要求 payload 为对象或为空。
    """
    if payload is None:
        return True, None
    if not isinstance(payload, dict):
        return False, "payload 必须是对象"
    return True, payload


@bp.post("/")
@jwt_required
def create_task():
    """POST /api/tasks
    body: {"type": "analysis|compare|ai_consult|quant_research", "payload": {...}}
    """
    body = request.get_json(silent=True) or {}
    task_type = (body.get("type") or "").strip()
    payload = body.get("payload")

    if not task_type:
        return fail(message="缺少任务类型", code="missing_type", http_status=400)
    if task_type not in ("analysis", "compare", "ai_consult", "quant_research"):
        return fail(message=f"不支持的任务类型: {task_type}", code="unsupported_type", http_status=400)

    ok, payload_or_err = _validate_task_payload(task_type, payload)
    if not ok:
        return fail(message=payload_or_err, code="invalid_payload", http_status=400)
    # None 视为空负载，归一化为 dict 以匹配 worker.submit 的签名约定
    payload = payload_or_err if payload_or_err is not None else {}

    task_id = task_worker.submit(task_type, payload)
    return ok(data={"task_id": task_id, "status": "pending"}, message="任务已提交")


@bp.get("/<task_id>")
@jwt_required
def get_task(task_id: str):
    """GET /api/tasks/<task_id> 查询状态。"""
    task = task_worker.status(task_id)
    if not task:
        return fail(message="任务不存在", code="task_not_found", http_status=404)
    return ok(data=task, message="success")


@bp.get("/")
@jwt_required
def list_tasks():
    """GET /api/tasks?limit=50 列出最近任务。"""
    limit = parse_limit_param("limit", default=50, hi=200)
    tasks = task_worker.list_tasks(limit=limit)
    return ok(data=tasks, message="success")
