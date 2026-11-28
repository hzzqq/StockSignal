# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_thesis_evidence_route.py — 毕设证据端点守卫（v2 /thesis 数据源）。

验证：
  1. 成功聚合三块（findings / ch6 / shap），负向 verdict 原样透出不美化；
  2. summarize_findings 异常 → 只降级 findings 块，其余块仍可用；
  3. ch6 metrics 文件缺失 → available=False + note 诚实说明，不补 0；
  4. SHAP 归因失败 → available=False + reason，baseline/adjustments 诚实 null/空；
  5. 未登录 → 401。

诚实红线：#2 GNN 负向 0.4948 / #3 RL 负向 Sharpe -0.741 必须如实出现，
不得包装成突破；ch6 小样本 note 原样带出。
"""
from __future__ import annotations

import json
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
import modules.experiment_improvements as ei  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path_factory.mktemp('thdb') / 'a.db'}"

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="thuser", role="user")
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
        u = User.query.filter_by(username="thuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


METRICS = {
    "snapshot_count": 41,
    "snapshot_date_range": ["2026-08-31", "2026-11-23"],
    "prediction_count": 41,
    "prediction_scored": 24,
    "prediction_hit_rate": 0.375,
    "note": "样本量小时如实标注，不推断统计显著性",
}


def _point_ch6_to(tmp_path, monkeypatch, content=None):
    """把 ch6 metrics 常量指向临时文件；content=None 表示文件不存在。"""
    p = tmp_path / "metrics.json"
    if content is not None:
        p.write_text(json.dumps(content), encoding="utf-8")
    monkeypatch.setattr(rr, "_THESIS_CH6_METRICS", p)


def _point_snapshot_to(tmp_path, monkeypatch, snap):
    """把 daily_snapshot 白名单路径指向临时快照。"""
    p = tmp_path / "daily_snapshot.json"
    p.write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setitem(rr._FILE_WHITELIST, "daily_snapshot", p)


SNAP = {
    "date": "2026-11-27", "temperature": 87.1, "score": 87.1,
    "bias": "偏多", "cycle": "主升高潮", "promo_overall": 43.1,
}


def test_thesis_evidence_ok_all_blocks(client, token, tmp_path, monkeypatch):
    """三块聚合成功；负向 verdict 原样透出；ch6 小样本 note 带出。"""
    _point_ch6_to(tmp_path, monkeypatch, METRICS)
    _point_snapshot_to(tmp_path, monkeypatch, SNAP)
    resp = client.get("/api/v2/read/thesis-evidence", headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok"
    d = obj["data"]

    # ① 三算法证据（真值来自 KNOWN_FINDINGS）
    findings = d["findings"]
    f = findings["findings"]
    assert f["transformer_signal"]["verdict"] == "modest_positive"
    assert f["transformer_signal"]["direction_hit"] == 0.5130
    assert f["gnn_factor"]["verdict"] == "negative"
    assert f["gnn_factor"]["direction_hit"] == 0.4948
    assert f["rl_position"]["verdict"] == "negative"
    assert f["rl_position"]["sharpe"] == -0.741
    assert findings["decision_closure_anchor"]["accuracy"] == 0.491
    assert "风险缩放器" in findings["asymmetric_finding"]["note"]

    # ② ch6 评估（41 快照 / 37.5%，小样本 note 原样）
    assert d["ch6"]["available"] is True
    assert d["ch6"]["metrics"]["snapshot_count"] == 41
    assert d["ch6"]["metrics"]["prediction_hit_rate"] == 0.375
    assert "样本量小" in d["ch6"]["metrics"]["note"]

    # ③ SHAP 加性归因：基准 + 调节 = 最终
    shap = d["shap_attribution"]
    assert shap["available"] is True
    assert shap["as_of"] == "2026-11-27"
    assert isinstance(shap["adjustments"], dict)
    assert shap["baseline"] is not None
    assert shap["final_running"] is not None
    assert abs(shap["baseline"] + shap["adjustments_total"] - shap["final_running"]) < 0.1

    assert "负向" in d["note"] or "不包装" in d["note"]


def test_findings_failure_only_degrades_that_block(client, token, tmp_path, monkeypatch):
    """findings 聚合异常 → 只该块降级，ch6/shap 仍可用。"""
    def _boom():
        raise RuntimeError("findings exploded")

    monkeypatch.setattr(ei, "summarize_findings", _boom)
    _point_ch6_to(tmp_path, monkeypatch, METRICS)
    _point_snapshot_to(tmp_path, monkeypatch, SNAP)
    resp = client.get("/api/v2/read/thesis-evidence", headers=_auth(token))
    assert resp.status_code == 200  # 绝不 500
    d = resp.get_json()["data"]
    assert d["findings"]["available"] is False
    assert "findings exploded" in d["findings"]["reason"]
    assert d["ch6"]["available"] is True  # 其余块不受影响
    assert d["shap_attribution"]["available"] is True


def test_ch6_missing_honest(client, token, tmp_path, monkeypatch):
    """ch6 文件缺失 → available=False + note，不补 0。"""
    _point_ch6_to(tmp_path, monkeypatch, None)  # 不写文件
    _point_snapshot_to(tmp_path, monkeypatch, SNAP)
    resp = client.get("/api/v2/read/thesis-evidence", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["ch6"]["available"] is False
    assert d["ch6"]["metrics"] is None
    assert "未做任何填充" in d["ch6"]["note"]


def test_shap_failure_honest(client, token, tmp_path, monkeypatch):
    """快照缺失 → SHAP available=False + reason，baseline/adjustments 诚实空。"""
    _point_ch6_to(tmp_path, monkeypatch, METRICS)
    p = tmp_path / "empty_snapshot.json"
    p.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setitem(rr._FILE_WHITELIST, "daily_snapshot", p)
    resp = client.get("/api/v2/read/thesis-evidence", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    shap = d["shap_attribution"]
    assert shap["available"] is False
    assert shap["baseline"] is None
    assert shap["adjustments"] == {}
    assert shap["reason"]


def test_thesis_evidence_requires_token(client):
    resp = client.get("/api/v2/read/thesis-evidence")
    assert resp.status_code == 401
