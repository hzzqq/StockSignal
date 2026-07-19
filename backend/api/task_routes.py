"""
backend/api/task_routes.py
--------------------------
后台任务 REST API：提交 / 查询 / 获取结果。
"""
from __future__ import annotations

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import ok, fail
from ..tasks.worker import task_worker

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


@bp.post("/")
@jwt_required
def create_task():
    """POST /api/tasks
    body: {"type": "analysis|compare|ai_consult|quant_research", "payload": {...}}
    """
    body = request.get_json(silent=True) or {}
    task_type = (body.get("type") or "").strip()
    payload = body.get("payload") or {}

    if not task_type:
        return fail(message="缺少任务类型", code="missing_type", http_status=400)
    if task_type not in ("analysis", "compare", "ai_consult", "quant_research"):
        return fail(message=f"不支持的任务类型: {task_type}", code="unsupported_type", http_status=400)

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
    limit = min(int(request.args.get("limit", "50")), 200)
    tasks = task_worker.list_tasks(limit=limit)
    return ok(data=tasks, message="success")
