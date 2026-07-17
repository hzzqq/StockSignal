"""
api/admin_routes.py
-------------------
管理端接口：用户 CRUD + 操作日志。仅 admin 可访问。
"""
from __future__ import annotations
from flask import Blueprint, g, request
from sqlalchemy import select, func
from ..auth.decorators import admin_required
from ..extensions import db
from ..models import User, OperationLog
from ..utils.response import ok
from ..utils.errors import ValidationError, NotFoundError, ConflictError
import re

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fa5]{2,32}$")
_PASSWORD_MIN = 6


def _log(action: str, target: str = "", detail: str = ""):
    """记录操作日志。"""
    u = g.current_user
    log = OperationLog(
        user_id=u.id,
        username=u.username,
        action=action,
        target=target,
        detail=detail,
    )
    db.session.add(log)


# ================================================================ 用户列表
@bp.get("/users")
@admin_required
def list_users():
    """GET /api/admin/users?page=1&per_page=50&keyword=adm"""
    page = int(request.args.get("page", "1"))
    per_page = min(int(request.args.get("per_page", "50")), 200)
    keyword = request.args.get("keyword", "").strip()

    stmt = select(User).order_by(User.id.asc())
    if keyword:
        stmt = stmt.where(User.username.contains(keyword))

    total = db.session.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar() or 0

    users = db.session.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).scalars()

    return ok(data={
        "items": [u.to_public() for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    })


# ================================================================ 创建用户
@bp.post("/users")
@admin_required
def create_user():
    """POST /api/admin/users  body: {username, password, role}"""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip()

    if not _USERNAME_RE.match(username):
        raise ValidationError("用户名需 2-32 位，仅含字母数字下划线中文")
    if len(password) < _PASSWORD_MIN:
        raise ValidationError(f"密码至少 {_PASSWORD_MIN} 位")
    if role not in ("admin", "user"):
        raise ValidationError("角色仅限 admin 或 user")

    exists = db.session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if exists:
        raise ConflictError("用户名已存在")

    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    _log("create_user", target=username, detail=f"role={role}")
    db.session.commit()

    return ok(data=user.to_public(), message="创建成功", code="created")


# ================================================================ 修改用户
@bp.put("/users/<int:user_id>")
@admin_required
def update_user(user_id: int):
    """PUT /api/admin/users/3  body: {role?, password?, is_active?}"""
    user = db.session.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    if not user:
        raise NotFoundError("资源不存在")

    data = request.get_json(silent=True) or {}
    changes = []

    if "role" in data:
        new_role = data["role"]
        if new_role not in ("admin", "user"):
            raise ValidationError("角色仅限 admin 或 user")
        if user.id == g.current_user.id and new_role != "admin":
            raise ValidationError("不能取消自己的管理员角色")
        user.role = new_role
        changes.append(f"role={new_role}")

    if "is_active" in data:
        if user.id == g.current_user.id and not data["is_active"]:
            raise ValidationError("不能停用自己的账号")
        user.is_active = bool(data["is_active"])
        changes.append(f"is_active={user.is_active}")

    if "password" in data and data["password"]:
        pwd = data["password"]
        if len(pwd) < _PASSWORD_MIN:
            raise ValidationError(f"密码至少 {_PASSWORD_MIN} 位")
        user.set_password(pwd)
        changes.append("password=***")

    _log("update_user", target=user.username, detail=", ".join(changes))
    db.session.commit()

    return ok(data=user.to_public(), message="更新成功")


# ================================================================ 删除用户
@bp.delete("/users/<int:user_id>")
@admin_required
def delete_user(user_id: int):
    """DELETE /api/admin/users/3"""
    user = db.session.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    if not user:
        raise NotFoundError("资源不存在")
    if user.id == g.current_user.id:
        raise ValidationError("不能删除自己")
    if user.username == "admin":
        raise ValidationError("不能删除初始管理员账号")

    _log("delete_user", target=user.username)
    db.session.delete(user)
    db.session.commit()
    return ok(message="删除成功")


# ================================================================ 操作日志
@bp.get("/logs")
@admin_required
def list_logs():
    """GET /api/admin/logs?page=1&per_page=50"""
    page = int(request.args.get("page", "1"))
    per_page = min(int(request.args.get("per_page", "50")), 200)

    stmt = select(OperationLog).order_by(OperationLog.id.desc())
    total = db.session.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar() or 0

    logs = db.session.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).scalars()

    return ok(data={
        "items": [l.to_dict() for l in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    })


# ================================================================ 运行监控
@bp.get("/monitor")
@admin_required
def monitor_stats():
    """GET /api/admin/monitor
    返回后端实时运行指标：请求量、错误率、延迟、活跃用户、热点端点。
    """
    from ..monitor import get_stats
    from ..models import User, ForumPost, ForumComment, PriceAlert
    from sqlalchemy import select, func

    base = get_stats()
    # 业务计数（轻量查询）
    try:
        user_total = db.session.execute(select(func.count()).select_from(User)).scalar() or 0
        post_total = db.session.execute(select(func.count()).select_from(ForumPost)).scalar() or 0
        comment_total = db.session.execute(select(func.count()).select_from(ForumComment)).scalar() or 0
        alert_total = db.session.execute(select(func.count()).select_from(PriceAlert)).scalar() or 0
    except Exception:
        user_total = post_total = comment_total = alert_total = 0

    base["business"] = {
        "users": user_total,
        "forum_posts": post_total,
        "forum_comments": comment_total,
        "price_alerts": alert_total,
    }
    return ok(data=base, message="success")
