"""
backend/api/stock_tag_routes.py
-----------------------------
股票标签 API：垃圾股 + 用户自定义打分。
- /api/junk-stocks
- /api/user-scores
"""
from __future__ import annotations
from flask import Blueprint, g, request
from sqlalchemy import select
from ..auth.decorators import jwt_required
from ..extensions import db
from ..models import JunkStock, UserStockScore, Stock
from ..utils.response import ok
from ..utils.errors import ValidationError, NotFoundError

bp = Blueprint("stock_tags", __name__, url_prefix="/api")


# ================================================================ 垃圾股
@bp.get("/junk-stocks")
@jwt_required
def get_junk_stocks():
    """GET /api/junk-stocks"""
    rows = db.session.execute(
        select(JunkStock).where(JunkStock.user_id == g.current_user.id).order_by(JunkStock.created_at.desc())
    ).scalars()
    items = []
    for j in rows:
        stock = db.session.execute(select(Stock).where(Stock.code == j.stock_code)).scalar_one_or_none()
        items.append({
            "id": j.id,
            "stock_code": j.stock_code,
            "stock_name": stock.name if stock else j.stock_code,
            "note": j.note,
            "created_at": j.created_at.isoformat() + "Z",
        })
    return ok(data=items)


@bp.post("/junk-stocks")
@jwt_required
def add_junk_stock():
    """POST /api/junk-stocks  body: {stock_code, note?}"""
    data = request.get_json(silent=True) or {}
    code = (data.get("stock_code") or "").strip()
    note = data.get("note", "")
    if not code:
        raise ValidationError("股票代码不能为空")

    exists = db.session.execute(
        select(JunkStock).where(
            JunkStock.user_id == g.current_user.id,
            JunkStock.stock_code == code,
        )
    ).scalar_one_or_none()
    if exists:
        return ok(message="已在垃圾股中")

    j = JunkStock(user_id=g.current_user.id, stock_code=code, note=note)
    db.session.add(j)
    db.session.commit()
    return ok(data={"id": j.id, "stock_code": code}, message="添加成功", code="created")


@bp.delete("/junk-stocks/<int:item_id>")
@jwt_required
def remove_junk_stock(item_id: int):
    """DELETE /api/junk-stocks/5"""
    j = db.session.execute(
        select(JunkStock).where(
            JunkStock.id == item_id,
            JunkStock.user_id == g.current_user.id,
        )
    ).scalar_one_or_none()
    if not j:
        raise NotFoundError("资源不存在")
    db.session.delete(j)
    db.session.commit()
    return ok(message="移除成功")


@bp.delete("/junk-stocks/batch")
@jwt_required
def remove_junk_stocks_batch():
    """DELETE /api/junk-stocks/batch  body: {ids:[1,2,3]}"""
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        raise ValidationError("ids 不能为空且须为数组")
    deleted = []
    for item_id in ids:
        j = db.session.execute(
            select(JunkStock).where(
                JunkStock.id == item_id,
                JunkStock.user_id == g.current_user.id,
            )
        ).scalar_one_or_none()
        if j:
            db.session.delete(j)
            deleted.append(item_id)
    db.session.commit()
    return ok(data={"deleted": deleted}, message="批量移除成功")


# ================================================================ 用户打分
@bp.get("/user-scores")
@jwt_required
def get_user_scores():
    """GET /api/user-scores"""
    rows = db.session.execute(
        select(UserStockScore).where(UserStockScore.user_id == g.current_user.id)
    ).scalars()
    return ok(data=[r.to_dict() for r in rows])


@bp.get("/user-scores/<stock_code>")
@jwt_required
def get_user_score(stock_code: str):
    """GET /api/user-scores/600519"""
    code = stock_code.strip()
    row = db.session.execute(
        select(UserStockScore).where(
            UserStockScore.user_id == g.current_user.id,
            UserStockScore.stock_code == code,
        )
    ).scalar_one_or_none()
    if not row:
        return ok(data=None)
    return ok(data=row.to_dict())


@bp.post("/user-scores")
@jwt_required
def upsert_user_score():
    """POST /api/user-scores  body: {stock_code, stock_name?, score}"""
    data = request.get_json(silent=True) or {}
    code = (data.get("stock_code") or "").strip()
    name = (data.get("stock_name") or "").strip()
    score = data.get("score")
    if not code:
        raise ValidationError("股票代码不能为空")
    try:
        score = int(score)
    except Exception:
        raise ValidationError("分数须为整数")
    if score < 0 or score > 100:
        raise ValidationError("分数须在 0–100 之间")

    row = db.session.execute(
        select(UserStockScore).where(
            UserStockScore.user_id == g.current_user.id,
            UserStockScore.stock_code == code,
        )
    ).scalar_one_or_none()
    if row:
        row.score = score
        if name:
            row.stock_name = name
    else:
        row = UserStockScore(
            user_id=g.current_user.id,
            stock_code=code,
            stock_name=name or code,
            score=score,
        )
        db.session.add(row)
    db.session.commit()
    return ok(data=row.to_dict(), message="评分已保存")


@bp.delete("/user-scores/<stock_code>")
@jwt_required
def delete_user_score(stock_code: str):
    """DELETE /api/user-scores/600519"""
    code = stock_code.strip()
    row = db.session.execute(
        select(UserStockScore).where(
            UserStockScore.user_id == g.current_user.id,
            UserStockScore.stock_code == code,
        )
    ).scalar_one_or_none()
    if row:
        db.session.delete(row)
        db.session.commit()
    return ok(message="评分已删除")
