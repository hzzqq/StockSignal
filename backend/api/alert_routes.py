"""
backend/api/alert_routes.py
----------------------------
自选股价格预警 API（按当前登录用户隔离）。
"""
from __future__ import annotations
from flask import Blueprint, g, request
from sqlalchemy import select
from ..auth.decorators import jwt_required
from ..extensions import db
from ..models import PriceAlert
from ..utils.response import ok
from ..utils.errors import ValidationError, NotFoundError

bp = Blueprint("alert", __name__, url_prefix="/api")


@bp.get("/price-alerts")
@jwt_required
def list_alerts():
    """GET /api/price-alerts —— 返回当前用户全部预警（含已触发）。"""
    rows = db.session.execute(
        select(PriceAlert)
        .where(PriceAlert.user_id == g.current_user.id)
        .order_by(PriceAlert.created_at.desc())
    ).scalars()
    return ok(data=[r.to_dict() for r in rows])


@bp.post("/price-alerts")
@jwt_required
def create_alert():
    """POST /api/price-alerts
    body: {stock_code, stock_name?, condition: "above"|"below", target_price: float}
    """
    data = request.get_json(silent=True) or {}
    code = (data.get("stock_code") or "").strip()
    condition = (data.get("condition") or "above").strip().lower()
    try:
        target = float(data.get("target_price"))
    except (TypeError, ValueError):
        raise ValidationError("目标价格必须是数字")

    if not code:
        raise ValidationError("股票代码不能为空")
    if condition not in ("above", "below"):
        raise ValidationError("condition 只能是 above 或 below")
    if target <= 0:
        raise ValidationError("目标价格必须大于 0")

    name = (data.get("stock_name") or "").strip()
    alert = PriceAlert(
        user_id=g.current_user.id,
        stock_code=code,
        stock_name=name,
        condition=condition,
        target_price=target,
        active=True,
        triggered=False,
    )
    db.session.add(alert)
    db.session.commit()
    return ok(data=alert.to_dict(), message="预警创建成功", code="created")


@bp.put("/price-alerts/<int:alert_id>/toggle")
@jwt_required
def toggle_alert(alert_id: int):
    """PUT /api/price-alerts/5/toggle —— 启用/停用切换。"""
    alert = db.session.execute(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == g.current_user.id,
        )
    ).scalar_one_or_none()
    if not alert:
        raise NotFoundError("预警不存在")
    alert.active = not alert.active
    db.session.commit()
    return ok(data=alert.to_dict(), message="状态已更新")


@bp.delete("/price-alerts/<int:alert_id>")
@jwt_required
def delete_alert(alert_id: int):
    """DELETE /api/price-alerts/5 —— 仅删除本人预警。"""
    alert = db.session.execute(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == g.current_user.id,
        )
    ).scalar_one_or_none()
    if not alert:
        raise NotFoundError("预警不存在")
    db.session.delete(alert)
    db.session.commit()
    return ok(message="预警已删除")
