# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_recommend_routes_gate.py — T-245 收尾回归守卫。

/api/recommendations/today 与 /api/recommendations/<date> 接入输出边界二道闸：
  1. status==ok 且 picks 含 overall_level=="high" → 剔除 + data.risk_gate_boundary_dropped
     + message 注明「剔除 N 只高危」（不静默）；
  2. unknown≠guilty：unknown / not_scanned / low / medium 一律保留、无剔除字段；
  3. /<date> 同款闸（合法日期如 2026-11-20）；
  4. date 非法（2026-13-01）→ 400 不受闸影响；
  5. status 非 ok（unavailable）诚实降级路径不过闸、原样透传。

fixture 范式同 test_read_routes.py（module 级 app/client/token + 临时 sqlite +
issue_token）；engine 加载函数经 monkeypatch 替换（路由内延迟 import，
patch modules.recommend_engine 属性即可生效）。
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
import modules.recommend_engine as recommend_engine  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('gate_db') / 'gate.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="gateuser", role="user")
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
        u = User.query.filter_by(username="gateuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _pick(code: str, level: str, scanned: bool = True):
    rs = ({"status": "scanned", "overall_level": level} if scanned
          else {"status": "not_scanned"})
    return {"code": code, "name": code, "risk_scan": rs}


# ── 1) /today：high 被剔除且不静默 ──
def test_today_drops_high_and_reports(client, token, monkeypatch):
    rec = {"status": "ok", "date": "2026-11-21", "picks": [
        _pick("600519", "low"),
        _pick("600666", "high"),
        _pick("600888", "low"),
    ]}
    monkeypatch.setattr(recommend_engine, "load_latest_recommendation", lambda: rec)
    resp = client.get("/api/recommendations/today", headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    assert obj["data"]["risk_gate_boundary_dropped"] == 1, obj["data"]
    assert "剔除 1 只高危" in obj["message"], obj["message"]
    codes = [p["code"] for p in obj["data"]["picks"]]
    assert "600666" not in codes, "高危标的应被输出边界二道闸剔除"
    assert codes == ["600519", "600888"], codes


# ── 2) /today：unknown≠guilty，全部保留且无剔除字段 ──
def test_today_unknown_not_guilty_all_kept(client, token, monkeypatch):
    rec = {"status": "ok", "date": "2026-11-21", "picks": [
        _pick("600519", "unknown"),
        _pick("600666", "medium"),
        _pick("600888", "low", scanned=False),      # not_scanned
        _pick("600999", "unknown", scanned=False),  # not_scanned + unknown 形态
        _pick("600777", "low"),
    ]}
    monkeypatch.setattr(recommend_engine, "load_latest_recommendation", lambda: rec)
    obj = client.get("/api/recommendations/today", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    assert "risk_gate_boundary_dropped" not in obj["data"], obj["data"]
    assert obj["message"] == "success", obj["message"]
    codes = [p["code"] for p in obj["data"]["picks"]]
    assert codes == ["600519", "600666", "600888", "600999", "600777"], codes


# ── 3) /<date>：同款剔除用例 ──
def test_by_date_drops_high_and_reports(client, token, monkeypatch):
    rec = {"status": "ok", "date": "2026-11-20", "picks": [
        _pick("600111", "high"),
        _pick("600222", "low"),
    ]}
    monkeypatch.setattr(recommend_engine, "load_recommendation_by_date", lambda d: rec)
    resp = client.get("/api/recommendations/2026-11-20", headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    assert obj["data"]["risk_gate_boundary_dropped"] == 1, obj["data"]
    assert "剔除 1 只高危" in obj["message"], obj["message"]
    assert [p["code"] for p in obj["data"]["picks"]] == ["600222"], obj["data"]


# ── 4) /<date>：非法 date → 400 不受闸影响 ──
def test_by_date_invalid_date_still_400(client, token):
    resp = client.get("/api/recommendations/2026-13-01", headers=_auth(token))
    assert resp.status_code == 400
    obj = resp.get_json(silent=True)
    assert isinstance(obj, dict) and obj["status"] == "error" and obj["code"] == "invalid_date", obj


# ── 5) status 非 ok：诚实降级路径不过闸、原样透传 ──
def test_non_ok_status_passthrough_not_gated(client, token, monkeypatch):
    rec = {"status": "unavailable", "reason": "推荐文件缺失",
           "picks": [_pick("600666", "high")]}
    monkeypatch.setattr(recommend_engine, "load_latest_recommendation", lambda: rec)
    obj = client.get("/api/recommendations/today", headers=_auth(token)).get_json()
    assert obj["status"] == "ok", obj
    assert obj["data"]["status"] == "unavailable", obj
    assert obj["message"] == "推荐文件缺失", obj["message"]
    assert obj["data"]["picks"] == [_pick("600666", "high")], "非 ok 降级路径不过闸"
    assert "risk_gate_boundary_dropped" not in obj["data"], obj["data"]


def test_non_ok_by_date_passthrough_not_gated(client, token, monkeypatch):
    rec = {"status": "unavailable", "reason": "无当日归档"}
    monkeypatch.setattr(recommend_engine, "load_recommendation_by_date", lambda d: rec)
    obj = client.get("/api/recommendations/2026-11-20", headers=_auth(token)).get_json()
    assert obj["status"] == "ok", obj
    assert obj["data"]["status"] == "unavailable", obj
    assert obj["message"] == "无当日归档", obj["message"]
