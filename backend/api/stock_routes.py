"""
backend/api/stock_routes.py
---------------------------
股票搜索 + 股票管理 API。
"""
from __future__ import annotations
from flask import Blueprint, request
from sqlalchemy import select, func
from ..extensions import db
from ..models import Stock
from ..auth.decorators import jwt_required, admin_required
from ..utils.response import ok
from ..utils.errors import NotFoundError
from ..services.stock_service import search_stocks, get_stock_list

bp = Blueprint("stocks", __name__, url_prefix="/api/stocks")


# ================================================================ 搜索
@bp.route("/search", methods=["GET"])
@jwt_required
def search():
    """
    GET /api/stocks/search?q=payy&limit=10
    支持代码 / 名称 / 拼音首字母 / 全拼 / 首字模糊匹配。
    """
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", "15")), 50)
    if not q:
        return ok(data=[], message="success")
    results = search_stocks(q, limit=limit)
    return ok(data=results, message="success")


# ================================================================ 列表（管理）
@bp.route("/list", methods=["GET"])
@admin_required
def list_stocks():
    """GET /api/stocks/list?page=1&per_page=50&keyword=茅台"""
    page = int(request.args.get("page", "1"))
    per_page = min(int(request.args.get("per_page", "50")), 200)
    keyword = request.args.get("keyword", "").strip()
    data = get_stock_list(page=page, per_page=per_page, keyword=keyword)
    return ok(data=data, message="success")


# ================================================================ 统计
@bp.route("/stats", methods=["GET"])
@admin_required
def stats():
    """股票数据统计（含按 asset_type 分布，纯增量、向后兼容）。"""
    total = db.session.execute(
        select(func.count()).select_from(Stock).where(Stock.is_active.is_(True))
    ).scalar() or 0
    sh_count = db.session.execute(
        select(func.count()).select_from(Stock).where(
            Stock.is_active.is_(True), Stock.market == "SH"
        )
    ).scalar() or 0
    sz_count = db.session.execute(
        select(func.count()).select_from(Stock).where(
            Stock.is_active.is_(True), Stock.market == "SZ"
        )
    ).scalar() or 0
    # 按 asset_type 分布（新增，纯增量）
    rows = db.session.execute(
        select(Stock.asset_type, func.count()).select_from(Stock).where(
            Stock.is_active.is_(True)
        ).group_by(Stock.asset_type)
    ).all()
    asset_type_counts = {row[0]: row[1] for row in rows}
    return ok(data={
        "total": total,
        "sh": sh_count,
        "sz": sz_count,
        "asset_type_counts": asset_type_counts,
    }, message="success")


# ================================================================ 单只详情
@bp.route("/<code>", methods=["GET"])
@jwt_required
def detail(code: str):
    """GET /api/stocks/600519"""
    stock = db.session.execute(
        select(Stock).where(Stock.code == code)
    ).scalar_one_or_none()
    if not stock:
        raise NotFoundError("资源不存在")
    return ok(data=stock.to_dict(), message="success")
