"""
backend/api/config_routes.py
----------------------------
系统配置 + 自选股 API。
"""
from __future__ import annotations
from flask import Blueprint, g, request
from sqlalchemy import select, func
from ..auth.decorators import jwt_required, admin_required
from ..extensions import db
from ..models import SystemConfig, Watchlist, Stock
from ..utils.response import ok
from ..utils.errors import ValidationError, NotFoundError, ConflictError

bp = Blueprint("config", __name__, url_prefix="/api")


# ================================================================ 系统配置（admin）
@bp.get("/admin/config")
@admin_required
def list_config():
    """GET /api/admin/config"""
    rows = db.session.execute(
        select(SystemConfig).order_by(SystemConfig.key.asc())
    ).scalars()
    return ok(data=[r.to_dict() for r in rows])


@bp.put("/admin/config/<key>")
@admin_required
def update_config(key: str):
    """PUT /api/admin/config/cache_days  body: {value, description?}"""
    cfg = db.session.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    ).scalar_one_or_none()
    if not cfg:
        raise NotFoundError("资源不存在")

    data = request.get_json(silent=True) or {}
    if "value" in data:
        cfg.value = str(data["value"])
    if "description" in data:
        cfg.description = data["description"]
    cfg.updated_by = g.current_user.id
    db.session.commit()
    return ok(data=cfg.to_dict(), message="更新成功")


@bp.post("/admin/config")
@admin_required
def create_config():
    """POST /api/admin/config  body: {key, value, description?}"""
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    value = data.get("value", "")
    desc = data.get("description", "")
    if not key:
        raise ValidationError("配置键不能为空")

    exists = db.session.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    ).scalar_one_or_none()
    if exists:
        raise ConflictError("配置键已存在")

    cfg = SystemConfig(key=key, value=str(value), description=desc, updated_by=g.current_user.id)
    db.session.add(cfg)
    db.session.commit()
    return ok(data=cfg.to_dict(), message="创建成功", code="created")


@bp.delete("/admin/config/<key>")
@admin_required
def delete_config(key: str):
    """DELETE /api/admin/config/cache_days"""
    cfg = db.session.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    ).scalar_one_or_none()
    if not cfg:
        raise NotFoundError("资源不存在")
    db.session.delete(cfg)
    db.session.commit()
    return ok(message="删除成功")


# ================================================================ 自选股（所有用户）
@bp.get("/watchlist")
@jwt_required
def get_watchlist():
    """GET /api/watchlist"""
    rows = db.session.execute(
        select(Watchlist).where(Watchlist.user_id == g.current_user.id).order_by(Watchlist.created_at.desc())
    ).scalars()

    items = []
    for w in rows:
        stock = db.session.execute(
            select(Stock).where(Stock.code == w.stock_code)
        ).scalar_one_or_none()
        items.append({
            "id": w.id,
            "stock_code": w.stock_code,
            "stock_name": stock.name if stock else w.stock_code,
            "note": w.note,
            "created_at": w.created_at.isoformat() + "Z",
        })
    return ok(data=items)


@bp.post("/watchlist")
@jwt_required
def add_watchlist():
    """POST /api/watchlist  body: {stock_code, note?}"""
    data = request.get_json(silent=True) or {}
    code = (data.get("stock_code") or "").strip()
    note = data.get("note", "")
    if not code:
        raise ValidationError("股票代码不能为空")

    exists = db.session.execute(
        select(Watchlist).where(
            Watchlist.user_id == g.current_user.id,
            Watchlist.stock_code == code,
        )
    ).scalar_one_or_none()
    if exists:
        return ok(message="已在自选股中")

    w = Watchlist(user_id=g.current_user.id, stock_code=code, note=note)
    db.session.add(w)
    db.session.commit()
    return ok(data={"id": w.id, "stock_code": code}, message="添加成功", code="created")


@bp.delete("/watchlist/<int:item_id>")
@jwt_required
def remove_watchlist(item_id: int):
    """DELETE /api/watchlist/5"""
    w = db.session.execute(
        select(Watchlist).where(
            Watchlist.id == item_id,
            Watchlist.user_id == g.current_user.id,
        )
    ).scalar_one_or_none()
    if not w:
        raise NotFoundError("资源不存在")
    db.session.delete(w)
    db.session.commit()
    return ok(message="移除成功")


# ================================================================ 自选批量
@bp.post("/watchlist/batch")
@jwt_required
def add_watchlist_batch():
    """
    POST /api/watchlist/batch
    body: {"codes": ["600519","000001"], "note": "可选"}
    批量加自选；仅绑定当前用户，天然越权安全。
    响应 data: {added:[...], skipped:[...], failed:[{code,reason}]}
    """
    data = request.get_json(silent=True) or {}
    codes = data.get("codes")
    note = data.get("note", "")
    if not isinstance(codes, list) or not codes:
        raise ValidationError("codes 不能为空且须为数组")

    added, skipped, failed = [], [], []
    for raw in codes:
        code = (str(raw) if raw is not None else "").strip()
        if not code:
            failed.append({"code": str(raw), "reason": "股票代码不能为空"})
            continue
        exists = db.session.execute(
            select(Watchlist).where(
                Watchlist.user_id == g.current_user.id,
                Watchlist.stock_code == code,
            )
        ).scalar_one_or_none()
        if exists:
            skipped.append(code)
            continue
        w = Watchlist(user_id=g.current_user.id, stock_code=code, note=note)
        db.session.add(w)
        added.append(code)
    db.session.commit()
    return ok(data={"added": added, "skipped": skipped, "failed": failed}, message="批量添加完成")


@bp.delete("/watchlist/batch")
@jwt_required
def remove_watchlist_batch():
    """
    DELETE /api/watchlist/batch
    body: {"ids": [1,2,3]} 优先；或 {"codes": ["600519",...]}
    严格越权：归属他人项进 forbidden 绝不删除；不存在进 not_found。
    响应 data: {deleted:[...], forbidden:[{code,reason}], not_found:[...]}
    """
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    codes = data.get("codes")
    if not isinstance(ids, list) and not isinstance(codes, list):
        raise ValidationError("ids 或 codes 至少提供一个数组")

    deleted, forbidden, not_found = [], [], []

    def _classify_by_id(item_id) -> None:
        own = db.session.execute(
            select(Watchlist).where(
                Watchlist.id == item_id,
                Watchlist.user_id == g.current_user.id,
            )
        ).scalar_one_or_none()
        if own is not None:
            deleted.append(own.stock_code)
            db.session.delete(own)
            return
        # 查是否存在的他人项，以区分 forbidden / not_found
        other = db.session.execute(
            select(Watchlist).where(Watchlist.id == item_id)
        ).scalar_one_or_none()
        if other is not None:
            forbidden.append({"code": other.stock_code, "reason": "无权限访问"})
        else:
            not_found.append(str(item_id))

    def _classify_by_code(code) -> None:
        own = db.session.execute(
            select(Watchlist).where(
                Watchlist.user_id == g.current_user.id,
                Watchlist.stock_code == code,
            )
        ).scalar_one_or_none()
        if own is not None:
            deleted.append(code)
            db.session.delete(own)
            return
        other = db.session.execute(
            select(Watchlist).where(Watchlist.stock_code == code)
        ).scalar_one_or_none()
        if other is not None:
            forbidden.append({"code": code, "reason": "无权限访问"})
        else:
            not_found.append(code)

    if isinstance(ids, list) and ids:
        for item_id in ids:
            try:
                _classify_by_id(int(item_id))
            except (TypeError, ValueError):
                not_found.append(str(item_id))
    elif isinstance(codes, list) and codes:
        for raw in codes:
            code = (str(raw) if raw is not None else "").strip()
            if not code:
                continue
            _classify_by_code(code)

    db.session.commit()
    return ok(
        data={"deleted": deleted, "forbidden": forbidden, "not_found": not_found},
        message="批量删除完成",
    )
