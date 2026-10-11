"""backend/tests/test_recommend_routes_security.py

T-238：荐股端点安全对表（flask-secure-json-api 基线）。

真实风险（2026-10-11 勘测）：GET /api/recommendations/<date> 的 date 直接拼
``os.path.join(d, "recommendations", f"{date}.json")``——Werkzeug <date> 不匹配
``/``，但 **Windows 路径分隔符 ``\\``（URL %5C）能到达 handler**，
``..\\..\\secret`` 可穿越读任意 .json（数据泄漏）；畸形格式则依赖宽泛 except 兜底。

约定：
1. date 必须匹配 ``^\\d{4}-\\d{2}-\\d{2}$``，否则 routes 层 400 统一信封（入口校验）；
2. engine 层 load_recommendation_by_date 同样拒绝非法格式（纵深防御，非 200 放行）；
3. 合法但无记录 → 200 + status=unavailable（既有诚实语义不破坏）。
"""
from __future__ import annotations

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND_DIR)
for p in (ROOT, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app import create_app            # noqa: E402
from backend.extensions import db             # noqa: E402
from backend.models import User               # noqa: E402
from backend.config import Config             # noqa: E402

try:
    from backend.utils.rate_limit import reset_rate_limit
except Exception:  # pragma: no cover
    def reset_rate_limit():
        pass


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 't.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        for uname, role in (("admin", "admin"), ("demo", "user")):
            if User.query.filter_by(username=uname).first() is None:
                u = User(username=uname, role=role)
                u.set_password("Pass@123")
                db.session.add(u)
        db.session.commit()
    yield application
    reset_rate_limit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_token(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "Pass@123"})
    assert r.status_code == 200, f"admin login failed: {r.status_code}"
    return r.get_json()["data"]["token"]


def _get(client, token, date_raw: str):
    return client.get(
        f"/api/recommendations/{date_raw}",
        headers={"Authorization": f"Bearer {token}"},
    )


# ── 1) 路径穿越 / 畸形格式必须 400（routes 层入口校验）──
@pytest.mark.parametrize("bad", [
    "..%5C..%5Csecret",          # Windows 反斜杠穿越（真实风险形态）
    "..%5C..%5C..%5Cetc",        # 多级穿越
    "2026-13-99",                # 合法形状但非法日期
    "abc",                       # 纯垃圾
    "20260101",                  # 缺分隔符
    "2026-1-1",                  # 单位数月日
])
def test_by_date_rejects_invalid_format(client, admin_token, bad):
    resp = _get(client, admin_token, bad)
    assert resp.status_code == 400, (
        f"GET /api/recommendations/{bad!r} 应 400，实际 {resp.status_code}（穿越/畸形放行）。body={resp.text[:200]!r}"
    )
    data = resp.get_json(silent=True)
    assert isinstance(data, dict) and data.get("status") == "error" and data.get("code") == "invalid_date", (
        f"400 响应必须是统一 error 信封（code=invalid_date）: {resp.text[:200]!r}"
    )


# ── 2) engine 层纵深防御：非法格式绝不触碰文件系统 ──
@pytest.mark.parametrize("bad", ["..\\..\\secret", "abc", "", None])
def test_engine_load_by_date_rejects_bad_format(bad):
    from modules.recommend_engine import load_recommendation_by_date

    rec = load_recommendation_by_date(bad)
    assert rec.get("status") == "unavailable", f"engine 应拒绝非法 date: {rec}"
    assert "格式" in (rec.get("reason") or ""), f"原因应说明格式非法: {rec}"


# ── 3) 合法日期 + 无记录 → 200 诚实 unavailable（既有语义不破坏）──
def test_by_date_valid_missing_returns_200_unavailable(client, admin_token):
    resp = _get(client, admin_token, "2024-01-01")
    assert resp.status_code == 200
    data = resp.get_json(silent=True)
    assert isinstance(data, dict) and data.get("status") == "ok"
    assert data["data"].get("status") == "unavailable"


def test_today_endpoint_shape(client, admin_token):
    resp = client.get("/api/recommendations/today", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.get_json(silent=True)
    assert isinstance(data, dict) and data.get("status") == "ok"
    assert data["data"].get("status") in ("ok", "unavailable")
