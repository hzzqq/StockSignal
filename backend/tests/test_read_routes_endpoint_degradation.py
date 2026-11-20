# -*- coding: utf-8 -*-  # noqa: UP009
"""backend/tests/test_read_routes_endpoint_degradation.py

**健壮性守卫：只读端点上游异常时不得 500，必须 200 + 明确的 unavailable 语义。**

背景（真实缺陷）：
``/api/v2/read/breadth-divergence`` 与 ``/api/v2/read/temperature-backtest``
两个端点此前直接 import 模块并调用，**没有顶层 try/except**。一旦模块 import
失败或计算抛异常（数据文件损坏 / 依赖缺失 / 上游格式变化），整个端点直接
500 —— 与同文件其它端点（如 /strong、/theme、/dragon-tiger）"诚实降级、
不 500" 的既有约定不一致。

修复后的契约：
- 异常 → 仍 200，信封合法；
- 顶层 ``available=false`` + ``unavailable`` 标注失败原因 + ``reason`` 说明；
- 分段结构保持与正常路径同形（前端 zod 契约要求这些键存在）；
- 异常**必须落日志**（不得静默吞掉；T-239 守卫要求 except 分支有日志或
  ui_audit_exempt 标注）。

本文件用 monkeypatch 让模块函数抛异常，验证端点降级行为（零网络）。
"""
from __future__ import annotations

import logging
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'degrade.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="degrade", role="user")
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
        u = User.query.filter_by(username="degrade").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _assert_envelope_ok(resp):
    assert resp.status_code == 200, f"异常必须降级为 200，不得 500：{resp.status_code}"
    body = resp.get_json()
    assert body["status"] == "ok", body
    for k in ("status", "code", "message", "data"):
        assert k in body, f"信封缺字段 {k}: {body}"
    return body["data"]


# ─────────────────── breadth-divergence ───────────────────
def test_breadth_divergence_exception_returns_200_unavailable(client, token, monkeypatch):
    """模块计算抛异常 → 200 + available=false + unavailable 标注。"""
    import modules.breadth_divergence as bd

    def _boom(*_a, **_k):
        raise RuntimeError("上游数据损坏")

    monkeypatch.setattr(bd, "breadth_calendar", _boom)

    resp = client.get("/api/v2/read/breadth-divergence", headers=_auth(token))
    data = _assert_envelope_ok(resp)

    assert data["available"] is False, "异常时顶层必须 available=false"
    assert data["unavailable"] == ["breadth_divergence_failed"]
    assert "RuntimeError" in data["reason"]
    # 分段结构保持同形（前端 zod 契约要求这些键存在）
    assert data["calendar"]["available"] is False
    assert data["divergence"]["available"] is False
    assert data["trend"]["available"] is False
    assert data["calendar"]["z"] == []
    assert data["divergence"]["episodes"] == []
    assert data["trend"]["dates"] == []


def test_breadth_divergence_logs_exception(client, token, monkeypatch, caplog):
    """异常必须落日志（不得静默吞掉）。"""
    import modules.breadth_divergence as bd

    def _boom(*_a, **_k):
        raise RuntimeError("上游数据损坏")

    monkeypatch.setattr(bd, "breadth_calendar", _boom)

    with caplog.at_level(logging.WARNING, logger="backend.api.read_routes"):
        client.get("/api/v2/read/breadth-divergence", headers=_auth(token))

    assert any("breadth-divergence" in r.message for r in caplog.records), \
        "异常必须留痕（不得静默吞异常）"


def test_breadth_divergence_validation_still_422(client, token):
    """参数校验优先级不变：非法参数仍是 422（不是 200 降级）。"""
    resp = client.get("/api/v2/read/breadth-divergence?red_thresh=999", headers=_auth(token))
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["code"] == "validation_error"


# ─────────────────── temperature-backtest ───────────────────
def test_temperature_backtest_exception_returns_200_unavailable(client, token, monkeypatch):
    """模块计算抛异常 → 200 + available=false + unavailable 标注。"""
    import modules.temperature_backtest as tb

    def _boom(*_a, **_k):
        raise RuntimeError("温度档计算失败")

    monkeypatch.setattr(tb, "band_backtest", _boom)

    resp = client.get("/api/v2/read/temperature-backtest", headers=_auth(token))
    data = _assert_envelope_ok(resp)

    assert data["available"] is False
    assert data["unavailable"] == ["temperature_backtest_failed"]
    assert "RuntimeError" in data["reason"]
    # 不可用时不得伪造统计字段
    assert data.get("bands") is None
    assert data.get("baseline") is None


def test_temperature_backtest_logs_exception(client, token, monkeypatch, caplog):
    """异常必须落日志（不得静默吞掉）。"""
    import modules.temperature_backtest as tb

    def _boom(*_a, **_k):
        raise RuntimeError("温度档计算失败")

    monkeypatch.setattr(tb, "band_backtest", _boom)

    with caplog.at_level(logging.WARNING, logger="backend.api.read_routes"):
        client.get("/api/v2/read/temperature-backtest", headers=_auth(token))

    assert any("temperature-backtest" in r.message for r in caplog.records), \
        "异常必须留痕（不得静默吞异常）"


def test_temperature_backtest_validation_still_422(client, token):
    """参数校验优先级不变：非法窗口仍是 422。"""
    resp = client.get("/api/v2/read/temperature-backtest?window_days=0", headers=_auth(token))
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["code"] == "validation_error"


# ─────────────────── 回归：正常路径不受影响 ───────────────────
def test_breadth_divergence_normal_path_still_works(client, token, monkeypatch):
    """正常路径仍然透传模块结果（不被新的 try/except 影响）。"""
    import modules.breadth_divergence as bd

    cal = {"available": True, "years": [2025], "months": list(range(1, 13)),
           "z": [[1.0] * 12], "latest_year": 2025}
    div = {"available": True, "threshold_red": 50.0, "ld_p90": 0.5,
           "episodes": [], "current": None, "n_episodes": 0}
    trend = {"available": True, "dates": ["2025-01-02"], "red_ratio": [55.5], "limit_down": [3]}

    monkeypatch.setattr(bd, "breadth_calendar", lambda: cal)
    monkeypatch.setattr(bd, "divergence_episodes", lambda **_k: div)
    monkeypatch.setattr(bd, "breadth_trend", lambda **_k: trend)

    resp = client.get("/api/v2/read/breadth-divergence", headers=_auth(token))
    data = _assert_envelope_ok(resp)
    assert data["available"] is True
    assert data["calendar"] == cal
    assert data["divergence"] == div
    assert data["trend"] == trend


def test_temperature_backtest_normal_path_still_works(client, token, monkeypatch):
    """正常路径仍然原样透传 band_backtest 结果。"""
    import modules.temperature_backtest as tb

    result = {"available": True, "reason": None,
              "data": {"rows": 100, "start": "2025-01-01", "end": "2025-06-30"},
              "baseline": {"n": 95}, "bands": [], "note": "方法学声明"}
    monkeypatch.setattr(tb, "band_backtest", lambda **_k: result)

    resp = client.get("/api/v2/read/temperature-backtest", headers=_auth(token))
    data = _assert_envelope_ok(resp)
    assert data == result
