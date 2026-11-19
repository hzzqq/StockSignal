# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_policy_read_endpoints.py — 政策事件传导工作台 3 个只读端点回归守卫。

零网络：monkeypatch 两个数据层模块（policy_store / sector_map）的函数；
event_graph.build_transmission / display_rows 是纯函数不触网，直接用真值。
覆盖：空库降级 / 非法 policy_id 400 / derived 标注 / failed 行业列 members_unavailable
不编成分股 / NaN 清洗 / status 校验 / 异常仍 200。
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
import backend.api.read_routes as rr  # noqa: E402


PID = "a" * 32
PID_OTHER = "b" * 32


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'policy_read.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="policyread", role="user")
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
        u = User.query.filter_by(username="policyread").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _doc(**over):
    d = {
        "policy_id": PID,
        "title": "关于促进半导体产业高质量发展的若干政策",
        "issuing_body": "国家发展改革委",
        "doc_number": "发改产业〔2026〕123号",
        "publish_date": "2026-11-10",
        "source_url": f"https://example.gov.cn/policy/{PID}",
        "source": "ndrc",
        "body_text": "推动半导体和集成电路产业高质量发展。" * 20,
        "body_source": "html",
        "content_hash": "c" * 32,
        "crawled_at": "2026-11-12T10:00:00",
    }
    d.update(over)
    return d


def _sector(**over):
    d = {
        "board_name": "半导体",
        "board_code": "BK001",
        "board_type": "industry",
        "keywords": "半导体,芯片,集成电路",
        "stock_codes": "600001,600002",
        "member_count": 2,
        "source": "rule_l1",
        "fetch_status": "ok",
        "updated_at": "2026-11-01 00:00:00",
    }
    d.update(over)
    return d


def _resolved(**over):
    s = _sector(**over)
    return {
        "name": s["board_name"],
        "board_code": s["board_code"],
        "board_type": s["board_type"],
        "keywords": s["keywords"],
        "stock_codes": s["stock_codes"],
        "member_count": s["member_count"],
        "source": s["source"],
        "fetch_status": s["fetch_status"],
        "description": None,
        "updated_at": s["updated_at"],
    }


def _stats():
    return {"total": 12, "ok": 10, "failed": 2, "stale": 0, "manual_sectors": 30}


# ───────────── 鉴权 ─────────────

def test_all_three_endpoints_require_token(client):
    for url in (
        "/api/v2/read/policy-documents",
        f"/api/v2/read/policy-transmission?policy_id={PID}",
        "/api/v2/read/sector-map",
    ):
        assert client.get(url).status_code == 401, url


# ───────────── policy-documents ─────────────

def test_policy_documents_empty_db_degrades(client, token, monkeypatch):
    monkeypatch.setattr(rr.policy_store, "read_recent", lambda limit=20: [])
    monkeypatch.setattr(rr.policy_store, "policy_store_stats", lambda: _stats())
    resp = client.get("/api/v2/read/policy-documents", headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok"
    assert obj["data"]["items"] == []
    assert "policy_db_empty" in obj["data"]["unavailable"]


def test_policy_documents_derived_fields_and_no_full_body(client, token, monkeypatch):
    monkeypatch.setattr(rr.policy_store, "read_recent", lambda limit=20: [_doc()])
    monkeypatch.setattr(rr.policy_store, "policy_store_stats", lambda: _stats())
    resp = client.get("/api/v2/read/policy-documents", headers=_auth(token))
    assert resp.status_code == 200
    item = resp.get_json()["data"]["items"][0]
    # 原文日期原样，不被 crawled_at / now() 覆盖
    assert item["publish_date"] == "2026-11-10"
    assert item["crawled_at"] == "2026-11-12T10:00:00"
    # 列表不返回完整 body_text，只给派生 200 字摘录
    assert "body_text" not in item
    assert isinstance(item["body_excerpt"], str) and len(item["body_excerpt"]) == 200
    # derived 字段有类型且 note 显式标注为派生
    assert isinstance(item["is_fresh"], bool)
    assert "派生" in resp.get_json()["data"]["note"]


def test_policy_documents_nan_sanitized(client, token, monkeypatch):
    bad = _doc(issuing_body=float("nan"), publish_date=None)
    monkeypatch.setattr(rr.policy_store, "read_recent", lambda limit=20: [bad])
    monkeypatch.setattr(rr.policy_store, "policy_store_stats", lambda: _stats())
    resp = client.get("/api/v2/read/policy-documents", headers=_auth(token))
    assert resp.status_code == 200
    raw = resp.get_data(as_text=True)
    assert "NaN" not in raw and "Infinity" not in raw
    item = resp.get_json()["data"]["items"][0]
    assert item["issuing_body"] is None
    assert item["publish_date"] is None  # 缺失不补 0 / 不 now() 兜底


def test_policy_documents_exception_still_200(client, token, monkeypatch):
    def boom(limit=20):
        raise RuntimeError("db down")

    monkeypatch.setattr(rr.policy_store, "read_recent", boom)
    resp = client.get("/api/v2/read/policy-documents", headers=_auth(token))
    assert resp.status_code == 200
    assert "policy_store_error" in resp.get_json()["data"]["unavailable"]


# ───────────── policy-transmission ─────────────

def test_policy_transmission_invalid_id_400(client, token):
    for bad in ("", "not-hex", "A" * 32, "a" * 31, "a" * 33):
        resp = client.get(f"/api/v2/read/policy-transmission?policy_id={bad}", headers=_auth(token))
        assert resp.status_code == 400, bad
        assert resp.get_json()["code"] == "validation_error"


def test_policy_transmission_ok_local_index(client, token, monkeypatch):
    monkeypatch.setattr(rr.policy_store, "read_recent", lambda limit=200: [_doc()])
    monkeypatch.setattr(rr.sector_map, "list_sectors", lambda status=None: [_sector()])
    monkeypatch.setattr(rr.sector_map, "resolve_sector", lambda name: _resolved())
    resp = client.get(f"/api/v2/read/policy-transmission?policy_id={PID}", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert d["status"] == "ok"
    assert d["policy"]["policy_id"] == PID
    assert d["policy"]["body_text"]  # 详情含原文正文
    assert d["entries"] and d["entries"][0]["code"] in ("600001", "600002")
    # 行业派生标注 + 代码占位名（name === code）
    assert d["sectors"][0]["derived"] is True
    assert d["sectors"][0]["matched_by"] == "name"
    assert all(e["name"] == e["code"] for e in d["entries"])
    # basis / disclaimer / derived_note 原样透出
    assert d["basis"] and d["disclaimer"] and "派生" in d["derived_note"]
    assert "非收益预测" in d["derived_note"]


def test_policy_transmission_failed_sector_not_expanded(client, token, monkeypatch):
    monkeypatch.setattr(rr.policy_store, "read_recent", lambda limit=200: [_doc()])
    monkeypatch.setattr(
        rr.sector_map, "list_sectors",
        lambda status=None: [_sector(fetch_status="failed")],
    )
    monkeypatch.setattr(
        rr.sector_map, "resolve_sector",
        lambda name: _resolved(fetch_status="failed"),
    )
    resp = client.get(f"/api/v2/read/policy-transmission?policy_id={PID}", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    # 命中失败行业列 members_unavailable，不展开成分股、不显示成 0 只
    assert d["entries"] == []
    assert d["members_unavailable"]
    assert d["members_unavailable"][0]["fetch_status"] == "failed"
    assert d["members_unavailable"][0]["derived"] is True


def test_policy_transmission_missing_policy_unavailable(client, token, monkeypatch):
    monkeypatch.setattr(rr.policy_store, "read_recent", lambda limit=200: [])
    resp = client.get(f"/api/v2/read/policy-transmission?policy_id={PID_OTHER}", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["status"] == "unavailable"
    assert "policy_not_found" in d["unavailable"]
    assert d["policy"] is None


# ───────────── sector-map ─────────────

def test_sector_map_ok_and_invalid_status(client, token, monkeypatch):
    monkeypatch.setattr(rr.sector_map, "list_sectors", lambda status=None: [_sector()])
    monkeypatch.setattr(rr.sector_map, "sector_map_stats", lambda: _stats())
    resp = client.get("/api/v2/read/sector-map", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["items"] and d["items"][0]["board_name"] == "半导体"
    assert d["stats"]["total"] == 12 and d["stats"]["manual_sectors"] == 30
    bad = client.get("/api/v2/read/sector-map?status=bogus", headers=_auth(token))
    assert bad.status_code == 400
    assert bad.get_json()["code"] == "validation_error"
