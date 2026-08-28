"""backend/tests/test_json_body_robustness.py

**畸形 JSON 请求体健壮性**回归。

问题形态：很多路由写 ``data = request.get_json()`` 后直接 ``data.get("x")``。
当客户端（或被伪造的前端）发来的 body 不是 JSON 对象，而是
``[1,2,3]`` / ``"str"`` / ``null`` / ``123`` 时：
- 列表 → ``AttributeError: 'list' object has no attribute 'get'``
- 字符串 / 数字 → 同样 AttributeError
- ``null`` → ``AttributeError: 'NoneType' object has no attribute 'get'``
未捕获就会冒泡成 **500**（且是内部错误，污染日志、可被 DoS 放大）。

约定：这类输入属于「客户端错误」，应返回 4xx 的统一 ``fail`` 信封，
**绝不能 500**。

测试策略：对每个本地 DB 写接口（刻意排除会触发网络/后台扫描的路由，
如 market-alerts/scan、cond-orders/scan、trade/orders、tasks/），
用 4 种畸形 body 打过去，断言：
  1. 状态码 < 500（4xx 可接受：400/401/403/404/422 都行）；
  2. 响应仍是 JSON 信封（含 status 字段），不是 HTML 错误页。

2026-08-28 新增（Cycle 67）。
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


# 仅本地 DB 写接口；刻意排除会触发网络/后台扫描/券商的路由
TARGETS = [
    "/api/watchlist",
    "/api/watchlist/batch",
    "/api/junk-stocks",
    "/api/user-scores",
    "/api/price-alerts",
    "/api/forum/posts",
    "/api/cond-orders",
    "/api/admin/users",
    "/api/admin/config",
    "/api/auth/settings",
    "/api/market-alerts/config",
    "/api/chat/history",
]

# 畸形 body：列表 / 字符串 / 数字 / null（都不是 JSON 对象）
BAD_BODIES = [
    ("list", [1, 2, 3]),
    ("string", "just-a-string"),
    ("number", 123),
    ("null", None),
]


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
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


@pytest.mark.parametrize("path", TARGETS)
@pytest.mark.parametrize("label,bad", BAD_BODIES)
def test_malformed_body_never_500(client, admin_token, path, label, bad):
    resp = client.post(
        path,
        json=bad,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code < 500, (
        f"POST {path} 收到畸形 body({label}={bad!r}) 触发 500 —— "
        f"应返回 4xx 统一信封。body={resp.text[:300]!r}"
    )
    # 即便是 4xx，也必须是 JSON 信封，不能是裸 HTML / traceback
    data = resp.get_json(silent=True)
    assert isinstance(data, dict) and "status" in data, (
        f"POST {path} body({label}) 响应不是统一 JSON 信封: {resp.text[:300]!r}"
    )


def test_valid_dict_body_still_works(client, admin_token):
    """反向验证：正常 dict body 不能被健壮性改动误伤（watchlist 加自选）。"""
    resp = client.post(
        "/api/watchlist",
        json={"code": "600519", "name": "贵州茅台"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code < 500
    data = resp.get_json(silent=True)
    assert isinstance(data, dict) and "status" in data
