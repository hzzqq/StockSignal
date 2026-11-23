# -*- coding: utf-8 -*-
"""
backend/tests/test_research_deep_qq_pb_turnover.py
—— /api/v2/read/research-deep 的 pb / turnover 真实源守卫。

腾讯单票快照 _qq_spot_single 有 60s 进程缓存，本测试直接 monkeypatch 该函数为
可控桩，零网络、零缓存污染。覆盖：
  1. 腾讯返回真实市净率/换手率 -> 真实透出；
  2. 腾讯失败 {} / 抛异常 / NaN-Inf -> pb、turnover 均为 None（不补 0、不造数）；
  3. PB=0 无业务意义 -> None；换手率 0 是合法真实值 -> 保留 0.0；
  4. deep_analysis_available 恒为 False，note 失效指引已更新且不再含 /legacy。
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


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'a.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="rdqquser", role="user")
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
        u = User.query.filter_by(username="rdqquser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _patch_other_sources(monkeypatch):
    """除 qq 外其余三源用确定性桩，隔离网络/缓存。"""
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: {
        "name": "贵州茅台", "industry": "白酒", "price": 1688.0,
        "pe_ttm": 28.1, "market_cap": 21000.0,
    })
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: None)
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": None)


def _get(client, token):
    return client.get("/api/v2/read/research-deep?code=600519", headers=_auth(token))


def test_research_deep_qq_real_pb_turnover(client, token, monkeypatch):
    _patch_other_sources(monkeypatch)
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {
        "名称": "贵州茅台", "市净率": 5.6, "换手率": 0.42,
        "量比": 1.3, "市盈率-动态": 28.5,
    })
    resp = _get(client, token)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    obj = resp.get_json()
    assert obj["status"] == "ok", obj
    d = obj["data"]
    assert d["pb"] == 5.6, f"pb 应真实透出腾讯市净率，实测 {d['pb']!r}"
    assert d["turnover"] == 0.42, f"turnover 应真实透出腾讯换手率，实测 {d['turnover']!r}"
    # 其余字段不受影响（回归护栏）
    assert d["name"] == "贵州茅台" and d["price"] == 1688.0
    assert d["market_cap"] == 21000.0 and d["pe_ttm"] == 28.1
    # deep 开关与 note 指引
    assert d["deep_analysis_available"] is False
    assert "/legacy" not in d["note"]
    assert "POST /api/tasks type=analysis" in d["note"]


def test_research_deep_qq_failure_empty_dict_honest_null(client, token, monkeypatch):
    _patch_other_sources(monkeypatch)
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {})  # 腾讯失败返 {}
    resp = _get(client, token)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert d["pb"] is None, f"腾讯失败时 pb 必须 null，实测 {d['pb']!r}"
    assert d["turnover"] is None, f"腾讯失败时 turnover 必须 null，实测 {d['turnover']!r}"
    assert d["deep_analysis_available"] is False
    # 不补 0：响应里这两个键不能是 0
    assert d["pb"] != 0 and d["turnover"] != 0


def test_research_deep_qq_exception_honest_null(client, token, monkeypatch):
    _patch_other_sources(monkeypatch)

    def boom(code):
        raise RuntimeError("腾讯快照网络故障")

    monkeypatch.setattr(rr, "_qq_spot_single", boom)
    resp = _get(client, token)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert d["pb"] is None and d["turnover"] is None
    assert d["deep_analysis_available"] is False


def test_research_deep_pb_zero_invalid_but_turnover_zero_kept(client, token, monkeypatch):
    _patch_other_sources(monkeypatch)
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {
        "市净率": 0.0, "换手率": 0.0,
    })
    resp = _get(client, token)
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["pb"] is None, f"PB=0 无业务意义必须为 null，实测 {d['pb']!r}"
    assert d["turnover"] == 0.0, f"换手率 0 是合法真实值必须保留为 0.0，实测 {d['turnover']!r}"
    # 字符串 '0' 同样按无效数值处理
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {
        "市净率": "0", "换手率": "0",
    })
    resp2 = _get(client, token)
    d2 = resp2.get_json()["data"]
    assert d2["pb"] is None
    assert d2["turnover"] == 0.0


def test_research_deep_qq_nan_inf_degraded(client, token, monkeypatch):
    _patch_other_sources(monkeypatch)
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {
        "市净率": float("nan"), "换手率": float("inf"),
    })
    resp = _get(client, token)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert d["pb"] is None and d["turnover"] is None


def test_research_deep_note_and_deep_flag_unchanged(client, token, monkeypatch):
    """即便 qq 有真值，deep 未接入事实与 note 指引也必须诚实。"""
    _patch_other_sources(monkeypatch)
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {
        "市净率": 1.2, "换手率": 3.5,
    })
    d = _get(client, token).get_json()["data"]
    assert d["deep_analysis_available"] is False
    assert "56 键异步深度分析暂未接入" in d["note"]
    assert "/legacy" not in d["note"]
    assert "POST /api/tasks type=analysis" in d["note"]
