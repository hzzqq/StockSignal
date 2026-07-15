"""
backend/api/forum_routes.py
---------------------------
股吧 API：用户发帖 / 看帖 / 评论 / 点赞。
- GET    /api/forum/posts              帖子列表（可按 stock_code 过滤、分页）
- POST   /api/forum/posts              发帖 {title, content, stock_code?, stock_name?}
- GET    /api/forum/posts/<id>         帖子详情（含评论，自增浏览量）
- DELETE /api/forum/posts/<id>         删除帖子（仅作者或管理员）
- POST   /api/forum/posts/<id>/like    点赞
- POST   /api/forum/posts/<id>/comments 评论 {content}
"""
from __future__ import annotations
from flask import Blueprint, g, request
from sqlalchemy import select, func
from ..auth.decorators import jwt_required
from ..extensions import db
from ..models import ForumPost, ForumComment
from ..utils.response import ok
from ..utils.errors import ValidationError, NotFoundError

bp = Blueprint("forum", __name__, url_prefix="/api/forum")


@bp.get("/posts")
@jwt_required
def list_posts():
    """GET /api/forum/posts?stock_code=600519&limit=50&offset=0"""
    stock_code = (request.args.get("stock_code") or "").strip()
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except Exception:
        limit, offset = 50, 0

    stmt = select(ForumPost)
    if stock_code:
        stmt = stmt.where(ForumPost.stock_code == stock_code)
    stmt = stmt.order_by(ForumPost.created_at.desc()).limit(limit).offset(offset)
    rows = db.session.execute(stmt).scalars().all()

    # 附带每帖评论数
    items = []
    for p in rows:
        d = p.to_dict(with_content=False)
        d["comment_count"] = db.session.execute(
            select(func.count(ForumComment.id)).where(ForumComment.post_id == p.id)
        ).scalar() or 0
        items.append(d)
    return ok(data=items)


@bp.post("/posts")
@jwt_required
def create_post():
    """POST /api/forum/posts  body: {title, content, stock_code?, stock_name?}"""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    stock_code = (data.get("stock_code") or "").strip()
    stock_name = (data.get("stock_name") or "").strip()
    if not title:
        raise ValidationError("标题不能为空")
    if not content:
        raise ValidationError("内容不能为空")
    if len(title) > 200:
        raise ValidationError("标题过长（≤200 字）")

    p = ForumPost(
        user_id=g.current_user.id,
        username=g.current_user.username,
        title=title,
        content=content,
        stock_code=stock_code,
        stock_name=stock_name,
    )
    db.session.add(p)
    db.session.commit()
    return ok(data=p.to_dict(), message="发布成功", code="created")


@bp.get("/posts/<int:post_id>")
@jwt_required
def get_post(post_id: int):
    """GET /api/forum/posts/5 —— 详情 + 评论，自增浏览量。"""
    p = db.session.get(ForumPost, post_id)
    if not p:
        raise NotFoundError("帖子不存在")
    p.views = (p.views or 0) + 1
    db.session.commit()

    comments = db.session.execute(
        select(ForumComment).where(ForumComment.post_id == post_id).order_by(ForumComment.created_at.asc())
    ).scalars().all()
    data = p.to_dict(with_content=True)
    data["comments"] = [c.to_dict() for c in comments]
    return ok(data=data)


@bp.delete("/posts/<int:post_id>")
@jwt_required
def delete_post(post_id: int):
    """DELETE /api/forum/posts/5 —— 仅作者或管理员。"""
    p = db.session.get(ForumPost, post_id)
    if not p:
        raise NotFoundError("帖子不存在")
    if p.user_id != g.current_user.id and g.current_user.role != "admin":
        raise ValidationError("只能删除自己的帖子")
    db.session.execute(
        ForumComment.__table__.delete().where(ForumComment.post_id == post_id)
    )
    db.session.delete(p)
    db.session.commit()
    return ok(message="已删除")


@bp.post("/posts/<int:post_id>/like")
@jwt_required
def like_post(post_id: int):
    """POST /api/forum/posts/5/like"""
    p = db.session.get(ForumPost, post_id)
    if not p:
        raise NotFoundError("帖子不存在")
    p.likes = (p.likes or 0) + 1
    db.session.commit()
    return ok(data={"likes": p.likes}, message="点赞成功")


@bp.post("/posts/<int:post_id>/comments")
@jwt_required
def add_comment(post_id: int):
    """POST /api/forum/posts/5/comments  body: {content}"""
    p = db.session.get(ForumPost, post_id)
    if not p:
        raise NotFoundError("帖子不存在")
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        raise ValidationError("评论内容不能为空")
    c = ForumComment(
        post_id=post_id,
        user_id=g.current_user.id,
        username=g.current_user.username,
        content=content,
    )
    db.session.add(c)
    db.session.commit()
    return ok(data=c.to_dict(), message="评论成功", code="created")
