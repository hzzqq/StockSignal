"""
backend/app.py
==============
StockSignal 管理后端入口。

本文件专门修一处高危问题：登录后响应体里夹杂了 HTML 标签、调试信息。
修复策略：
  1. 所有路由（无论业务层、auth 层、debug 接口）必须返回 utils.response.ok/fail 包装的 JSON。
  2. 全局 errorhandler 覆盖 ApiError、HTTPException、Exception 三类，
     强制走 JSON，绝不放行 Flask 默认的 HTML 错误页。
  3. 关闭 PROPAGATE_EXCEPTIONS；开启 JSON 排序 + UTF-8。
  4. 错误信息不暴露内部实现：
        - 生产模式不返回 traceback、文件路径、模块名
        - 仅允许 EXPOSE_INTERNAL_ERROR=1 调试时再打开
"""
from __future__ import annotations
import logging
from flask import Flask
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import db
from .utils.response import fail
from .utils.errors import ApiError


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # ---- 扩展 ----
    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})

    # ---- 蓝图 ----
    from .auth.routes import bp as auth_bp
    from .api.dashboard import bp as dashboard_bp
    from .api.admin_routes import bp as admin_bp
    from .api.stock_routes import bp as stock_bp
    from .api.config_routes import bp as config_bp
    from .api.market_routes import bp as market_bp
    from .api.task_routes import bp as task_bp
    from .api.chat_routes import bp as chat_bp
    from .api.alert_routes import bp as alert_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(alert_bp)

    # ---- 全局错误处理：把任何出口都锁回 JSON ----
    _register_error_handlers(app)
    _register_security_headers(app)

    # 关闭异常传播，避免默认 handler 漏出 HTML
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config["TRAP_HTTP_EXCEPTIONS"] = False
    app.json.sort_keys = False  # JSON 字段顺序稳定

    # ---- 健康检查（同样走 ok() 包装）----
    @app.get("/api/health")
    def health():
        from .utils.response import ok
        return ok(data={"service": "stocksignal-backend", "status": "alive"})

    # ---- 后端管理界面（适配前端金融风格；独立的有意 HTML 页，非 API）----
    # 说明：全局 errorhandler 仍对异常返回 JSON；本路由仅成功路径返回 text/html，
    # 同源调用既有鉴权 API，不注入任何用户输入，无 XSS 风险。
    from .admin_ui import render_admin_ui

    @app.get("/")
    @app.get("/admin")
    def admin_ui():
        return render_admin_ui()

    return app


# =====================================================================
# 错误处理
# =====================================================================

def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(err: ApiError):
        return fail(message=err.message, code=err.code, http_status=err.status)

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        # 任何 werkzeug HTTP 异常（404/405/415/...）一律 JSON
        # 注意：name 字段可能含 HTML，按需做安全消息替换
        code = (err.name or "http_error").lower().replace(" ", "_")
        code_map = {
            "not_found": (404, "资源不存在"),
            "method_not_allowed": (405, "请求方法不被允许"),
            "unsupported_media_type": (415, "不支持的媒体类型"),
            "bad_request": (400, "请求参数错误"),
            "forbidden": (403, "无权限访问"),
            "unauthorized": (401, "未授权"),
            "internal_server_error": (500, "服务内部错误"),
        }
        if code in code_map:
            http_status, safe_msg = code_map[code]
        else:
            safe_msg = "请求被拒绝"
            http_status = err.code or 500
        return fail(
            message=safe_msg,
            code=code if code in code_map else "http_error",
            http_status=http_status,
        )

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        # 关键：未捕获异常绝不放行原始 traceback / HTML
        # 服务端记录日志（运维需要），但响应体严格脱敏
        app.logger.exception("Unhandled exception: %s", type(err).__name__)
        expose = app.config.get("EXPOSE_INTERNAL_ERROR", False)
        if expose:
            # 仅调试模式才返回类型/消息；不允许回 HTML
            return fail(
                message=f"{type(err).__name__}: {err}",
                code="internal_error",
                http_status=500,
            )
        return fail(
            message="服务内部错误",
            code="internal_error",
            http_status=500,
        )


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def _add_headers(resp):
        ct = resp.headers.get("Content-Type", "")
        # 安全网：把「意外」的非 JSON 响应强制为 JSON，避免 Flask 默认 HTML 错误页泄漏。
        # 但有意的管理界面 HTML 页（text/html）必须保留，不能被误改成 JSON 头。
        if "text/html" not in ct and not ct.startswith("application/json"):
            try:
                resp.headers["Content-Type"] = "application/json; charset=utf-8"
            except Exception:
                pass
        # 安全头
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp


# =====================================================================
# 入口
# =====================================================================

logging.basicConfig(level=logging.INFO)
app = create_app()


if __name__ == "__main__":
    # 仅本地启动使用。生产请用 gunicorn / uvicorn + asgi-wsgi 桥。
    # 严禁 debug=True 暴露到公网。
    app.run(host="127.0.0.1", port=5050, debug=False)
