"""
自驱研究记录 API（H1+ 方向 B，T-213/T-216）
====================================
- GET  /api/research-runs       列表 + 总数（?limit=&offset=&status=&metric_key=）
- POST /api/research-runs/run   管理员手动触发一轮自驱研究（仿 market-alerts/scan）

数据由 ``backend.research_watch`` 定时自驱产出，``status`` 诚实透传
（ok/partial/unavailable，绝不粉饰）。citations / limitations 供前端点开溯源。
"""
from __future__ import annotations

import time

from flask import Blueprint, current_app, request
from sqlalchemy import select, func

from ..auth.decorators import jwt_required, admin_required
from ..extensions import db
from ..models import ResearchRun
from ..utils.response import ok
from ..utils.params import parse_int_param, parse_limit_param

bp = Blueprint("research_run", __name__, url_prefix="/api/research-runs")

_ALLOWED_STATUS = {"ok", "partial", "unavailable"}


@bp.get("")
@jwt_required
def list_runs():
    """GET /api/research-runs?limit=50&offset=0&status=ok&metric_key=adr"""
    limit = parse_limit_param("limit", default=50, hi=200)
    offset = parse_int_param("offset", default=0, lo=0)
    status = (request.args.get("status") or "").strip()
    metric_key = (request.args.get("metric_key") or "").strip()

    stmt = select(ResearchRun)
    count_stmt = select(func.count(ResearchRun.id))
    if status in _ALLOWED_STATUS:
        stmt = stmt.where(ResearchRun.status == status)
        count_stmt = count_stmt.where(ResearchRun.status == status)
    if metric_key:
        stmt = stmt.where(ResearchRun.trigger_metric_key == metric_key)
        count_stmt = count_stmt.where(ResearchRun.trigger_metric_key == metric_key)

    stmt = stmt.order_by(ResearchRun.created_at.desc()).limit(limit).offset(offset)
    rows = db.session.execute(stmt).scalars().all()
    total = db.session.execute(count_stmt).scalar() or 0

    return ok(data={
        "items": [r.to_dict() for r in rows],
        "total": total,
    })


@bp.post("/run")
@admin_required
def trigger_run():
    """POST /api/research-runs/run —— 管理员手动触发一轮自驱研究。

    语义（诚实优先）：
    - 无「未处理告警」→ ``ran=False`` 如实返回，不硬跑；
    - 有 → 同步跑一轮（管理员显式动作，绕过配额闸但同样落库/标记/通知），
      结果原样透传（unavailable 就是 unavailable）。
    """
    from .. import research_watch as rw

    app = current_app._get_current_object()
    alert = rw.latest_unprocessed_alert(app)
    if alert is None:
        return ok(data={"ran": False, "reason": "无未处理告警"},
                  message="没有需要研究的新告警")
    a = rw._norm_alert(alert)
    rec = rw.run_watch_once(alert=a, persist_fn=rw.persist_run)
    rw._mark_ran(time.time(), a.get("metric_key"))
    rw.notify_run(a, rec)
    return ok(
        data={
            "ran": True,
            "record": {
                "status": rec.get("status"),
                "question": rec.get("question"),
                "answer": rec.get("answer"),
                "citations": rec.get("citations"),
                "limitations": rec.get("limitations"),
            },
        },
        message=f"自驱研究完成（status={rec.get('status')}）",
    )
