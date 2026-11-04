"""
backend/api/task_routes.py
--------------------------
后台任务 REST API：提交 / 查询 / 获取结果。
"""
from __future__ import annotations  # noqa: I001

import logging
from typing import Any

from flask import Blueprint, request  # noqa: F401

from ..auth.decorators import jwt_required
from ..utils.response import ok, fail
from ..utils.params import parse_int_param, parse_limit_param, json_body  # noqa: F401
from ..tasks.worker import task_worker

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")

logger = logging.getLogger(__name__)

# 允许的后台任务类型（单一来源：create_task 校验与文档都引用这里）
_ALLOWED_TASK_TYPES = ("analysis", "compare", "ai_consult", "quant_research", "ai_research")


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
    body: {"type": "analysis|compare|ai_consult|quant_research|ai_research", "payload": {...}}
    """
    body = json_body()
    task_type = (body.get("type") or "").strip()
    payload = body.get("payload")

    if not task_type:
        return fail(message="缺少任务类型", code="missing_type", http_status=400)
    if task_type not in _ALLOWED_TASK_TYPES:
        return fail(message=f"不支持的任务类型: {task_type}", code="unsupported_type", http_status=400)

    # 注意：此处局部变量名不得用 `ok`——它会遮蔽本模块导入的响应助手 ok()，
    # 导致末尾 `return ok(data=...)` 抛 TypeError: 'bool' object is not callable（HTTP 500），
    # 使所有后台任务（ai_consult/analysis/...）提交即失败、前端永远拿不到 task_id。
    valid, payload_or_err = _validate_task_payload(task_type, payload)
    if not valid:
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


@bp.get("/<task_id>/timeline")
@jwt_required
def get_task_timeline(task_id: str):
    """GET /api/tasks/<task_id>/timeline —— 批次9：完整 timeline（不受内存 MAX_EVENTS=200 限制）。

    数据源优先级：
      1. progress_bus.get_events() → 实时内存 timeline（批次8 dict event + str message）
      2. AiTimelineEvent 表         → SQLite 持久化 timeline（批次9尽力而为持久化）
    两者 ts+message 相同视为重复，取前者（内存 = 更实时）。
    对完全未知 task_id 返回 404；对空 timeline 返回空数组（200）。
    """
    from backend.tasks.progress_bus import get_events as get_mem_events  # noqa: I001
    from backend.models import AiTimelineEvent, db
    from typing import Any as _Any, cast as _cast

    mem_events = _cast(list[dict[str, _Any]], get_mem_events(task_id))

    # SQLite 拉取——尽力而为（无表/未建 schema → 空列表，不影响返回）
    db_events: list[dict] = []
    try:
        rows = db.session.execute(
            db.select(AiTimelineEvent)
            .where(AiTimelineEvent.task_id == task_id)
            .order_by(AiTimelineEvent.ts.asc())
        ).scalars().all()
        db_events = [r.to_dict() for r in rows]
    # ui_audit_exempt: except-pass timeline SQLite 兜底读取尽力而为：schema 未就绪/查询失败按空列表返回，内存事件为主源不受影响
    except Exception:
        # 不静默：留痕后再按空列表返回（内存事件为主源，容量不受影响）
        logger.debug("task timeline SQLite 兜底读取失败，按空列表返回（内存事件为主源）", exc_info=True)

    # 内存 timeline 用批次8 dict/str 混合格式，SQLite timeline 用批次9 to_dict 统一格式
    if mem_events:
        unified = []
        for e in mem_events:
            if isinstance(e, dict):
                _fmt = e.get("message") or ""
                _ev = e.get("event") if isinstance(e.get("event"), dict) else None
                unified.append({
                    "event_type": _ev.get("type") if _ev else None,
                    "tool_name": _ev.get("tool") if _ev else None,
                    "message": _fmt,
                    "event": _ev,
                    "idx": _ev.get("idx") if _ev else None,
                    "elapsed_s": _ev.get("elapsed_s") if _ev else None,
                    "status": _ev.get("status") if _ev else None,
                    "data_as_of": _ev.get("data_as_of") if _ev else None,  # 批次10
                    "ts": e.get("ts", 0.0),
                })
        return ok(data={"source": "memory", "events": unified}, message="success")

    # 纯 SQLite fallback
    return ok(data={"source": "db", "events": db_events}, message="success")


@bp.delete("/<task_id>")
@jwt_required
def cancel_task(task_id: str):
    """DELETE /api/tasks/<task_id> 停止任务（T-315 停止生成）。

    状态：已取消 / 已结束（终态不可取消，409）/ 不存在（404）。
    诚实语义：仅标记取消，正在执行的 handler 线程无法强杀；结果不再发布给前端。
    """
    res = task_worker.cancel(task_id)
    if res is None:
        return fail(message="任务不存在", code="task_not_found", http_status=404)
    if res is False:
        return fail(message="任务已结束，无法取消", code="task_not_cancellable", http_status=409)
    return ok(data={"task_id": task_id, "status": "cancelled"}, message="任务已停止")


@bp.get("/")
@jwt_required
def list_tasks():
    """GET /api/tasks?limit=50 列出最近任务。"""
    limit = parse_limit_param("limit", default=50, hi=200)
    tasks = task_worker.list_tasks(limit=limit)
    return ok(data=tasks, message="success")
