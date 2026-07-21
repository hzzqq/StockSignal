"""
tests/test_market_alert.py
--------------------------
市场指标异动提醒：检测引擎（纯逻辑）+ API 路由 + 扫描去重。

- detect_anomalies：阈值越界判定（含正向指标 severity=info、PMI/利差低位风险）。
- 路由：列表/未读计数/全部已读/管理员手动扫描。
- 扫描去重：同一指标 6h 冷却内只写一次。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User, MarketAlert  # noqa: E402
from backend.market_alert_engine import detect_anomalies, scan_and_store, _evaluate  # noqa: E402


# ──────────────────────────── 纯逻辑：detect_anomalies ────────────────────────────
def _extreme_df():
    """一列把多数规则打到 danger / info 的 DataFrame。"""
    rows = {
        "date": ["2026-07-01", "2026-07-02"],
        "adr": [1.0, 2.0],       # danger_hi 1.8
        "vix": [15.0, 35.0],      # danger_hi 30
        "pcr": [0.8, 1.5],        # danger_hi 1.2
        "zt_ratio": [2.0, 6.0],   # danger_hi 5
        "pe_pct": [60.0, 95.0],   # danger_hi 90
        "pmi": [51.0, 47.0],      # danger_lo 48
        "rsi": [50.0, 85.0],      # danger_hi 80
        "bias": [3.0, 15.0],      # danger_hi 12
        "yield_spread": [0.3, -0.5],  # danger_lo -0.2
        "nhnl": [-100.0, -600.0],  # danger_lo -500
        "north_net": [50.0, 300.0],   # positive hi -> info
        "margin_net": [20.0, 250.0],  # positive hi -> info
        "adl": [100.0, 200.0],    # 无阈值 -> 不触发
        "div_yield": [2.0, 2.0],  # 未越界 -> 不触发
    }
    return pd.DataFrame(rows)


def _quiet_df():
    rows = {
        "date": ["2026-07-01", "2026-07-02"],
        "adr": [1.0, 1.0],
        "vix": [15.0, 15.0],
        "pcr": [0.8, 0.8],
        "zt_ratio": [2.0, 2.0],
        "pe_pct": [50.0, 50.0],
        "pmi": [51.0, 51.0],
        "rsi": [50.0, 50.0],
        "bias": [3.0, 3.0],
        "yield_spread": [0.3, 0.3],
        "nhnl": [-100.0, -100.0],
        "north_net": [50.0, 50.0],
        "margin_net": [20.0, 20.0],
    }
    return pd.DataFrame(rows)


def test_detect_extreme_triggers():
    out = detect_anomalies(_extreme_df())
    by_key = {a["metric_key"]: a for a in out}
    assert "adr" in by_key and by_key["adr"]["severity"] == "danger"
    assert "vix" in by_key and by_key["vix"]["severity"] == "danger"
    assert "pmi" in by_key and by_key["pmi"]["severity"] == "danger"  # 低位风险
    assert "yield_spread" in by_key and by_key["yield_spread"]["severity"] == "danger"
    # 正向指标（北向/融资大幅净流入）severity 应为 info
    assert by_key["north_net"]["severity"] == "info"
    assert by_key["margin_net"]["severity"] == "info"
    # 无阈值/未越界指标不应出现
    assert "adl" not in by_key
    assert "div_yield" not in by_key
    # 数值与阈值应写入
    assert by_key["adr"]["value"] == 2.0
    assert by_key["adr"]["threshold"] == 1.8


def test_detect_quiet_empty():
    out = detect_anomalies(_quiet_df())
    assert out == [], f"正常区间不应产生告警：{out}"


def test_evaluate_none_value():
    rule = {"key": "vix", "name": "VIX", "warn_hi": 20, "danger_hi": 30}
    assert _evaluate(rule, None, None) is None


# ──────────────────────────── 路由 + 扫描去重（app 上下文） ────────────────────────────
@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'alert.db'}"
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
    reset_rate_limit()


def reset_rate_limit():
    try:
        from backend.utils.ratelimit import reset_rate_limit as _r
        _r()
    except Exception:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


def _token(client, username="demo"):
    r = client.post("/api/auth/login", json={"username": username, "password": "Pass@123"})
    assert r.status_code == 200, f"login failed: {r.status_code}"
    return r.get_json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_and_read_all(app, client):
    with app.app_context():
        db.session.add(MarketAlert(metric_key="vix", metric_name="VIX恐慌指数",
                                   severity="danger", message="恐慌", value=35.0, threshold=30.0))
        db.session.commit()

    tok = _token(client, "demo")
    r = client.get("/api/market-alerts", headers=_auth(tok))
    obj = r.get_json(force=True)
    assert obj["status"] == "ok"
    assert obj["data"]["unread_count"] == 1
    assert obj["data"]["total"] == 1
    assert obj["data"]["items"][0]["metric_key"] == "vix"

    # 全部已读后未读清零
    rr = client.post("/api/market-alerts/read-all", headers=_auth(tok))
    assert rr.status_code == 200
    r2 = client.get("/api/market-alerts", headers=_auth(tok))
    assert r2.get_json(force=True)["data"]["unread_count"] == 0


def test_read_requires_auth(client):
    r = client.get("/api/market-alerts")
    assert r.status_code in (401, 403)


def test_scan_requires_admin(app, client):
    demo_tok = _token(client, "demo")
    r = client.post("/api/market-alerts/scan", headers=_auth(demo_tok))
    assert r.status_code == 403  # 非 admin 禁止


def test_scan_inserts_and_dedup(app, client, monkeypatch):
    import modules.market_drivers as MD
    monkeypatch.setattr(MD, "get_market_drivers", lambda days=180: (_extreme_df(), {}))

    admin_tok = _token(client, "admin")
    # 第一次扫描：应插入多条
    r1 = client.post("/api/market-alerts/scan", headers=_auth(admin_tok))
    ins1 = r1.get_json(force=True)["data"]["inserted"]
    assert ins1 >= 10, f"首次扫描应写入多条，实际 {ins1}"

    # 立即第二次扫描：冷却期内应写入 0
    r2 = client.post("/api/market-alerts/scan", headers=_auth(admin_tok))
    ins2 = r2.get_json(force=True)["data"]["inserted"]
    assert ins2 == 0, f"冷却期内不应重复写入，实际 {ins2}"

    # 管理员可见刚才写入的告警
    rl = client.get("/api/market-alerts", headers=_auth(admin_tok))
    assert rl.get_json(force=True)["data"]["total"] >= 10
