"""
backend/tests/test_event_backtest.py
------------------------------------
事件因子回测模块（modules.event_backtest）单元测试 + 端点集成冒烟。

覆盖（诚实红线 / 稳健性）：
  1. 参数非法 → run() 返回 available=False 带 reason（不抛异常）；
  2. NaN 指标日 → 跳过、不计入窗口、不崩溃；
  3. 小样本触发（n_event < MIN_N）→ z=None、edge 仍计算、诚实 note 存在；
  4. 退化常量序列 → 不 500、结构合法（base_rate 可能为 None，显式弃权）；
  5. 输出结构：distribution 长度 = N_BINS，example_dates ≤ 10；
  6. 端点：合法 200 + 信封合法；非法 metric/quantile/horizon → 400；无 token → 401。
"""
from __future__ import annotations

import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import modules.event_backtest as eb  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.models import User  # noqa: E402


# ── 合成数据工具：控制 limit_down_ratio 与红/绿日 ──────────────────────────
def _rec(date: str, red: bool, limit_down_ratio: float):
    up = 1500 if red else 500
    down = 500 if red else 1500
    total = up + down  # flat=0
    limit_down = round(limit_down_ratio / 100.0 * total, 2)
    return dict(
        date=date,
        up_count=up,
        down_count=down,
        flat_count=0,
        limit_up=10.0,
        limit_down=limit_down,
        red_ratio=round(up / (up + down) * 100, 4),
    )


def _make_series(n_normal=400, n_extreme=10):
    recs = []
    # 前 n_normal 天：红绿交替（基准率≈0.5），limit_down_ratio=0.2%
    for i in range(n_normal):
        recs.append(_rec(f"2020-{1 + i // 30:02d}-{1 + i % 28:02d}", red=(i % 2 == 0), limit_down_ratio=0.2))
    # 后 n_extreme 天：全红、limit_down_ratio=9%（极端，落在历史前 10%）
    for j in range(n_extreme):
        recs.append(_rec(f"2022-{1 + j // 30:02d}-{1 + j % 28:02d}", red=True, limit_down_ratio=9.0))
    return recs


@pytest.fixture
def patch_series(monkeypatch):
    def _patch(recs):
        monkeypatch.setattr(eb, "_load_series", lambda: (recs, None))
    return _patch


# ── 1. 参数非法 ───────────────────────────────────────────────────────────
def test_invalid_params_return_available_false():
    assert eb.run("bad_metric", 0.1, "high", 1)["available"] is False
    assert eb.run("limit_down_ratio", 0.0, "high", 1)["available"] is False
    assert eb.run("limit_down_ratio", 1.0, "high", 1)["available"] is False
    assert eb.run("limit_down_ratio", 0.1, "sideways", 1)["available"] is False
    assert eb.run("limit_down_ratio", 0.1, "high", 7)["available"] is False


# ── 2. NaN 指标日跳过 ─────────────────────────────────────────────────────
def test_nan_metric_skipped(patch_series):
    recs = _make_series()
    recs[300]["limit_down"] = float("nan")  # 一天指标 NaN
    patch_series(recs)
    out = eb.run("limit_down_ratio", 0.1, "high", 1)
    assert out["available"] is True
    assert isinstance(out["n_event"], int) and out["n_event"] >= 1
    # 不崩溃、分布结构完整
    assert len(out["distribution"]) == eb.N_BINS


# ── 3. 小样本触发 → z=None ────────────────────────────────────────────────
def test_small_sample_no_z(patch_series):
    recs = _make_series(n_normal=400, n_extreme=10)  # 触发约 10 天 < MIN_N=30
    patch_series(recs)
    out = eb.run("limit_down_ratio", 0.1, "high", 1)
    assert out["available"] is True
    assert 1 <= out["n_event"] < eb.MIN_N
    assert out["z"] is None  # 样本不足，不报显著性
    assert any("z" in n or "显著性" in n for n in out["honesty_notes"])


# ── 4. 退化常量序列不崩溃 ─────────────────────────────────────────────────
def test_degenerate_constant_no_crash(patch_series):
    recs = [_rec(f"2020-01-{i+1:02d}", red=(i % 2 == 0), limit_down_ratio=0.2) for i in range(400)]
    patch_series(recs)
    out = eb.run("limit_down_ratio", 0.1, "high", 1)
    assert out["available"] is True  # 不抛异常
    assert len(out["distribution"]) == eb.N_BINS
    assert "method" in out and "honesty_notes" in out


# ── 5. 输出结构 ───────────────────────────────────────────────────────────
def test_output_structure(patch_series):
    recs = _make_series(n_normal=600, n_extreme=20)  # 触发 20 天，仍 < MIN_N
    patch_series(recs)
    out = eb.run("limit_down_ratio", 0.1, "high", 3)
    assert set(["available", "n_event", "n_base", "base_rate", "event_rate",
                "edge_pp", "z", "distribution", "example_dates", "method",
                "honesty_notes"]).issubset(out)
    assert all("event_count" in b and "base_count" in b and "bucket" in b
               for b in out["distribution"])
    assert len(out["example_dates"]) <= 10
    for ex in out["example_dates"]:
        assert {"date", "metric_value", "forward_red_day_frac"}.issubset(ex)


# ── 6. 端点集成 ───────────────────────────────────────────────────────────
@pytest.fixture
def app():
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 't.db')}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        for uname, role in (("admin", "admin"), ("demo", "user")):
            if User.query.filter_by(username=uname).first() is None:
                u = User(username=uname, role=role)
                u.set_password("Pass@123")
                db.session.add(u)
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _token(client, username="demo", password="Pass@123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


def test_endpoint_valid_envelope(client):
    tok = _token(client)
    hdr = {"Authorization": f"Bearer {tok}"}
    r = client.get(
        "/api/v2/read/event-backtest?metric=limit_down_ratio&quantile=0.1&direction=high&horizon=1",
        headers=hdr,
    )
    assert r.status_code == 200, r.text[:200]
    j = r.get_json()
    for k in ("status", "code", "message", "data"):
        assert k in j, f"信封缺 {k}: {j}"
    assert isinstance(j["data"], dict)
    assert j["data"]["available"] in (True, False)


def test_endpoint_invalid_params_400(client):
    tok = _token(client)
    hdr = {"Authorization": f"Bearer {tok}"}
    for bad in (
        "/api/v2/read/event-backtest?metric=BAD",
        "/api/v2/read/event-backtest?quantile=2",
        "/api/v2/read/event-backtest?horizon=7",
        "/api/v2/read/event-backtest?direction=up",
    ):
        r = client.get(bad, headers=hdr)
        assert r.status_code == 400, f"{bad} 应 400，实得 {r.status_code} {r.text[:200]}"


def test_endpoint_requires_token(client):
    r = client.get("/api/v2/read/event-backtest?metric=limit_down_ratio&quantile=0.1")
    assert r.status_code == 401, r.text[:200]
    assert r.get_json().get("code") == "missing_token", r.text[:200]
