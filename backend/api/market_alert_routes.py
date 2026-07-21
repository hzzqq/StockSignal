"""
市场指标异动提醒 API（全局告警，按用户维度记录已读）
===================================================
- GET    /api/market-alerts               列表 + 未读数（?limit=&offset=&unread_only=1）
- POST   /api/market-alerts/<id>/read     标记单条已读
- POST   /api/market-alerts/read-all      全部标记为已读
- POST   /api/market-alerts/scan          管理员手动触发一次扫描（不受交易时段限制）

未读判定：User.settings.last_seen_market_alert 之后的告警即未读。
"""
from __future__ import annotations

import json
from datetime import datetime

from flask import Blueprint, g, request
from sqlalchemy import select, func

from ..auth.decorators import jwt_required, admin_required
from ..extensions import db
from ..models import MarketAlert
from ..utils.response import ok
from ..utils.errors import NotFoundError

bp = Blueprint("market_alert", __name__, url_prefix="/api/market-alerts")


def _parse_last_seen(user) -> datetime | None:
    raw = getattr(user, "settings", None) or ""
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    ts = d.get("last_seen_market_alert")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", ""))
    except Exception:
        return None


def _set_last_seen(user, dt: datetime) -> None:
    raw = getattr(user, "settings", None) or ""
    try:
        d = json.loads(raw) if raw else {}
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    d["last_seen_market_alert"] = dt.isoformat() + "Z"
    user.settings = json.dumps(d, ensure_ascii=False)
    db.session.commit()


@bp.get("")
@jwt_required
def list_alerts():
    """GET /api/market-alerts?limit=50&offset=0&unread_only=1"""
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
        unread_only = request.args.get("unread_only") == "1"
    except Exception:
        limit, offset = 50, 0
        unread_only = False

    last_seen = _parse_last_seen(g.current_user)

    stmt = select(MarketAlert)
    if unread_only and last_seen is not None:
        stmt = stmt.where(MarketAlert.created_at > last_seen)
    stmt = stmt.order_by(MarketAlert.created_at.desc()).limit(limit).offset(offset)
    rows = db.session.execute(stmt).scalars().all()

    if last_seen is not None:
        unread_filter = MarketAlert.created_at > last_seen
    else:
        unread_filter = MarketAlert.id.isnot(None)
    unread_count = db.session.execute(
        select(func.count(MarketAlert.id)).where(unread_filter)
    ).scalar() or 0
    total = db.session.execute(select(func.count(MarketAlert.id))).scalar() or 0

    return ok(data={
        "items": [r.to_dict() for r in rows],
        "unread_count": unread_count,
        "total": total,
        "last_seen": last_seen.isoformat() + "Z" if last_seen else None,
    })


@bp.post("/<int:alert_id>/read")
@jwt_required
def mark_read(alert_id: int):
    """POST /api/market-alerts/5/read —— 单条已读（推进该用户 last_seen 到该告警时间）。"""
    a = db.session.get(MarketAlert, alert_id)
    if not a:
        raise NotFoundError("告警不存在")
    last_seen = _parse_last_seen(g.current_user) or datetime.min
    if a.created_at and a.created_at > last_seen:
        _set_last_seen(g.current_user, a.created_at)
    return ok(message="已标记为已读")


@bp.post("/read-all")
@jwt_required
def mark_all():
    """POST /api/market-alerts/read-all —— 全部已读。"""
    _set_last_seen(g.current_user, datetime.utcnow())
    return ok(message="已全部标记为已读")


@bp.post("/scan")
@admin_required
def trigger_scan():
    """POST /api/market-alerts/scan —— 管理员手动触发一次扫描。"""
    from ..market_alert_engine import scan_and_store

    n = scan_and_store()
    return ok(data={"inserted": n}, message=f"扫描完成，新增 {n} 条")
