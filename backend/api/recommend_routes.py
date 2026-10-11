"""
backend/api/recommend_routes.py
-------------------------------
每日荐股 REST API（T-233）。范式抄 market_alert_routes（jwt 信封 + 分页参数）。

- GET /api/recommendations/today    最新一份推荐（无则 status=unavailable，诚实语义）
- GET /api/recommendations/<date>   指定日期归档
- POST /api/recommendations/generate 手动触发生成（admin；幂等，当日已有则跳过）
"""
from __future__ import annotations

import re
from datetime import datetime

from flask import Blueprint

from ..auth.decorators import admin_required, jwt_required
from ..utils.response import fail, ok

bp = Blueprint("recommendations", __name__, url_prefix="/api/recommendations")

# T-238：date 路径段白名单——Werkzeug <date> 不匹配 "/"，但 Windows 反斜杠（URL %5C）
# 能到达 handler，``..\\..\\secret`` 曾可拼进文件路径读任意 .json（数据泄漏）。
# 正则管形状，strptime 管真实日历（2026-13-99 这类假日期同样 400）。
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(date: str) -> bool:
    if not (isinstance(date, str) and _DATE_RE.fullmatch(date)):
        return False
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


@bp.get("/today")
@jwt_required
def today():
    from modules.recommend_engine import load_latest_recommendation
    rec = load_latest_recommendation()
    return ok(data=rec, message="success" if rec.get("status") == "ok" else rec.get("reason", "unavailable"))


@bp.get("/<date>")
@jwt_required
def by_date(date: str):
    if not _valid_date(date or ""):
        return fail(message="日期格式非法（须为真实存在的 YYYY-MM-DD）", code="invalid_date", http_status=400)
    from modules.recommend_engine import load_recommendation_by_date
    rec = load_recommendation_by_date(date)
    return ok(data=rec, message="success" if rec.get("status") == "ok" else rec.get("reason", "unavailable"))


@bp.post("/generate")
@admin_required
def generate():
    """手动触发当日生成（幂等；调度器同一落盘，已有当日文件则直接返回）。"""
    from modules.recommend_engine import generate_daily_recommendation, today_generated
    if today_generated():
        from modules.recommend_engine import load_latest_recommendation
        return ok(data=load_latest_recommendation(), message="今日推荐已存在（幂等跳过）")
    rec = generate_daily_recommendation()
    return ok(data=rec, message="已生成" if rec.get("status") == "ok" else rec.get("reason", "生成失败"))
