"""形态扫描后端化验收测试（pure function + 端点）。

测试夹具说明：
  * 本文件所有 K 线均为**合成确定性夹具，非真实行情**，仅用于验证算法语义与降级；
  * FLAT_V：长期平稳 + 末端急跌急涨，稳定触发 MACD金叉/均线金叉/KDJ金叉/底背离。

端点层用真 Flask test_client + 独立临时 SQLite + 真 JWT；禁止 pytest.skip，禁止仅断言 200。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import modules.pattern_scan as ps  # noqa: E402
import modules.technical as technical  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402


# ── 合成确定性 K 线夹具（非真实行情）──
def _flat_then_v_rows() -> list[dict]:
    vals = [100.0] * 60 + [90, 85, 80, 90, 100, 110, 120, 125]
    return [
        {
            "date": f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}",
            "open": c - 0.5, "high": c + 1.0, "low": c - 1.0, "close": c,
        }
        for i, c in enumerate(vals)
    ]


FLAT_V = _flat_then_v_rows()
BASE = {"date": "2025-12-01", "name": "锤子线", "bias": "看涨", "desc": "测试夹具基础形态"}


def _to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if "ma5" not in df.columns:
        df["ma5"] = df["close"].rolling(5).mean()
    if "ma20" not in df.columns:
        df["ma20"] = df["close"].rolling(20).mean()
    return df.reset_index(drop=True)


# ───────────── 1. detect_advanced_patterns ─────────────
def test_detect_advanced_patterns_macd_golden_cross():
    pats = ps.detect_advanced_patterns(_to_df(FLAT_V))
    assert any(p["name"] == "MACD金叉" and p["bias"] == "看涨" for p in pats), pats


def test_detect_advanced_patterns_insufficient_bars():
    assert ps.detect_advanced_patterns(_to_df(FLAT_V[:20])) == []
    assert ps.detect_advanced_patterns(pd.DataFrame({"close": [1, 2]})) == []


def test_detect_advanced_patterns_swallows_internal_exception():
    df = _to_df(FLAT_V).drop(columns=["date"])  # 缺 date -> 组装形态时 KeyError，须内部吞掉
    assert ps.detect_advanced_patterns(df) == []


# ───────────── 2. merge_patterns ─────────────
def test_merge_advanced_exception_keeps_base_patterns(monkeypatch):
    monkeypatch.setattr(technical, "full_analysis", lambda df: {"patterns": [dict(BASE)]})

    def boom(df):
        raise RuntimeError("advanced boom")

    monkeypatch.setattr(ps, "detect_advanced_patterns", boom)
    out = ps.merge_patterns(_to_df(FLAT_V))
    assert out == [BASE], out


def test_merge_dedup_and_truncate_to_eight(monkeypatch):
    base = [
        {"date": f"2025-12-{i:02d}", "name": f"基础{i}", "bias": "看涨", "desc": ""}
        for i in range(10, 0, -1)
    ]
    monkeypatch.setattr(technical, "full_analysis", lambda df: {"patterns": base})
    adv = [
        {"date": "2025-12-11", "name": "MACD金叉", "bias": "看涨", "desc": ""},
        {"date": "2025-12-09", "name": "基础8", "bias": "看涨", "desc": ""},  # 与 base 重复
    ]
    monkeypatch.setattr(ps, "detect_advanced_patterns", lambda df: adv)

    out = ps.merge_patterns(_to_df(FLAT_V))
    assert len(out) == 8, out
    keys = [(p["name"], p["bias"]) for p in out]
    assert len(keys) == len(set(keys)), keys
    assert keys.count(("基础8", "看涨")) == 1, keys
    assert out[0]["name"] == "MACD金叉", out
    dates = [p["date"] for p in out]
    assert dates == sorted(dates, reverse=True), dates


# ───────────── 3. scan_patterns ─────────────
def test_scan_patterns_happy_path():
    r = ps.scan_patterns(FLAT_V)
    assert r["available"] is True, r
    assert r["reason"] is None, r
    assert r["n_bars"] == len(FLAT_V), r
    assert any(p["name"] == "MACD金叉" for p in r["patterns"]), r


@pytest.mark.parametrize("klines,expected_n,reason_part", [
    ([], 0, "空"),
    (None, 0, "空"),
    ("not-a-list", 0, "空"),
    (FLAT_V[:20], 20, "35"),
])
def test_scan_patterns_honest_degradation(klines, expected_n, reason_part):
    r = ps.scan_patterns(klines)
    assert r["available"] is False, r
    assert r["patterns"] == [], r
    assert r["n_bars"] == expected_n, r
    assert reason_part in r["reason"], r


def test_scan_patterns_missing_required_field():
    rows = [
        {k: v for k, v in row.items() if k != "close"}  # 35 行但缺 close
        for row in FLAT_V[:35]
    ]
    r = ps.scan_patterns(rows)
    assert r["available"] is False and r["patterns"] == [], r
    assert r["n_bars"] == 35 and "缺少" in r["reason"], r


def test_scan_patterns_exception_degrades(monkeypatch):
    def boom(df):
        raise RuntimeError("merge boom")

    monkeypatch.setattr(ps, "merge_patterns", boom)
    r = ps.scan_patterns(FLAT_V)
    assert r["available"] is False, r
    assert r["patterns"] == [], r
    assert r["reason"], r


# ───────────── 4. 端点（真 Flask test_client + 临时 SQLite + JWT）─────────────
@pytest.fixture
def app(tmp_path, monkeypatch):
    db_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file.as_posix()}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    # team-lead 会在 backend/app.py 统一注册本 blueprint；此处条件注册保证测试在当前
    # worktree（app.py 尚未改）也能跑，且未来 app.py 注册后不会重复注册。
    from backend.api.pattern_routes import bp as pattern_bp

    if "pattern" not in application.blueprints:
        application.register_blueprint(pattern_bp)

    with application.app_context():
        db.create_all()
        if User.query.filter_by(username="demo").first() is None:
            u = User(username="demo", role="user")
            u.set_password("Pass@123")
            db.session.add(u)
            db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Pass@123"})
    assert r.status_code == 200, f"登录失败: {r.status_code} {r.text[:300]}"
    token = r.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _install_fetch(monkeypatch, fail_codes=(), calls=None, klines=None):
    import backend.api.pattern_routes as pr

    data = klines if klines is not None else FLAT_V

    def fake(code, window_days):
        if calls is not None:
            calls[code] = window_days
        if code in fail_codes:
            raise RuntimeError("boom")
        return data

    monkeypatch.setattr(pr, "_load_klines", fake)


def _assert_validation_422(r):
    assert r.status_code == 422, f"期望 422，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert j["status"] == "error" and j["code"] == "validation_error", j
    assert j["data"] is None, j


def test_pattern_scan_happy_path(client, auth, monkeypatch):
    calls = {}
    _install_fetch(monkeypatch, calls=calls)
    r = client.post(
        "/api/v2/pattern-scan",
        json={"codes": ["600519", "000001"], "window_days": 120},
        headers=auth,
    )
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok" and j["code"] == "ok", j
    d = j["data"]
    assert set(d) == {"results", "n_scanned", "available"}, d
    assert d["n_scanned"] == 2, d
    assert d["available"] is True, d
    assert [x["code"] for x in d["results"]] == ["600519", "000001"], d
    for item in d["results"]:
        assert set(item) == {"code", "available", "patterns", "reason", "n_bars"}, item
        assert item["available"] is True and item["reason"] is None, item
        assert item["n_bars"] == len(FLAT_V), item
        assert any(p["name"] == "MACD金叉" for p in item["patterns"]), item
    assert calls == {"600519": 120, "000001": 120}, calls


def test_pattern_scan_drops_blank_codes(client, auth, monkeypatch):
    calls = {}
    _install_fetch(monkeypatch, calls=calls)
    r = client.post(
        "/api/v2/pattern-scan",
        json={"codes": ["", "  600519  ", "", "000001"]},
        headers=auth,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["n_scanned"] == 2, d
    assert [x["code"] for x in d["results"]] == ["600519", "000001"], d
    assert list(calls) == ["600519", "000001"], calls


@pytest.mark.parametrize("body", [
    {"codes": []},
    {"codes": ["", "   "]},  # 去空后为空
    {"codes": ["600519"] * 51},  # 超过 50
    {"codes": "600519"},  # 非数组
    {"codes": ["ABCDEF"]},  # 形状非法
    {"codes": ["600519"], "window_days": 0},
    {"codes": ["600519"], "window_days": 5001},
    {"codes": ["600519"], "window_days": "abc"},
    {"codes": ["600519"], "window_days": 1.5},
    ["not-a-dict"],
])
def test_pattern_scan_invalid_params_422(client, auth, monkeypatch, body):
    _install_fetch(monkeypatch)
    r = client.post("/api/v2/pattern-scan", json=body, headers=auth)
    _assert_validation_422(r)


def test_pattern_scan_no_token_401(client, monkeypatch):
    _install_fetch(monkeypatch)
    r = client.post("/api/v2/pattern-scan", json={"codes": ["600519"]})
    assert r.status_code == 401, f"期望 401，实得 {r.status_code}: {r.text[:300]}"
    assert r.get_json()["status"] == "error", r.get_json()


def test_pattern_scan_single_code_failure_does_not_abort(client, auth, monkeypatch):
    _install_fetch(monkeypatch, fail_codes={"000001"})
    r = client.post(
        "/api/v2/pattern-scan",
        json={"codes": ["600519", "000001", "300750"]},
        headers=auth,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["n_scanned"] == 3, d
    assert d["available"] is True, d
    by_code = {x["code"]: x for x in d["results"]}
    failed = by_code["000001"]
    assert failed["available"] is False and failed["patterns"] == [], failed
    assert failed["reason"] and "K线获取失败" in failed["reason"], failed
    # 失败股不中断整批：其余两只仍扫出形态
    for code in ("600519", "300750"):
        assert by_code[code]["available"] is True, by_code[code]
        assert any(p["name"] == "MACD金叉" for p in by_code[code]["patterns"]), by_code[code]
