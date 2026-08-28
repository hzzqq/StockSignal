"""
backend/api/order_routes.py
---------------------------
实盘交易 + 智能条件单 API。

账户：
  GET  /api/trade/account          查询（无则自动创建默认模拟账户）
  PUT  /api/trade/account          更新券商配置 / live 开关 / 风控参数
  POST /api/trade/account/health   券商通道健康检查
持仓与订单：
  GET  /api/trade/positions        持仓列表
  GET  /api/trade/orders           订单流水（最近 200 条）
  POST /api/trade/orders           手动下单 {stock_code, stock_name, side, quantity, price?}
条件单：
  GET    /api/cond-orders          列表
  POST   /api/cond-orders          新建
  PUT    /api/cond-orders/<id>     启停 {active}
  DELETE /api/cond-orders/<id>     删除
  POST   /api/cond-orders/scan     手动触发一轮扫描（当前用户视角，走全局扫描）
"""
from __future__ import annotations

import json
import re

from flask import Blueprint, current_app, g, request
import logging

from ..auth.decorators import jwt_required
from ..extensions import db
from ..models import ConditionalOrder, RealAccount, RealOrder, RealPosition
from ..utils.params import validate_stock_code
from ..utils.response import fail, ok

bp = Blueprint("trade", __name__, url_prefix="/api")

logger = logging.getLogger(__name__)

_BROKER_TYPES = ("sim", "qmt", "easytrader")
_TRIGGER_TYPES = ("margin_stock", "margin_market", "ma5_break_up", "ma5_break_down")


def _get_or_create_account(user_id: int) -> RealAccount:
    acc = RealAccount.query.filter_by(user_id=user_id).first()
    if acc is None:
        acc = RealAccount(user_id=user_id)
        db.session.add(acc)
        db.session.commit()
    return acc


# ================================================================== 账户
@bp.get("/trade/account")
@jwt_required
def trade_account():
    acc = _get_or_create_account(g.current_user.id)
    return ok(data=acc.to_dict(), message="success")


@bp.put("/trade/account")
@jwt_required
def trade_account_update():
    data = request.get_json(silent=True) or {}
    acc = _get_or_create_account(g.current_user.id)

    if "broker_type" in data:
        bt = str(data.get("broker_type") or "sim").strip().lower()
        if bt not in _BROKER_TYPES:
            return fail(message="不支持的券商类型", code="invalid_param", http_status=400)
        acc.broker_type = bt
    if "broker_config" in data:
        cfg = data.get("broker_config")
        if cfg is not None and not isinstance(cfg, dict):
            return fail(message="broker_config 须为对象", code="invalid_param", http_status=400)
        # 保留旧密码：前端传 ****** 时不覆盖
        old = acc.config_dict()
        merged = dict(cfg or {})
        for k, v in list(merged.items()):
            if isinstance(v, str) and v.strip("*") == "" and v and k in old:
                merged[k] = old[k]
        acc.broker_config = json.dumps(merged, ensure_ascii=False)
    if "live_mode" in data:
        live = bool(data.get("live_mode"))
        if live and acc.broker_type == "sim":
            return fail(message="模拟账本无需开启实盘模式；请先选择并配置真实券商通道",
                        code="invalid_param", http_status=400)
        acc.live_mode = live
    if "max_order_amount" in data:
        try:
            v = float(data["max_order_amount"])
            if v <= 0:
                raise ValueError
            acc.max_order_amount = v
        except (TypeError, ValueError):
            return fail(message="单笔金额上限须为正数", code="invalid_param", http_status=400)
    if "daily_loss_limit" in data:
        try:
            v = float(data["daily_loss_limit"])
            if v <= 0:
                raise ValueError
            acc.daily_loss_limit = v
        except (TypeError, ValueError):
            return fail(message="当日亏损停手线须为正数", code="invalid_param", http_status=400)
    if data.get("clear_risk_pause"):
        acc.risk_paused_date = None

    db.session.commit()
    return ok(data=acc.to_dict(), message="账户已更新")


@bp.post("/trade/account/health")
@jwt_required
def trade_account_health():
    from ..broker import BrokerUnavailable, get_broker
    acc = _get_or_create_account(g.current_user.id)
    try:
        broker = get_broker(acc, db.session)
        return ok(data=broker.health_check(), message="success")
    except BrokerUnavailable as e:
        logger.warning("券商健康检查不可用: %s", e)
        return fail(message="券商服务暂时不可用，请稍后重试", code="broker_unavailable", http_status=503)
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)


# ================================================================== 持仓 / 订单
@bp.get("/trade/positions")
@jwt_required
def trade_positions():
    rows = (RealPosition.query.filter_by(user_id=g.current_user.id)
            .order_by(RealPosition.updated_at.desc()).all())
    return ok(data=[r.to_dict() for r in rows], message="success")


@bp.get("/trade/orders")
@jwt_required
def trade_orders():
    rows = (RealOrder.query.filter_by(user_id=g.current_user.id)
            .order_by(RealOrder.created_at.desc()).limit(200).all())
    return ok(data=[r.to_dict() for r in rows], message="success")


@bp.post("/trade/orders")
@jwt_required
def trade_place_order():
    from ..broker import execute_order
    data = request.get_json(silent=True) or {}
    code = (str(data.get("stock_code") or "")).strip()
    name = (str(data.get("stock_name") or "")).strip()
    side = (str(data.get("side") or "")).strip().lower()
    try:
        quantity = int(data.get("quantity") or 0)
    except (TypeError, ValueError):
        return fail(message="数量无效", code="invalid_param", http_status=400)
    price = data.get("price")
    try:
        price = float(price) if price not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return fail(message="价格无效", code="invalid_param", http_status=400)

    if not validate_stock_code(code)[0]:
        return fail(message="股票代码须为 6 位数字", code="invalid_param", http_status=400)
    if side not in ("buy", "sell"):
        return fail(message="方向须为 buy/sell", code="invalid_param", http_status=400)
    if quantity <= 0 or quantity % 100 != 0:
        return fail(message="数量须为 100 的整数倍", code="invalid_param", http_status=400)

    acc = _get_or_create_account(g.current_user.id)
    order, result = execute_order(acc, db.session, code=code, name=name,
                                  side=side, quantity=quantity, price=price,
                                  source="manual")
    db.session.commit()
    if result.ok:
        return ok(data=order.to_dict(), message=result.message or "下单成功")
    return fail(message=result.message or "下单未成功", code="order_failed", http_status=400)


# ================================================================== 条件单
@bp.get("/cond-orders")
@jwt_required
def cond_list():
    rows = (ConditionalOrder.query.filter_by(user_id=g.current_user.id)
            .order_by(ConditionalOrder.created_at.desc()).limit(200).all())
    return ok(data=[r.to_dict() for r in rows], message="success")


@bp.post("/cond-orders")
@jwt_required
def cond_create():
    data = request.get_json(silent=True) or {}
    code = (str(data.get("stock_code") or "")).strip()
    name = (str(data.get("stock_name") or "")).strip()
    trigger_type = (str(data.get("trigger_type") or "")).strip()
    action = (str(data.get("action") or "buy")).strip().lower()
    params = data.get("trigger_params") or {}
    expire_date = (str(data.get("expire_date") or "")).strip() or None
    try:
        quantity = int(data.get("quantity") or 0)
    except (TypeError, ValueError):
        return fail(message="数量无效", code="invalid_param", http_status=400)

    if trigger_type not in _TRIGGER_TYPES:
        return fail(message="不支持的触发类型", code="invalid_param", http_status=400)
    if not validate_stock_code(code)[0]:
        return fail(message="股票代码须为 6 位数字", code="invalid_param", http_status=400)
    if action not in ("buy", "sell"):
        return fail(message="动作须为 buy/sell", code="invalid_param", http_status=400)
    if quantity <= 0 or quantity % 100 != 0:
        return fail(message="数量须为 100 的整数倍", code="invalid_param", http_status=400)
    if not isinstance(params, dict):
        return fail(message="trigger_params 须为对象", code="invalid_param", http_status=400)
    if trigger_type in ("margin_stock", "margin_market"):
        try:
            th = float(params.get("threshold") or 0)
            if th <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return fail(message="阈值须为正数", code="invalid_param", http_status=400)
    if expire_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", expire_date):
        return fail(message="到期日格式须为 YYYY-MM-DD", code="invalid_param", http_status=400)

    # 每用户 pending 条件单上限，防滥用
    pending_cnt = ConditionalOrder.query.filter_by(
        user_id=g.current_user.id, status="pending").count()
    if pending_cnt >= 50:
        return fail(message="待触发条件单已达上限（50 条）", code="limit_exceeded", http_status=400)

    co = ConditionalOrder(
        user_id=g.current_user.id, stock_code=code, stock_name=name,
        trigger_type=trigger_type,
        trigger_params=json.dumps(params, ensure_ascii=False),
        action=action, quantity=quantity, expire_date=expire_date)
    db.session.add(co)
    db.session.commit()
    return ok(data=co.to_dict(), message="条件单已创建")


@bp.put("/cond-orders/<int:oid>")
@jwt_required
def cond_toggle(oid: int):
    co = ConditionalOrder.query.filter_by(id=oid, user_id=g.current_user.id).first()
    if co is None:
        return fail(message="条件单不存在", code="not_found", http_status=404)
    data = request.get_json(silent=True) or {}
    if "active" in data:
        if co.status != "pending":
            return fail(message="仅待触发状态可启停", code="invalid_state", http_status=400)
        co.active = bool(data["active"])
    db.session.commit()
    return ok(data=co.to_dict(), message="已更新")


@bp.delete("/cond-orders/<int:oid>")
@jwt_required
def cond_delete(oid: int):
    co = ConditionalOrder.query.filter_by(id=oid, user_id=g.current_user.id).first()
    if co is None:
        return fail(message="条件单不存在", code="not_found", http_status=404)
    db.session.delete(co)
    db.session.commit()
    return ok(data={"deleted": oid}, message="已删除")


@bp.post("/cond-orders/scan")
@jwt_required
def cond_scan_now():
    """手动触发一轮扫描（全局扫描，返回统计）。"""
    from ..conditional_engine import scan_and_execute
    try:
        stats = scan_and_execute(current_app._get_current_object())
        return ok(data=stats, message="扫描完成")
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)
