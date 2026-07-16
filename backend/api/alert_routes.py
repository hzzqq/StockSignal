"""
backend/api/alert_routes.py
----------------------------
自选股预警 API（按当前登录用户隔离）。支持价格 / 技术形态 / 成交量异动 / 公告 四类预警。
"""
from __future__ import annotations
import json
from flask import Blueprint, g, request
from sqlalchemy import select
from ..auth.decorators import jwt_required
from ..extensions import db
from ..models import PriceAlert
from ..utils.response import ok
from ..utils.errors import ValidationError, NotFoundError

ALERT_TYPES = ("price", "pattern", "volume", "announcement")

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
    body: {
      stock_code, stock_name?,
      alert_type: "price"|"pattern"|"volume"|"announcement",
      condition?: "above"|"below", target_price?: float,   # price 用
      params?: {pattern_name?, volume_ratio?, keyword?}     # 其余类型用
    }
    """
    data = request.get_json(silent=True) or {}
    code = (data.get("stock_code") or "").strip()
    alert_type = (data.get("alert_type") or "price").strip().lower()
    raw_params = data.get("params") or {}

    if not code:
        raise ValidationError("股票代码不能为空")
    if alert_type not in ALERT_TYPES:
        raise ValidationError("alert_type 只能是 price/pattern/volume/announcement")

    name = (data.get("stock_name") or "").strip()
    condition = (data.get("condition") or "above").strip().lower()
    target = 0.0
    params_json = None

    if alert_type == "price":
        try:
            target = float(data.get("target_price"))
        except (TypeError, ValueError):
            raise ValidationError("目标价格必须是数字")
        if condition not in ("above", "below"):
            raise ValidationError("condition 只能是 above 或 below")
        if target <= 0:
            raise ValidationError("目标价格必须大于 0")
    elif alert_type == "pattern":
        pname = (raw_params.get("pattern_name") or "").strip() if isinstance(raw_params, dict) else ""
        if not pname:
            raise ValidationError("形态预警需指定 pattern_name")
        params_json = json.dumps({"pattern_name": pname}, ensure_ascii=False)
    elif alert_type == "volume":
        try:
            vr = float(raw_params.get("volume_ratio"))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError("成交量异动预警需指定 volume_ratio（数字）")
        if vr <= 0:
            raise ValidationError("volume_ratio 必须大于 0")
        params_json = json.dumps({"volume_ratio": vr}, ensure_ascii=False)
    elif alert_type == "announcement":
        kw = (raw_params.get("keyword") or "").strip() if isinstance(raw_params, dict) else ""
        if not kw:
            raise ValidationError("公告预警需指定 keyword")
        params_json = json.dumps({"keyword": kw}, ensure_ascii=False)

    alert = PriceAlert(
        user_id=g.current_user.id,
        stock_code=code,
        stock_name=name,
        alert_type=alert_type,
        condition=condition,
        target_price=target,
        params=params_json,
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
