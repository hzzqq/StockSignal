"""
auth/service.py
---------------
登录业务 + token 签发。所有错误向上抛 ApiError，绝不在本层返回 HTML/字符串。
"""
from __future__ import annotations
import re
import time
from typing import Any, Dict
import jwt
from flask import current_app

from ..extensions import db
from ..models import User, OperationLog
from ..utils.errors import AuthError, ValidationError, ConflictError

# 与 admin_routes 保持一致的用户名/密码规则
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fa5]{2,32}$")
_PASSWORD_MIN = 6


def issue_token(user: User) -> str:
    """生成 JWT。sub=username；exp 自动写入。"""
    expires_in = int(current_app.config.get("JWT_EXPIRES_SECONDS", 3600))
    payload: Dict[str, Any] = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }
    secret = current_app.config["SECRET_KEY"]
    alg = current_app.config.get("JWT_ALGORITHM", "HS256")
    return jwt.encode(payload, secret, algorithm=alg)


def decode_token(token: str) -> Dict[str, Any]:
    """校验 JWT；失败统一抛 AuthError。"""
    secret = current_app.config["SECRET_KEY"]
    alg = current_app.config.get("JWT_ALGORITHM", "HS256")
    try:
        return jwt.decode(token, secret, algorithms=[alg])
    except jwt.ExpiredSignatureError:
        # 不暴露 token 原文/时间细节
        raise AuthError("登录已过期，请重新登录", code="token_expired")
    except jwt.InvalidTokenError:
        raise AuthError("无效的登录凭证", code="invalid_token")


def authenticate(username: str, password: str) -> User:
    """
    校验用户名/密码。失败消息统一为 '用户名或密码错误'，避免账户枚举。
    """
    if not username or not password:
        raise ValidationError("请提供用户名和密码")

    user = User.query.filter_by(username=username).first()
    # 故意两个分支都走同样消息，防止通过响应差异枚举账号
    if user is None or not user.is_active or not user.verify_password(password):
        raise AuthError("用户名或密码错误", code="invalid_credentials")

    return user


def register_user(username: str, password: str, confirm: str) -> User:
    """
    开放注册：新用户角色固定为 user，绝不允许通过自注册提权为 admin。
    失败统一抛 ApiError（由全局 errorhandler 转 JSON）。
    成功写库 + 记录审计日志，返回 User 实例。
    """
    # 长度防御：避免把超长字符串丢给数据库
    if len(username) > 64 or len(password) > 128:
        raise ValidationError("用户名或密码长度不合法")

    if not _USERNAME_RE.match(username):
        raise ValidationError("用户名需 2-32 位，仅含字母、数字、下划线或中文")
    if len(password) < _PASSWORD_MIN:
        raise ValidationError(f"密码至少 {_PASSWORD_MIN} 位")
    if password != confirm:
        raise ValidationError("两次输入的密码不一致")

    exists = User.query.filter_by(username=username).first()
    if exists:
        raise ConflictError("用户名已存在")

    user = User(username=username, role="user")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    # 审计日志：自注册（无操作者，记为自己）
    log = OperationLog(
        user_id=user.id,
        username=user.username,
        action="register",
        target=username,
        detail="self-registered as user",
    )
    db.session.add(log)
    db.session.commit()
    return user
