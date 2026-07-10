"""
utils/errors.py
---------------
集中定义业务异常。所有业务层抛出的异常都会被全局 errorhandler 捕获，
统一转换为纯 JSON 响应，绝不返回 HTML / 调试栈。
"""
from __future__ import annotations


class ApiError(Exception):
    """
    业务层统一异常。
    :param message:  给用户看的错误描述（已脱敏，不含内部实现）
    :param status:   HTTP 状态码
    :param code:     业务错误码（前端分支判断用）
    :param http_code_in_body: True=在 body 里额外暴露 http 字段（默认 False 避免冗余）
    """

    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code

    def to_dict(self) -> dict:
        return {"message": self.message, "code": self.code}


class AuthError(ApiError):
    """401 鉴权失败：用于 token 缺失/失效/密码错误。"""

    def __init__(self, message: str = "未授权", code: str = "unauthorized"):
        super().__init__(message, status=401, code=code)


class ForbiddenError(ApiError):
    """403 权限不足。"""

    def __init__(self, message: str = "无权限访问", code: str = "forbidden"):
        super().__init__(message, status=403, code=code)


class NotFoundError(ApiError):
    """404 资源不存在。"""

    def __init__(self, message: str = "资源不存在", code: str = "not_found"):
        super().__init__(message, status=404, code=code)


class ValidationError(ApiError):
    """422 参数校验失败。"""

    def __init__(self, message: str = "参数不合法", code: str = "validation_error"):
        super().__init__(message, status=422, code=code)


class ConflictError(ApiError):
    """409 冲突：资源已存在。"""

    def __init__(self, message: str = "资源已存在", code: str = "conflict"):
        super().__init__(message, status=409, code=code)
