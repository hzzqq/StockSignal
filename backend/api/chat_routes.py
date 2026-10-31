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
from ..models import ChatHistory, ChatConversation
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

# =====================================================================
# T-311 多会话管理：/api/chat/conversations*
# 与旧单记录端点（上方 /history）并存向后兼容；新前端走会话端点，
# 旧前端 / 降级模式仍走 /history，互不影响。
# =====================================================================
_MAX_CONVS = 50     # 每用户最多保留会话数（防无限膨胀）
_TITLE_MAX = 40     # 会话标题长度上限


def _load_messages_field(raw) -> list:
    """把 DB 里的 JSON 文本解析为消息列表；损坏/非列表一律诚实降级为空，不抛。"""
    if not raw:
        return []
    try:
        msgs = json.loads(raw)
    except Exception:
        return []
    return msgs if isinstance(msgs, list) else []


def _norm_title(title, fallback="新对话") -> str:
    """标题规范化：去空白、空则回退默认、钳到上限。"""
    t = str(title or "").strip()
    if not t:
        t = fallback
    return t[:_TITLE_MAX]


def _serialize_conv(rec: ChatConversation, with_messages: bool = False) -> dict:
    data = {
        "id": rec.id,
        "title": rec.title or "新对话",
        "count": len(_load_messages_field(rec.messages)),
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }
    if with_messages:
        data["messages"] = _load_messages_field(rec.messages)
    return data


@bp.get("/conversations")
@jwt_required
def list_conversations():
    """GET /api/chat/conversations —— 当前用户会话列表（按更新时间倒序，封顶 50）。"""
    recs = (
        ChatConversation.query.filter_by(user_id=g.current_user.id)
        .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        .limit(_MAX_CONVS)
        .all()
    )
    return ok(data={"conversations": [_serialize_conv(r) for r in recs]})


@bp.post("/conversations")
@jwt_required
def create_conversation():
    """POST /api/chat/conversations —— 新建会话。body 可选 {"title": "..."}。"""
    body = json_body()
    conv_count = ChatConversation.query.filter_by(user_id=g.current_user.id).count()
    if conv_count >= _MAX_CONVS:
        return fail(
            message=f"会话数已达上限（{_MAX_CONVS}），请先删除旧会话",
            code="too_many_conversations", http_status=400,
        )
    rec = ChatConversation(
        user_id=g.current_user.id,
        title=_norm_title(body.get("title")),
        messages="[]",
    )
    db.session.add(rec)
    db.session.commit()
    return ok(data=_serialize_conv(rec, with_messages=True))


@bp.get("/conversations/<int:cid>")
@jwt_required
def get_conversation(cid: int):
    """GET /api/chat/conversations/<id> —— 取单个会话（含 messages）。越权/不存在一律 404。"""
    rec = ChatConversation.query.filter_by(id=cid, user_id=g.current_user.id).first()
    if rec is None:
        return fail(message="会话不存在", code="not_found", http_status=404)
    return ok(data=_serialize_conv(rec, with_messages=True))


@bp.post("/conversations/<int:cid>")
@jwt_required
def save_conversation(cid: int):
    """POST /api/chat/conversations/<id> —— 覆盖保存会话消息（可选更新标题）。

    body: {"messages": [...], "title": "可选"}
    """
    rec = ChatConversation.query.filter_by(id=cid, user_id=g.current_user.id).first()
    if rec is None:
        return fail(message="会话不存在", code="not_found", http_status=404)
    body = json_body()
    messages = body.get("messages")
    if not isinstance(messages, list):
        return fail(message="messages 必须是数组", code="bad_messages", http_status=400)
    if len(messages) > _MAX_MESSAGES:
        messages = messages[-_MAX_MESSAGES:]
    messages = _ensure_json_safe(messages)
    try:
        payload = json.dumps(messages, ensure_ascii=False)
    except Exception:
        return fail(message="消息序列化失败", code="serialize_error", http_status=400)
    if len(payload) > _MAX_CHARS:
        return fail(message="会话内容过长，无法保存", code="too_large", http_status=413)
    rec.messages = payload
    if "title" in body:
        rec.title = _norm_title(body.get("title"))
    db.session.commit()
    return ok(data={"saved": True, "count": len(messages)})


@bp.delete("/conversations/<int:cid>")
@jwt_required
def delete_conversation(cid: int):
    """DELETE /api/chat/conversations/<id> —— 删除会话。越权/不存在一律 404。"""
    rec = ChatConversation.query.filter_by(id=cid, user_id=g.current_user.id).first()
    if rec is None:
        return fail(message="会话不存在", code="not_found", http_status=404)
    db.session.delete(rec)
    db.session.commit()
    return ok(data={"deleted": True, "id": cid})


# =====================================================================
# T-311 扩展：会话导出（markdown / json）
# =====================================================================
_EXPORT_FORMATS = ("markdown", "json")

_ROLE_LABEL = {
    "user": "🧑 用户",
    "assistant": "🤖 星辰AI",
    "system": "⚙️ 系统",
}


def _render_markdown(rec: ChatConversation) -> str:
    """把一个会话渲染成 Markdown 导出文本。

    格式：# 标题 / 导出时间 / 逐轮对话（role→emoji 标签）。
    sources 标签、as_of 等元信息如实保留在消息里；不编造内容。
    """
    ts = rec.updated_at.isoformat() if rec.updated_at else "—"
    lines = [
        f"# {rec.title or '未命名会话'}",
        "",
        f"**会话 ID**：#{rec.id}",
        f"**更新时间**：{ts}",
        f"**消息数**：{len(_load_messages_field(rec.messages))}",
        "",
        "---",
        "",
    ]
    msgs = _load_messages_field(rec.messages)
    if not msgs:
        lines.append("_（空会话，尚无消息）_")
    for i, m in enumerate(msgs, 1):
        role = str(m.get("role", "")).strip() if isinstance(m, dict) else ""
        label = _ROLE_LABEL.get(role, role or "?")
        content = ""
        if isinstance(m, dict):
            content = str(m.get("content") or "")
        lines.append(f"### {i}. {label}")
        lines.append("")
        lines.append(content or "_（空消息）_")
        lines.append("")
    return "\n".join(lines)


@bp.get("/conversations/<int:cid>/export")
@jwt_required
def export_conversation(cid: int):
    """GET /api/chat/conversations/<id>/export?format=markdown|json —— 导出会话。

    - format=json  → Flask envelope 包装的结构化数据（与 GET /conversations/<id> 同形）
    - format=markdown → 直接返回 text/markdown 纯文本（Content-Length 诚实标注）
    - 越权/不存在 → 404（与其他端点一致）
    - format 非法 → 400
    """
    rec = ChatConversation.query.filter_by(id=cid, user_id=g.current_user.id).first()
    if rec is None:
        return fail(message="会话不存在", code="not_found", http_status=404)

    fmt = request.args.get("format", "json").lower()
    if fmt not in _EXPORT_FORMATS:
        return fail(
            message=f"format 必须是 {' / '.join(_EXPORT_FORMATS)}",
            code="bad_format", http_status=400,
        )

    if fmt == "json":
        return ok(data=_serialize_conv(rec, with_messages=True))

    # markdown
    md = _render_markdown(rec)
    from flask import Response
    return Response(
        md,
        mimetype="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition":
                f"attachment; filename=\"conversation_{cid}_{rec.title[:20].replace(' ', '_')}.md\"",
        },
    )
