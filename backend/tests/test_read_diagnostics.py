# -*- coding: utf-8 -*-  # noqa: UP009
"""W4-D · /api/v2/read/diagnostics（数据源 + 接口检测）端点回归。

覆盖：
  - 鉴权闸门（无 token 401）；
  - 默认零网络（probe 为 null，且不调用任何真实探网方法）；
  - probe=1 才触发真实探测，且探测失败时该项独立降级、整端点不 500；
  - 端点清单来自 Flask url_map（不硬编码），含 diagnostics 自身；
  - 数据源/时效两项分别独立降级：任一抛异常不影响另外两项；
  - 只读红线：端点不写任何数据文件（不调用 detect_stall/record_health_observation）。
"""
from __future__ import annotations

import os
import sys

import pytest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    # 必须用文件型 SQLite：项目 SQLAlchemy 配置带 pool_size/max_overflow，
    # :memory: 走 StaticPool 会拒收这两个参数（TypeError）。与 test_read_routes.py 同款。
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('diagdb') / 'a.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="diaguser", role="user")
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
        u = User.query.filter_by(username="diaguser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _get(client, token, qs=""):
    return client.get(f"/api/v2/read/diagnostics{qs}", headers=_auth(token))


def test_auth_gate_requires_token(client):
    """无 token 必须 401（与其它 read 端点同款闸门）。"""
    assert client.get("/api/v2/read/diagnostics").status_code == 401


def test_default_is_zero_network(client, token, monkeypatch):
    """默认 probe=null，且绝不调用真实探网方法（秒回、离线可用）。"""
    called = []

    def _forbidden(*_a, **_kw):
        called.append(1)
        raise AssertionError("默认请求不得触发真实网络探测")

    monkeypatch.setattr(rr, "_diag_network_probe", _forbidden)
    resp = _get(client, token)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert d["probe"] is None, "默认不应带探网结果"
    assert called == [], "默认请求触发了探网"


def test_envelope_shape(client, token):
    """契约字段齐全、逐项带 available 诚实标志、端点清单非空且来自动态枚举。"""
    d = _get(client, token).get_json()["data"]
    for k in ("sources", "freshness", "endpoints", "probe", "note"):
        assert k in d, f"data 缺字段 {k}"
    assert isinstance(d["sources"], dict) and "available" in d["sources"]
    assert isinstance(d["sources"]["items"], list)
    assert isinstance(d["freshness"], dict) and "available" in d["freshness"]
    assert isinstance(d["freshness"]["rows"], list)
    assert isinstance(d["endpoints"], list) and len(d["endpoints"]) > 0
    paths = [e["path"] for e in d["endpoints"]]
    assert "/api/v2/read/diagnostics" in paths, "端点清单应包含自身"
    assert all(e["path"].startswith("/api/v2/read/") for e in d["endpoints"])
    # 需参端点（路径参数 OR 必填 query）必须标注为不可自动探测，不编造 probe_path
    for e in d["endpoints"]:
        assert "required_query" in e and "sample_query" in e
        if "<" in e["path"] or e["path"] in rr._DIAG_REQUIRED_QUERY:
            assert e["needs_params"] is True and e["probe_path"] is None
            assert e["required_query"], "需参端点必须列出 required_query"
        else:
            assert e["needs_params"] is False and e["probe_path"] == e["path"]


def test_required_query_endpoints_are_never_auto_probed(client, token):
    """缺 query 即 400 的端点不得出现在自动探测清单里（否则接真后端大面积假 400）。"""
    d = _get(client, token).get_json()["data"]
    by_path = {e["path"]: e for e in d["endpoints"]}
    assert by_path, "端点清单为空"
    for path, params in rr._DIAG_REQUIRED_QUERY.items():
        e = by_path.get(path)
        assert e is not None, f"登记的需参端点未在路由表中注册: {path}"
        assert e["needs_params"] is True and e["probe_path"] is None
        assert set(e["required_query"]) == set(params), f"{path} 参数清单与实现不一致"
        assert e["sample_query"] and all(f"{k}=" in e["sample_query"] for k in params)
    auto = [e["path"] for e in d["endpoints"] if e["probe_path"]]
    assert not (set(rr._DIAG_REQUIRED_QUERY) & set(auto)), "需参端点混进了自动探测清单"


def test_probe_flag_triggers_network_check(client, token, monkeypatch):
    """probe=1 显式触发探网；探测失败时整项独立降级、整端点仍 200。"""
    monkeypatch.setattr(rr, "_diag_network_probe", lambda: {
        "available": False, "levels": [], "reason": "模拟探网不可用（测试桩）",
    })
    d = _get(client, token, "?probe=1").get_json()["data"]
    assert d["probe"] is not None
    assert d["probe"]["available"] is False
    assert "模拟探网不可用" in d["probe"]["reason"]


def test_probe_levels_shape(client, token, monkeypatch):
    """探网成功时四源结果如实透出（不美化失败项）。"""
    monkeypatch.setattr(rr, "_diag_network_probe", lambda: {
        "available": True,
        "levels": [
            {"level": "L1", "ok": True, "detail": "30 行", "latency_ms": 176},
            {"level": "L2", "ok": False, "detail": "连接超时", "latency_ms": 10000},
        ],
        "reason": None,
    })
    d = _get(client, token, "?probe=1").get_json()["data"]
    levels = d["probe"]["levels"]
    assert [x["level"] for x in levels] == ["L1", "L2"]
    assert levels[1]["ok"] is False and "超时" in levels[1]["detail"]


def test_source_health_failure_is_isolated(client, token, monkeypatch):
    """数据源检测不可用时 → 仅该项 available=False 降级，时效/端点清单仍正常返回。

    _diag_source_health 内部已自行捕获异常并返回降级对象，这里以桩替换其返回值，
    验证端点如实传递降级态（不把失败包装成「全部可用」）。
    """
    monkeypatch.setattr(rr, "_diag_source_health", lambda: {
        "available": False, "summary": None, "checked_at": None,
        "items": [], "reason": "RuntimeError: 模拟 fetcher 不可用",
    })
    resp = _get(client, token)
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["sources"]["available"] is False
    assert d["sources"]["items"] == []
    assert "endpoints" in d and len(d["endpoints"]) > 0
    assert "freshness" in d


def test_freshness_failure_is_isolated(client, token, monkeypatch):
    """时效检测抛异常 → 仅该项降级，不把空数组包装成「全部新鲜」。"""
    monkeypatch.setattr(rr, "_diag_freshness", lambda: {
        "available": False, "rows": [], "reason": "OSError: 模拟本地文件不可读",
    })
    resp = _get(client, token)
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["freshness"]["available"] is False
    assert d["freshness"]["rows"] == []
    assert d["sources"]["available"] in (True, False)


def test_no_write_side_effect(client, token, monkeypatch):
    """只读红线：不得调用任何会 CREATE TABLE / INSERT 的健康观测写方法。"""
    import modules.data_health as dh
    writes = []

    def _forbidden(*_a, **_kw):
        writes.append(1)
        raise AssertionError("diagnostics 端点不得写库")

    monkeypatch.setattr(dh, "record_health_observation", _forbidden, raising=False)
    monkeypatch.setattr(dh, "detect_stall", _forbidden, raising=False)
    resp = _get(client, token)
    assert resp.status_code == 200
    assert writes == []
