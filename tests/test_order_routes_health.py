"""交易路由健康检查：券商不可用时的错误响应语义。

修复前 trade_account_health 在 BrokerUnavailable 时返回
ok(data={"ok": False, "message": str(e)}, message="success")，
把业务失败当成功、且把内部异常细节泄露给前端。
验证：BrokerUnavailable -> 503 + fail + 不泄露内部信息。
"""
from __future__ import annotations

import pytest
from backend.app import create_app
from backend.extensions import db
from backend.models import User
from backend.broker.base import BrokerUnavailable
from werkzeug.security import generate_password_hash


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        u = User.query.filter_by(username="demo").first()
        if u is None:
            u = User(username="demo", role="user")
            u.set_password("Demo@123")
            db.session.add(u)
        else:
            u.set_password("Demo@123")
            u.role = "user"
            u.is_active = True
        db.session.commit()
    return app.test_client()


def _login(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Demo@123"})
    assert r.status_code == 200, r.text
    return r.get_json()["data"]["token"]


def test_health_broker_unavailable_returns_503_fail(client, monkeypatch):
    import backend.broker as broker_pkg

    def _boom(*a, **k):
        raise BrokerUnavailable("simulated broker down /var/run/qmt.sock refused")

    monkeypatch.setattr(broker_pkg, "get_broker", _boom)
    token = _login(client)
    r = client.post(
        "/api/trade/account/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503, r.text
    body = r.get_json()
    assert body["status"] == "error"
    assert body.get("code") == "broker_unavailable"
    # 不泄露内部异常细节
    blob = str(body)
    assert "simulated broker down" not in blob
    assert "/var/run" not in blob


def test_health_ok_when_broker_available(client, monkeypatch):
    import backend.broker as broker_pkg

    class _FakeBroker:
        def health_check(self):
            return {"ok": True, "latency_ms": 12}

    def _ok(*a, **k):
        return _FakeBroker()

    monkeypatch.setattr(broker_pkg, "get_broker", _ok)
    token = _login(client)
    r = client.post(
        "/api/trade/account/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["data"]["ok"] is True
