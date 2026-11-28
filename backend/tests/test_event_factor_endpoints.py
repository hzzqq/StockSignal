# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_event_factor_endpoints.py — I3 事件因子两端点守卫。

覆盖 GET /api/v2/read/event-factor 与 GET /api/v2/read/event-long-list：
  1. 成功全字段透传（缺失保持 None，不补 0）；
  2. 失败 available=False + reason 带出；
  3. 非法 code -> 400；
  4. 适配器异常 -> 200 降级（绝不 500）；
  5. 看多榜成功 items + count；
  6. 空榜 items=[] count=0；
  7. 非法 limit -> 400，缺省 -> top_n=20；
  8. 两端点未登录 -> 401。

诚实红线：适配器返回什么就透传什么，本层不编造 score/rank/日期。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
import modules.event_factor as ef  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    from modules import cache_utils
    cache_utils._CACHE.clear()
    yield
    cache_utils._CACHE.clear()


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path_factory.mktemp('efdb') / 'a.db'}"

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="efuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        u = User.query.filter_by(username="efuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


FACTOR_OK = {
    "available": True,
    "symbol": "600519",
    "score": 72.5,
    "signal": "看多",
    "rank": 0.92,
    "date": "2026-10-16",
    "source": "P1-ev-top_long",
    "horizon": {"label": "1-2 周（10 交易日）", "days": 10},
    "hard_logic": {"label": "订单/中标", "matched": True},
}
LONG_ROWS = [
    {"symbol": "600519", "score": 92.0, "raw_rank": 0.92, "raw_pred": 1.4,
     "signal": "看多", "source": "P1-ev-top_long", "horizon": {"days": 10},
     "hard_logic": {"label": "订单"}},
    {"symbol": "000001", "score": None, "raw_rank": None, "raw_pred": None,
     "signal": "看多", "source": "P1-ev-top_long", "horizon": {"days": 10},
     "hard_logic": {"label": "无标注"}},
]


# ── 1. event-factor 成功全字段透传 ──────────────────────────────────────
def test_event_factor_ok_all_fields(client, token, monkeypatch):
    monkeypatch.setattr(ef, "get_event_factor", lambda **kw: dict(FACTOR_OK))
    resp = client.get("/api/v2/read/event-factor?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok"
    d = obj["data"]
    for k in ("available", "symbol", "score", "signal", "rank", "date",
              "source", "horizon", "hard_logic", "reason"):
        assert k in d, f"契约字段缺失: {k}"
    assert d["available"] is True
    assert d["score"] == 72.5
    assert d["signal"] == "看多"
    assert d["rank"] == 0.92
    assert d["date"] == "2026-10-16"
    assert d["source"] == "P1-ev-top_long"
    assert d["horizon"] == {"label": "1-2 周（10 交易日）", "days": 10}
    assert d["reason"] is None  # 成功态 reason 显式 None，不臆造


# ── 2. event-factor 失败降级带 reason ───────────────────────────────────
def test_event_factor_unavailable_reason(client, token, monkeypatch):
    monkeypatch.setattr(ef, "get_event_factor", lambda **kw: {
        "available": False, "symbol": "600519", "reason": "模型 ev 无信号文件",
    })
    resp = client.get("/api/v2/read/event-factor?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["available"] is False
    assert "无信号文件" in d["reason"]
    assert d["score"] is None and d["signal"] is None  # 不编造伪评分


# ── 3. 非法 code -> 400 ─────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["", "12345", "1234567", "60a519", "SH600519"])
def test_event_factor_invalid_code(client, token, bad):
    resp = client.get(f"/api/v2/read/event-factor?code={bad}", headers=_auth(token))
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_param"


# ── 4. 适配器异常 -> 200 降级 ───────────────────────────────────────────
def test_event_factor_exception_degrades(client, token, monkeypatch):
    def _boom(**kw):
        raise RuntimeError("adapter exploded")

    monkeypatch.setattr(ef, "get_event_factor", _boom)
    resp = client.get("/api/v2/read/event-factor?code=600519", headers=_auth(token))
    assert resp.status_code == 200  # 绝不 500
    d = resp.get_json()["data"]
    assert d["available"] is False
    assert "adapter exploded" in d["reason"]
    assert d["score"] is None


# ── 5. 看多榜成功 ───────────────────────────────────────────────────────
def test_event_long_list_ok(client, token, monkeypatch):
    seen = {}

    def _rows(top_n):
        seen["top_n"] = top_n
        return [dict(r) for r in LONG_ROWS]

    monkeypatch.setattr(ef, "event_driven_long_list", _rows)
    resp = client.get("/api/v2/read/event-long-list?limit=20", headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok"
    d = obj["data"]
    assert seen["top_n"] == 20
    assert d["count"] == 2 and len(d["items"]) == 2
    assert d["items"][0]["symbol"] == "600519"
    assert d["items"][0]["score"] == 92.0
    assert d["items"][1]["score"] is None  # 缺失不补 0
    assert "无信号即空榜" in d["note"]


# ── 6. 空榜 ─────────────────────────────────────────────────────────────
def test_event_long_list_empty(client, token, monkeypatch):
    monkeypatch.setattr(ef, "event_driven_long_list", lambda top_n: [])
    resp = client.get("/api/v2/read/event-long-list", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["items"] == [] and d["count"] == 0
    assert d["note"]


# ── 7. 非法 limit -> 400；缺省 -> top_n=20；异常 -> 空榜 ────────────────
@pytest.mark.parametrize("bad", ["0", "7", "abc", "1000", "-1"])
def test_event_long_list_invalid_limit(client, token, bad):
    resp = client.get(f"/api/v2/read/event-long-list?limit={bad}", headers=_auth(token))
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_param"


def test_event_long_list_default_limit(client, token, monkeypatch):
    seen = {}
    monkeypatch.setattr(ef, "event_driven_long_list",
                        lambda top_n: (seen.update(top_n=top_n) or []))
    resp = client.get("/api/v2/read/event-long-list", headers=_auth(token))
    assert resp.status_code == 200
    assert seen["top_n"] == 20


def test_event_long_list_exception_empty(client, token, monkeypatch):
    def _boom(top_n):
        raise RuntimeError("list exploded")

    monkeypatch.setattr(ef, "event_driven_long_list", _boom)
    resp = client.get("/api/v2/read/event-long-list?limit=10", headers=_auth(token))
    assert resp.status_code == 200  # 绝不 500
    d = resp.get_json()["data"]
    assert d["items"] == [] and d["count"] == 0


# ── 8. 未登录 -> 401（鉴权闸门先于参数校验与取数）──────────────────────
@pytest.mark.parametrize("ep", [
    "/api/v2/read/event-factor?code=600519",
    "/api/v2/read/event-long-list?limit=20",
])
def test_event_factor_endpoints_require_token(client, ep):
    resp = client.get(ep)
    assert resp.status_code == 401
