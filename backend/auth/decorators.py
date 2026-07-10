"""
auth/decorators.py
------------------
JWT 校验 + 角色校验装饰器。失败抛 ApiError，由全局 handler 转 JSON。
"""
from __future__ import annotations
from functools import wraps
from flask import request, current_app, g
from jwt import PyJWTError

from ..models import User
from ..utils.errors import AuthError, ForbiddenError
from .service import decode_token


def _extract_bearer_token() -> str:
    auth = request.headers.get("Authorization", "")
    if not auth or not auth.startswith("Bearer "):
        raise AuthError("缺少登录凭证", code="missing_token")
    token = auth[len("Bearer "):].strip()
    if not token:
        raise AuthError("缺少登录凭证", code="missing_token")
    return token


def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        try:
            payload = decode_token(token)
        except PyJWTError:
            # 防御性：service 层已经处理过，这里再兜一次
            raise AuthError("无效的登录凭证", code="invalid_token")

        user = User.query.filter_by(username=payload.get("sub")).first()
        if user is None or not user.is_active:
            raise AuthError("用户不存在或已停用", code="user_inactive")

        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    @jwt_required
    def wrapper(*args, **kwargs):
        user: User = getattr(g, "current_user", None)
        if user is None or user.role != "admin":
            # 不告诉前端"你不是 admin"，统一说无权限
            raise ForbiddenError("无权限访问", code="forbidden")
        return fn(*args, **kwargs)

    return wrapper
