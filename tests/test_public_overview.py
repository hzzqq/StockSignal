# -*- coding: utf-8 -*-  # noqa: UP009
"""登录页公开摘要端点守卫（GET /api/v2/read/public-overview，无鉴权）。

背景（2026-11-17 老板截图报修）：登录页左栏「资金温度 / 今日市场 / AI 信号」
此前调用 daily-snapshot（需鉴权），未登录永远拿不到 → 三面板全「—」。
修复 = 新增无鉴权脱敏摘要端点 + 登录页改接线。

本守卫锁四件事：
  1. 无 token 可访问（200），字段形状正确（温度/涨跌/AI 信号计数）；
  2. 脱敏：绝不透传持仓/推荐/梯队/评分等敏感字段；
  3. 快照缺失 → 200 not_found 优雅降级（绝不 500），绝不编造数字；
  4. 契约守卫登记 + 前端接线存在（防漂移）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402

import backend.api.read_routes as rr  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    """对齐 test_read_contract_drift.py 范式：临时库 + set_password（NOT NULL）。"""
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 't.db'}"

    app = create_app(_C)
    with app.app_context():
        db.create_all()
        u = User(username="admin", role="admin")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    with app.test_client() as c:
        yield c


def _patch_whitelist(monkeypatch, data_dir: Path):
    """保存/恢复式隔离（monkeypatch 自动还原，不做直接赋值泄漏）。"""
    wl = dict(rr._FILE_WHITELIST)
    wl["daily_snapshot"] = data_dir / "daily_snapshot.json"
    monkeypatch.setattr(rr, "_FILE_WHITELIST", wl)
    monkeypatch.setattr(rr, "_DATA_DIR", data_dir)


_FULL = {
    "date": "2026-11-17",
    "as_of": "2026-11-17T16:31:19",
    "cycle": "冰点",
    "temperature": 29.0,
    # 敏感字段：绝不允许透传到公开端点
    "position": {"sug_delta": 5},
    "score": {"total": 61},
    "ladder": {"F2": []},
    "indicators": {
        "up_count": 1216.0,
        "down_count": 3882.0,
        "limit_up": 37.0,
        "limit_down": 84.0,
        "red_ratio": 23.85,
        "median_chg": -1.266,
        "turnover_amt": 1.5e12,
    },
    "event_factor": {
        "available": True,
        "long_count": 20,
        "adj": 2,
        "as_of": "2026-11-09",
        "macro": {"available": True, "regime_score": 33},
    },
}


def test_public_overview_no_auth_ok_shape(client, monkeypatch, tmp_path):
    """无 token 可访问；字段形状对齐登录页三面板。"""
    (tmp_path / "daily_snapshot.json").write_text(
        json.dumps(_FULL, ensure_ascii=False), encoding="utf-8")
    _patch_whitelist(monkeypatch, tmp_path)
    r = client.get("/api/v2/read/public-overview")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok", body
    data = body["data"]
    assert data["date"] == "2026-11-17"
    assert data["temperature"] == 29.0
    assert data["cycle"] == "冰点"
    ind = data["indicators"]
    assert ind["up_count"] == 1216.0 and ind["down_count"] == 3882.0
    assert ind["limit_up"] == 37.0 and ind["limit_down"] == 84.0
    assert ind["red_ratio"] == 23.85 and ind["median_chg"] == -1.266
    ef = data["event_factor"]
    assert ef["long_count"] == 20 and ef["adj"] == 2 and ef["as_of"] == "2026-11-09"


def test_public_overview_sanitized_no_sensitive_fields(client, monkeypatch, tmp_path):
    """脱敏红线：持仓/评分/梯队/换手额/macro 明细绝不透传。"""
    (tmp_path / "daily_snapshot.json").write_text(
        json.dumps(_FULL, ensure_ascii=False), encoding="utf-8")
    _patch_whitelist(monkeypatch, tmp_path)
    r = client.get("/api/v2/read/public-overview")
    text = json.dumps(r.get_json(), ensure_ascii=False)
    for banned in ("position", "sug_delta", "ladder", "turnover_amt", "macro", "regime_score"):
        assert banned not in text, f"敏感字段 {banned} 泄漏进公开端点"


def test_public_overview_missing_file_graceful_200(client, monkeypatch, tmp_path):
    """快照缺失 → 200 not_found 优雅降级，绝不 500。"""
    _patch_whitelist(monkeypatch, tmp_path)
    r = client.get("/api/v2/read/public-overview")
    assert r.status_code == 200
    assert r.get_json()["status"] == "error"


def test_public_overview_partial_fields_none_not_fabricated(client, monkeypatch, tmp_path):
    """字段缺失 → None 透传（前端显「—」），绝不编造数字。"""
    (tmp_path / "daily_snapshot.json").write_text(
        json.dumps({"date": "2026-11-17", "indicators": {}}), encoding="utf-8")
    _patch_whitelist(monkeypatch, tmp_path)
    r = client.get("/api/v2/read/public-overview")
    data = r.get_json()["data"]
    assert data["temperature"] is None
    assert data["indicators"]["up_count"] is None
    assert data["event_factor"]["long_count"] is None


def test_public_overview_registered_in_contract_guard():
    """契约漂移守卫登记：新端点必须进 OBJ_ENDPOINTS 与 PublicOverviewSchema 对齐。"""
    src = (ROOT / "tests" / "test_read_contract_drift.py").read_text(encoding="utf-8")
    assert "/api/v2/read/public-overview" in src
    fe = (ROOT / "frontend-v2" / "src" / "api" / "schemas" / "read.ts").read_text(encoding="utf-8")
    assert "PublicOverviewSchema" in fe
    api = (ROOT / "frontend-v2" / "src" / "api" / "read.ts").read_text(encoding="utf-8")
    assert "getPublicOverview" in api
