"""
backend/tests/test_auth_refresh.py
----------------------------------
T-158：JWT 有效期缩短 + refresh 机制的守卫。

【背景（T-149 人工校准实证）】
  JWT_EXPIRES_SECONDS 原默认 604800（7 天）。token 一旦泄露，7 天内攻击者可
  自由使用且无任何撤销手段——严格大厂口径直接不达标。

【新契约】
  1. access token 默认 1 小时（3600s），env 可覆盖；
  2. 新增 JWT_REFRESH_SECONDS（默认 7 天）：「滑动刷新窗口」——签名有效且
     iat 距今不超窗的 token，即使已过期，也可 POST /api/auth/refresh 换新；
  3. refresh 被滥用面收敛：伪造签名 / 超窗 / 用户禁用 / 缺头，全部 401；
  4. 刷新出的新 token 必须能通过既有 jwt_required（/api/auth/me 可用）。

【为什么是滑动窗口而不是独立 refresh_token 表】
  本项目为单机 SQLite + 无状态 JWT，独立 refresh token 需要服务端存储与
  撤销语义（DB 表 + 清理任务），复杂度收益比差；iat 滑动窗口在无状态前提下
  把「泄露 token 的可用时长」从 7 天压缩到 1 小时（续期需真实凭证在窗口内
  主动刷新），已覆盖主要风险面。语义升级留待多租户改造一并考虑。
"""
from __future__ import annotations

import os
import sys
import time

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import jwt as pyjwt                          # noqa: E402
import pytest                                # noqa: E402

from backend.app import create_app           # noqa: E402
from backend.config import Config            # noqa: E402
from backend.extensions import db            # noqa: E402
from backend.models import User              # noqa: E402


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'a.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600          # 新默认：1 小时
        JWT_REFRESH_SECONDS = 604800        # 刷新窗口：7 天

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        u = User(username="alice", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        dead = User(username="banned", role="user")
        dead.set_password("Pass@123")
        dead.is_active = False
        db.session.add(dead)
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client):
    return client.post("/api/auth/login",
                       json={"username": "alice", "password": "Pass@123"})


def _post_refresh(client, token):
    return client.post("/api/auth/refresh",
                       headers={"Authorization": f"Bearer {token}"})


def _mint(app, username="alice", *, iat=None, exp=None, secret_override=None):
    """手工造 token（用于构造「已过期但在窗口内」等边界样本）。"""
    with app.app_context():
        secret = secret_override or app.config["SECRET_KEY"]
        now = int(time.time())
        payload = {
            "sub": username, "uid": 1, "role": "user",
            "iat": now if iat is None else iat,
            "exp": now + 3600 if exp is None else exp,
        }
        return pyjwt.encode(payload, secret, algorithm="HS256")


# ───────────────────────── 1. 新默认值契约 ─────────────────────────
class TestDefaults:
    def test_access_token_default_is_one_hour(self):
        """T-149 校准实证的缺陷主体：默认 7 天 → 1 小时。"""
        assert Config.JWT_EXPIRES_SECONDS == 3600

    def test_refresh_window_default_is_seven_days(self):
        assert getattr(Config, "JWT_REFRESH_SECONDS", None) == 604800


# ───────────────────────── 2. refresh 端点行为 ─────────────────────────
class TestRefreshEndpoint:
    def test_refresh_with_valid_token_issues_new(self, client, app):
        """有效 token 换新：新 token 与旧 token 同身份，且可直接使用。"""
        old = _login(client).get_json()["data"]["token"]
        resp = _post_refresh(client, old)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["status"] == "ok"
        assert body["data"]["token"], "必须返回新 token"
        assert body["data"]["user"]["username"] == "alice"
        # 同一秒内续期，新 token 的 iat/exp 与旧 token 相同 → 字符串可相等，
        # 这是可接受的（身份与有效窗口完全一致）；硬断言必须换「新窗口」的
        # 语义由 test_refresh_after_expiry_within_window 的「过期后可用」覆盖。

        # 新 token 必须能通过既有鉴权（防「刷新出的 token 是废纸」）
        me = client.get("/api/auth/me",
                        headers={"Authorization": f"Bearer {body['data']['token']}"})
        assert me.status_code == 200

    def test_refresh_after_expiry_within_window(self, client, app):
        """核心新能力：token 已过期但 iat 在窗口内 → 仍可换新（滑动续期）。"""
        now = int(time.time())
        expired = _mint(app, iat=now - 3700, exp=now - 100)  # 过期 100s，iat 1h 前
        me = client.get("/api/auth/me",
                        headers={"Authorization": f"Bearer {expired}"})
        assert me.status_code == 401  # 旧 token 确实已不能用

        resp = _post_refresh(client, expired)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        new_token = resp.get_json()["data"]["token"]
        me2 = client.get("/api/auth/me",
                         headers={"Authorization": f"Bearer {new_token}"})
        assert me2.status_code == 200, "刷新出的 token 必须立即可用"

    def test_refresh_beyond_window_rejected(self, client, app):
        """iat 超出刷新窗口（默认 7 天）→ 401，必须重新登录。"""
        now = int(time.time())
        ancient = _mint(app, iat=now - 604800 - 3600, exp=now - 604700)
        resp = _post_refresh(client, ancient)
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "token_expired"

    def test_refresh_forged_token_rejected(self, client, app):
        """伪造签名（密钥不对）→ 401 invalid_token，绝不能换新。"""
        forged = _mint(app, secret_override="attacker-controlled-secret-0123456789")
        resp = _post_refresh(client, forged)
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "invalid_token"

    def test_refresh_missing_token_rejected(self, client):
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 401

    def test_refresh_garbage_token_rejected(self, client):
        resp = _post_refresh(client, "not.a.jwt")
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "invalid_token"

    def test_refresh_inactive_user_rejected(self, client, app):
        """被禁用用户的 token（即使签名/窗口都合法）→ 401。"""
        now = int(time.time())
        with app.app_context():
            payload = {"sub": "banned", "uid": 2, "role": "user",
                       "iat": now - 100, "exp": now + 3000}
            token = pyjwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")
        resp = _post_refresh(client, token)
        assert resp.status_code == 401

    def test_refresh_rate_limited(self, tmp_path):
        """refresh 与 login 共享限流桶（同 IP+身份 60s/N 次），防窗口端点被爆破。

        RATE_LIMIT_MAX=2 时：login 消耗第 1 次，第 1 次 refresh 是第 2 次（放行），
        第 2 次 refresh 超限 → 429。
        """
        class _RLConfig(Config):
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'rl.db'}"
            TESTING = True
            RATE_LIMIT_ENABLED = True
            RATE_LIMIT_MAX = 2
            RATE_LIMIT_WINDOW = 60

        application = create_app(_RLConfig)
        with application.app_context():
            db.create_all()
            u = User(username="carol", role="user")
            u.set_password("Pass@123")
            db.session.add(u)
            db.session.commit()
        c = application.test_client()
        old = c.post("/api/auth/login",
                     json={"username": "carol", "password": "Pass@123"}
                     ).get_json()["data"]["token"]
        seen = []
        for i in range(2):
            seen.append(c.post("/api/auth/refresh",
                               headers={"Authorization": f"Bearer {old}"}).status_code)
        assert seen == [200, 429], f"login 占 1 次额度后：refresh 首次放行、次次 429，实际 {seen}"
