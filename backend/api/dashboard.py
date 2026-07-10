"""
api/dashboard.py
----------------
演示用：返回市场全景看板的概要数据。
任何用户登录后即可访问——对应截图中"市场全景看板"模块。
"""
from __future__ import annotations
from datetime import datetime
from flask import Blueprint, g
from ..auth.decorators import jwt_required
from ..utils.response import ok

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@bp.get("/summary")
@jwt_required
def summary():
    """
    GET /api/dashboard/summary
    {
      "user": "演示用户",
      "modules": [
        {"key": "tech",  "title": "技术面+AI分析"},
        {"key": "mood",  "title": "事件驱动/评分"},
        {"key": "news",   "title": "全板块资讯"}
      ],
      "ts": "2025-01-01T00:00:00Z"
    }
    """
    data = {
        "user": g.current_user.username,
        "modules": [
            {"key": "tech", "title": "技术面+AI分析", "icon": "🤖"},
            {"key": "mood", "title": "事件驱动/评分", "icon": "🔔"},
            {"key": "news", "title": "全板块资讯", "icon": "📰"},
        ],
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    return ok(data=data, message="欢迎回来")
