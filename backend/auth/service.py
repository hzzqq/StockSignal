"""
auth/service.py
---------------
登录业务 + token 签发。所有错误向上抛 ApiError，绝不在本层返回 HTML/字符串。
"""
from __future__ import annotations
import re
import time
import threading
from typing import Any, Dict
import jwt
from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

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


_DUMMY_PLAIN = "__stocksignal_timing_equalizer__"
_dummy_hash: str | None = None
_dummy_lock = threading.Lock()


def _equalize_hash_time(password: str) -> None:
    """用户不存在时，仍消耗一次等价的密码哈希校验开销。

    ⚠️ 为什么必需：werkzeug 默认哈希为 scrypt(32768,8,1)，单次校验实测约
    350ms。若「用户不存在」直接短路返回，而「用户存在但密码错」要跑满这
    350ms，二者响应时间差了两个数量级——攻击者只用秒表就能判定任意用户名
    是否注册（账户枚举），统一错误文案的防御被时序侧信道整个绕过。

    这里用同一套 generate/check 生成哑哈希（自动跟随 werkzeug 当前默认算法，
    无需手工同步参数），首次调用会多付一次 generate 的开销，之后缓存复用。
    """
    global _dummy_hash
    if _dummy_hash is None:
        with _dummy_lock:
            if _dummy_hash is None:
                _dummy_hash = generate_password_hash(_DUMMY_PLAIN)
    # 结果必然为 False，仅为消耗与真实校验等量的 CPU 时间
    check_password_hash(_dummy_hash, password or "")


def authenticate(username: str, password: str) -> User:
    """
    校验用户名/密码。失败消息统一为 '用户名或密码错误'，避免账户枚举。

    枚举防御分两层：
      1. 文案层：用户不存在 / 已禁用 / 密码错，全部返回同一条消息与 code。
      2. 时序层：用户不存在时也跑一次等价开销的哈希校验（见 _equalize_hash_time），
         使三条失败路径的耗时同量级。缺了这层，第 1 层形同虚设。
    """
    if not username or not password:
        raise ValidationError("请提供用户名和密码")

    user = User.query.filter_by(username=username).first()

    if user is None:
        # 抹平时序：不存在的用户名同样付出一次哈希校验的时间
        _equalize_hash_time(password)
        password_ok = False
    else:
        # 已禁用的用户也照常校验密码，避免「禁用」成为另一个时序标记
        password_ok = user.verify_password(password)

    # 故意三个分支都走同样消息，防止通过响应差异枚举账号
    if user is None or not user.is_active or not password_ok:
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
