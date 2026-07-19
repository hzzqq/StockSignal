"""
auth/routes.py
--------------
所有接口严格走 utils.response.ok/fail，禁止直接返回字符串、HTML。
"""
from __future__ import annotations
from flask import Blueprint, request, g
from sqlalchemy import select
from ..extensions import db
from ..utils.response import ok, fail
from ..utils.errors import ValidationError
from ..utils.ratelimit import is_allowed, make_key
from ..models import OperationLog
from .service import authenticate, issue_token, decode_token, register_user
from .decorators import jwt_required

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _parse_json() -> dict:
    """只接受 application/json 里的 JSON；其它类型直接 422。"""
    if not request.is_json:
        raise ValidationError("请求必须是 application/json 格式")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体格式错误")
    return body


@bp.post("/login")
def login():
    """
    POST /api/auth/login
    body: {"username": "...", "password": "..."}
    返回: {"status":"ok", "data": {"token": "...", "user": {...}}}
    """
    body = _parse_json()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    # 长度防御：避免把超长字符串丢给数据库
    if len(username) > 64 or len(password) > 128:
        raise ValidationError("用户名或密码长度不合法")

    # 认证限流：同 IP+用户名 60s 内最多 5 次，防爆破
    if not is_allowed(make_key(request.remote_addr or "", username)):
        return fail(
            message="请求过于频繁，请稍后再试",
            code="rate_limited",
            http_status=429,
        )

    user = authenticate(username, password)
    token = issue_token(user)
    return ok(
        data={"token": token, "user": user.to_public()},
        message="登录成功",
    )


@bp.post("/register")
def register():
    """
    POST /api/auth/register
    body: {"username": "...", "password": "...", "confirm": "..."}
    开放注册：新用户角色固定为 user（不可自提权），返回 201 + user 公开信息。
    """
    body = _parse_json()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    confirm = body.get("confirm") or body.get("confirm_password") or ""

    # 注册限流：同 IP+用户名 60s 内最多 5 次，防批量注册/爆破
    if not is_allowed(make_key(request.remote_addr or "", username)):
        return fail(
            message="请求过于频繁，请稍后再试",
            code="rate_limited",
            http_status=429,
        )

    user = register_user(username, password, confirm)
    return ok(
        data=user.to_public(),
        message="注册成功",
        code="created",
        http_status=201,
    )


@bp.get("/me")
@jwt_required
def me():
    """返回当前登录用户。"""
    return ok(data=g.current_user.to_public())


@bp.post("/avatar")
@jwt_required
def save_avatar():
    """
    POST /api/auth/avatar
    body: {"avatar": "data:image/png;base64,...."}
    把当前用户头像（base64 data URL）按账号持久化到数据库，
    刷新 / 换设备 / 重启后端都不会丢失。仅接受 data:image/ 前缀，限制体积。
    """
    body = _parse_json()
    avatar = body.get("avatar")
    if not isinstance(avatar, str):
        raise ValidationError("头像数据格式不正确")
    # base64 后约 3MB（对应原图 ~2.2MB）；过大直接拒绝，避免撑爆 users 表
    if len(avatar) > 4_000_000:
        raise ValidationError("头像数据过大，请压缩到 3MB 以内")
    if not avatar.startswith("data:image/"):
        raise ValidationError("头像必须是 data:image/ 开头的 base64 图片")
    g.current_user.avatar = avatar
    db.session.commit()
    return ok(data=g.current_user.to_public(), message="头像已保存")


@bp.post("/settings")
@jwt_required
def save_settings():
    """
    POST /api/auth/settings
    body: {"settings": {"theme_mode": "dark", "font_size": "large", ...}}
    把当前用户偏好（主题 / 字号等）按账号持久化到数据库，刷新 / 换设备不丢。
    """
    import json as _json
    body = _parse_json()
    settings = body.get("settings")
    if not isinstance(settings, dict):
        raise ValidationError("settings 必须是对象")
    raw = _json.dumps(settings, ensure_ascii=False)
    if len(raw) > 10_000:
        raise ValidationError("设置数据过大")
    g.current_user.settings = raw
    db.session.commit()
    return ok(data=g.current_user.to_public(), message="设置已保存")


@bp.post("/logout")
@jwt_required
def logout():
    """
    无状态 JWT 没有服务端会话，'注销' 主要是建议客户端丢弃 token。
    服务端可选地做 token 黑名单，这里先返回成功。
    """
    return ok(message="已登出")


@bp.get("/token-info")
@jwt_required
def token_info():
    """
    调试/前端用：返回 token 中的非敏感声明。
    """
    auth = request.headers.get("Authorization", "")
    token = auth[len("Bearer "):].strip()
    payload = decode_token(token)
    safe = {k: v for k, v in payload.items() if k in ("sub", "uid", "role", "iat", "exp")}
    return ok(data=safe)


@bp.get("/logins")
@jwt_required
def login_history():
    """
    GET /api/auth/logins?limit=20
    返回当前用户最近的登录记录（来源：OperationLog action='login'），
    供「我的」页展示登录历史。
    """
    from ..extensions import db
    limit = min(int(request.args.get("limit", "20")), 50)
    stmt = (
        select(OperationLog)
        .where(OperationLog.user_id == g.current_user.id, OperationLog.action == "login")
        .order_by(OperationLog.id.desc())
        .limit(limit)
    )
    rows = db.session.execute(stmt).scalars().all()
    return ok(
        data=[r.to_dict() for r in rows],
        message="success",
    )
