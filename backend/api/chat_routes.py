"""
backend/api/chat_routes.py
--------------------------
星辰 AI 对话历史持久化 REST API（按用户维度）。

- GET  /api/chat/history   返回当前登录用户的对话历史（JSON 数组）
- POST /api/chat/history   覆盖保存当前用户的对话历史

所有响应走 utils.response.ok/fail 包装；鉴权走 jwt_required（设置 g.current_user）。
"""
from __future__ import annotations

import json

from flask import Blueprint, request, g

from ..auth.decorators import jwt_required
from ..utils.response import ok, fail, _json_safe
from ..models import ChatHistory
from ..extensions import db

from ..utils.params import json_body
bp = Blueprint("chat", __name__, url_prefix="/api/chat")


def _ensure_json_safe(obj):
    """递归把消息中的不可序列化对象（datetime/Decimal/bytes/set…）转成 JSON 安全形式。

    直接复用 utils.response._json_safe（已覆盖常见类型且永不抛出），
    本函数仅作命名包装，保证保存历史时序列化永不崩溃——存入的是净化副本。
    """
    return _json_safe(obj)

# 保护上限：避免单用户历史无限膨胀撑爆字段
_MAX_MESSAGES = 200
_MAX_CHARS = 200_000


@bp.get("/history")
@jwt_required
def get_history():
    """GET /api/chat/history —— 取回当前用户对话历史。"""
    rec = ChatHistory.query.filter_by(user_id=g.current_user.id).first()
    if not rec or not rec.messages:
        return ok(data={"messages": []})
    try:
        messages = json.loads(rec.messages)
    except Exception:
        messages = []
    if not isinstance(messages, list):
        messages = []
    return ok(data={"messages": messages})


@bp.post("/history")
@jwt_required
def save_history():
    """POST /api/chat/history —— 保存（覆盖）当前用户对话历史。

    body: {"messages": [ {role, content, ...}, ... ]}
    """
    body = json_body()
    messages = body.get("messages")

    if not isinstance(messages, list):
        return fail(message="messages 必须是数组", code="bad_messages", http_status=400)

    # 截断到保护上限，保留最近 N 条
    if len(messages) > _MAX_MESSAGES:
        messages = messages[-_MAX_MESSAGES:]

    # 序列化前做安全净化：datetime/Decimal/bytes/set 等转为 JSON 安全形式，
    # 存入的是净化副本，避免 json.dumps 因不可序列化对象而崩溃丢失消息。
    messages = _ensure_json_safe(messages)

    try:
        payload = json.dumps(messages, ensure_ascii=False)
    except Exception:
        return fail(message="消息序列化失败", code="serialize_error", http_status=400)

    if len(payload) > _MAX_CHARS:
        return fail(message="对话历史过长，无法保存", code="too_large", http_status=413)

    rec = ChatHistory.query.filter_by(user_id=g.current_user.id).first()
    if rec is None:
        rec = ChatHistory(user_id=g.current_user.id)
        db.session.add(rec)
    rec.messages = payload
    db.session.commit()
    return ok(data={"saved": True, "count": len(messages)})
