# -*- coding: utf-8 -*-
"""
backend/openapi.py — OpenAPI 3.0 规范生成器（T-159 骨架）

为什么不用 flasgger / flask-smorest：
    本项目后端零重型依赖倾向，且 75 个端点的详细 schema 注解改造是一笔大账。
    骨架阶段用 url_map 动态生成「路径全集 + 方法 + 分组 + 鉴权 + 统一信封」，
    对接方即有单一可读契约面；请求/响应字段的逐端点详述可增量补，
    由 tests/test_openapi_spec.py 钉住「路径全集不漂移」的下限。

口径约定（对接方须知）：
    - 所有业务响应都是统一信封 {status, code, message, data}（EnvelopeResponse）；
    - security 标注为自动推断：公开端点白名单之外的 /api/* 一律标 BearerAuth，
      如与个别路由的实际鉴权有出入，以路由代码（jwt_required/admin_required
      装饰器）为准——这是文档下限而非权威。
"""
from __future__ import annotations

import re
from typing import Any, Dict

from flask import Flask, jsonify

# bp 名 → tag 分组（endpoint 前缀）。查不到的 bp 用通用名兜底，绝不丢端点。
TAGS: Dict[str, Dict[str, str]] = {
    "auth": {"name": "Auth", "description": "登录 / 注册 / token 续期 / 会话"},
    "dashboard": {"name": "Dashboard", "description": "看板聚合数据"},
    "admin": {"name": "Admin", "description": "后台管理（admin_required）"},
    "stock": {"name": "Stock", "description": "个股数据 / 名称 / 行情"},
    "config": {"name": "Config", "description": "系统配置读写"},
    "market": {"name": "Market", "description": "市场数据（指数 / 资金 / 情绪）"},
    "task": {"name": "Task", "description": "后台任务与进度"},
    "chat": {"name": "Chat", "description": "AI 对话"},
    "alert": {"name": "Alert", "description": "预警规则与通知"},
    "stock_tag": {"name": "StockTag", "description": "个股标签管理"},
    "forum": {"name": "Forum", "description": "股吧 / 社区"},
    "market_alert": {"name": "MarketAlert", "description": "市场异动告警"},
    "order": {"name": "Order", "description": "交易 / 模拟盘订单"},
}

# 公开端点（不标 BearerAuth 的白名单；其余 /api/* 默认标注鉴权）
_PUBLIC = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
}

_PARAM_RE = re.compile(r"<(?:(?P<conv>[^:<>]+):)?(?P<name>[^<>]+)>")


def _openapi_path(rule: str) -> str:
    """Flask 规则 <int:code> → OpenAPI {code}。"""
    return _PARAM_RE.sub(r"{\g<name>}", rule)


def _param_schema(flask_rule: str) -> list:
    """从 Flask 规则提取 path 参数（converter → type）。"""
    params = []
    for m in _PARAM_RE.finditer(flask_rule):
        conv = (m.group("conv") or "string").lower()
        t = "integer" if conv.startswith("int") else "string"
        params.append({
            "name": m.group("name"),
            "in": "path",
            "required": True,
            "schema": {"type": t},
        })
    return params


def build_spec(app: Flask) -> Dict[str, Any]:
    """从 app.url_map 动态生成 OpenAPI 3.0.3 spec。输出键序稳定（便于 diff）。"""
    paths: Dict[str, Any] = {}
    for rule in app.url_map.iter_rules():
        if rule.rule in ("/api/openapi.json", "/api/docs"):
            continue  # 文档自举端点不进 paths
        if not rule.rule.startswith("/api/"):
            continue  # admin_ui 等非 API 路由不在契约面内
        endpoint = rule.endpoint
        bp = endpoint.split(".", 1)[0] if "." in endpoint else ""
        tag_meta = TAGS.get(bp)
        tag_name = tag_meta["name"] if tag_meta else (bp.capitalize() or "Root")
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        node = paths.setdefault(_openapi_path(rule.rule), {})
        for m in methods:
            op: Dict[str, Any] = {
                "tags": [tag_name],
                "summary": f"{m.upper()} {rule.endpoint}",
                "responses": {
                    "200": {
                        "description": "统一信封响应",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EnvelopeResponse"}
                            }
                        },
                    }
                },
            }
            path_params = _param_schema(rule.rule)
            if path_params:
                op["parameters"] = path_params
            is_public = rule.rule in _PUBLIC
            if not is_public:
                op["security"] = [{"BearerAuth": []}]
                op["responses"]["401"] = {
                    "description": "未登录 / token 过期（可 POST /api/auth/refresh 续期）",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/EnvelopeResponse"}
                        }
                    },
                }
            node[m.lower()] = op

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "StockSignal Backend API",
            "version": "1.0.0",
            "description": (
                "统一信封：所有业务响应为 {status, code, message, data}；"
                "status=ok 时 data 为业务数据。鉴权：登录换取 JWT，"
                "请求头 Authorization: Bearer <token>；token 1 小时有效，"
                "过期前/后可调 /api/auth/refresh 在滑动窗口内静默续期（T-158）。"
                "security 标注为自动推断，个别出入以路由代码为准。"
            ),
        },
        "tags": [
            {"name": m["name"], "description": m["description"]}
            for m in TAGS.values()
        ],
        "paths": dict(sorted(paths.items())),
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            },
            "schemas": {
                "EnvelopeResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string",
                                   "enum": ["ok", "error"],
                                   "description": "ok=成功；error=失败"},
                        "code": {"type": "string",
                                 "description": "业务码：ok / created / "
                                                "validation_error / token_expired / "
                                                "invalid_token / rate_limited / "
                                                "unauthorized / forbidden ..."},
                        "message": {"type": "string", "description": "人类可读提示（已脱敏）"},
                        "data": {"description": "业务数据（任意 JSON 类型，失败时为 null）"},
                    },
                    "required": ["status", "code", "message"],
                }
            },
        },
    }


_DOCS_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>StockSignal API 文档</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    // spec 由本服务动态生成；CDN 不可达时直接下载 /api/openapi.json 离线阅读
    SwaggerUIBundle({url: '/api/openapi.json', dom_id: '#swagger-ui'});
  </script>
</body>
</html>
"""


def register_openapi(app: Flask) -> None:
    """挂载 GET /api/openapi.json（裸 spec）与 GET /api/docs（Swagger UI 页）。"""

    @app.get("/api/openapi.json")
    def openapi_json():
        # 裸 spec（不包统一信封）：OpenAPI 工具链要求可直读的规范 JSON
        return jsonify(build_spec(app))

    @app.get("/api/docs")
    def openapi_docs():
        return _DOCS_HTML
