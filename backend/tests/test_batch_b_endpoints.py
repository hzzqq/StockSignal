"""
backend/tests/test_batch_b_endpoints.py
---------------------------------------
Parity B 批次后端端点真实验收测试。

覆盖：
  * 4 个新端点 happy path（真实 Flask test_client + 真实 JWT）；
  * 每个端点参数非法 → 422 validation_error（不是 400，也不是 500）；
  * 两个写端点的「写入后立刻 GET 回读一致」；
  * 看板 widgets 顺序原样保留、review-notes 全文覆盖语义；
  * 算法端点在数据源缺失时 available:false 原样透出（monkeypatch 模块函数）。

隔离约束：
  * 独立临时 SQLite（不碰 backend/data/app.db）；
  * read_routes._DATA_DIR / _FILE_WHITELIST["user_dashboard"] 均 monkeypatch 到 pytest
    tmp_path，任何写入只落在临时目录，绝不写主区 data/；
  * 算法端点用桩函数替掉模块纯函数，不读真实历史数据，确定性可重复；
  * 禁止 pytest.skip，禁止仅断言 status==200 的伪测试。
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

from backend.api import read_routes  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402

# ── 桩返回（结构与 modules 的真实返回一致，便于逐字段透出断言）──
CAL = {
    "available": True, "years": [2024, 2025], "months": list(range(1, 13)),
    "z": [[1.0] * 12, [2.0] * 12], "latest_year": 2025,
}
DIV = {
    "available": True, "threshold_red": 50.0, "ld_p90": 0.5,
    "episodes": [{"date": "2025-01-02", "red_ratio": 60.0, "limit_down": 5}],
    "current": {"date": "2025-01-03", "is_divergent": False}, "n_episodes": 1,
}
TREND = {
    "available": True, "dates": ["2025-01-02"], "red_ratio": [55.5], "limit_down": [3],
}
CAL_OFF = {
    "available": False, "years": [], "months": list(range(1, 13)), "z": [], "latest_year": None,
}
DIV_OFF = {
    "available": False, "threshold_red": 50.0, "ld_p90": None,
    "episodes": [], "current": None, "n_episodes": 0,
}
TREND_OFF = {"available": False, "dates": [], "red_ratio": [], "limit_down": []}

BACKTEST = {
    "available": True, "reason": None,
    "data": {"rows": 100, "start": "2025-01-01", "end": "2025-06-30"},
    "baseline": {"n": 95, "next_impr_rate": 50.0},
    "bands": [{"level": 0, "available": False, "n": 0}],
    "note": "测试用方法学声明",
}
BACKTEST_OFF = {"available": False, "reason": "广度历史为空（数据缺失）"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    """真实 Flask app + 独立 SQLite；数据根重定向到 tmp_path。"""
    db_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(read_routes, "_DATA_DIR", data_dir)
    monkeypatch.setitem(
        read_routes._FILE_WHITELIST, "user_dashboard", data_dir / "user_dashboard.json"
    )

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file.as_posix()}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
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


def _install_bd(monkeypatch, cal=CAL, div=DIV, trend=TREND, calls=None):
    """把 breadth_divergence 三个纯函数替换为桩，并记录传入参数。"""
    import modules.breadth_divergence as bd

    def f_cal():
        if calls is not None:
            calls["calendar"] = True
        return cal

    def f_div(red_thresh, ld_quantile):
        if calls is not None:
            calls["divergence"] = (red_thresh, ld_quantile)
        return div

    def f_trend(window_days):
        if calls is not None:
            calls["trend"] = window_days
        return trend

    monkeypatch.setattr(bd, "breadth_calendar", f_cal)
    monkeypatch.setattr(bd, "divergence_episodes", f_div)
    monkeypatch.setattr(bd, "breadth_trend", f_trend)


def _install_tb(monkeypatch, result=BACKTEST, calls=None):
    """把 temperature_backtest.band_backtest 替换为桩，并记录 window_days。"""
    import modules.temperature_backtest as tb

    def f(window_days):
        if calls is not None:
            calls["window_days"] = window_days
        return result

    monkeypatch.setattr(tb, "band_backtest", f)


def _assert_validation_422(r):
    assert r.status_code == 422, f"期望 422，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert isinstance(j, dict), f"响应非 JSON: {r.text[:300]}"
    assert j["status"] == "error", j
    assert j["code"] == "validation_error", j
    assert j["data"] is None, f"校验失败不得返回假数据: {j}"


# ───────────────── 1. breadth-divergence ─────────────────
def test_breadth_divergence_happy_path_forwards_params(client, auth, monkeypatch):
    calls = {}
    _install_bd(monkeypatch, calls=calls)
    r = client.get(
        "/api/v2/read/breadth-divergence?red_thresh=60&ld_quantile=0.8&window_days=120",
        headers=auth,
    )
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok", j
    d = j["data"]
    assert set(d) == {"available", "calendar", "divergence", "trend"}, d
    assert d["available"] is True, d
    assert d["calendar"] == CAL, d
    assert d["divergence"] == DIV, d
    assert d["trend"] == TREND, d
    # 真正把参数透传给模块函数，而不是写死默认值
    assert calls.get("calendar") is True, calls
    assert calls["divergence"] == (60.0, 0.8), calls
    assert calls["trend"] == 120, calls


def test_breadth_divergence_defaults(client, auth, monkeypatch):
    calls = {}
    _install_bd(monkeypatch, calls=calls)
    r = client.get("/api/v2/read/breadth-divergence", headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert calls["divergence"] == (50.0, 0.9), calls
    assert calls["trend"] == 750, calls


@pytest.mark.parametrize("query", [
    "red_thresh=-1", "red_thresh=101", "red_thresh=abc", "red_thresh=nan",
    "ld_quantile=0", "ld_quantile=1", "ld_quantile=abc",
    "window_days=0", "window_days=5001", "window_days=abc", "window_days=1.5",
])
def test_breadth_divergence_invalid_params_422(client, auth, monkeypatch, query):
    _install_bd(monkeypatch)
    r = client.get(f"/api/v2/read/breadth-divergence?{query}", headers=auth)
    _assert_validation_422(r)


def test_breadth_divergence_honest_degradation(client, auth, monkeypatch):
    _install_bd(monkeypatch, CAL_OFF, DIV_OFF, TREND_OFF)
    r = client.get("/api/v2/read/breadth-divergence", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is False, d
    assert d["calendar"] == CAL_OFF, d
    assert d["divergence"] == DIV_OFF, d
    assert d["trend"] == TREND_OFF, d
    # 缺失时不得伪造分化日 / 热力矩阵 / 趋势点
    assert d["divergence"]["episodes"] == [], d
    assert d["calendar"]["z"] == [], d
    assert d["trend"]["dates"] == [], d


# ───────────────── 2. temperature-backtest ─────────────────
def test_temperature_backtest_happy_path_passthrough(client, auth, monkeypatch):
    calls = {}
    _install_tb(monkeypatch, calls=calls)
    r = client.get("/api/v2/read/temperature-backtest?window_days=250", headers=auth)
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok", j
    assert j["data"] == BACKTEST, j["data"]
    assert calls["window_days"] == 250, calls


def test_temperature_backtest_default_window_is_none(client, auth, monkeypatch):
    calls = {}
    _install_tb(monkeypatch, calls=calls)
    r = client.get("/api/v2/read/temperature-backtest", headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert calls["window_days"] is None, calls
    assert r.get_json()["data"] == BACKTEST


@pytest.mark.parametrize("query", ["window_days=0", "window_days=5001", "window_days=abc", "window_days=-5"])
def test_temperature_backtest_invalid_window_422(client, auth, monkeypatch, query):
    _install_tb(monkeypatch)
    r = client.get(f"/api/v2/read/temperature-backtest?{query}", headers=auth)
    _assert_validation_422(r)


def test_temperature_backtest_honest_degradation(client, auth, monkeypatch):
    _install_tb(monkeypatch, BACKTEST_OFF)
    r = client.get("/api/v2/read/temperature-backtest", headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert r.get_json()["data"] == BACKTEST_OFF


# ───────────────── 3. user-dashboard PUT ─────────────────
def test_user_dashboard_put_then_get_readback_keeps_order(client, auth, tmp_path):
    # 使用 v2 组件稳定 id；故意非字典序，验证用户传入顺序被原样保留
    widgets = ["breadth", "snapshot"]
    r = client.put("/api/v2/read/user-dashboard", json={"widgets": widgets}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert r.get_json()["data"] == {"widgets": widgets}

    get_r = client.get("/api/v2/read/user-dashboard", headers=auth)
    assert get_r.status_code == 200, get_r.text[:300]
    assert get_r.get_json()["data"] == {"widgets": widgets}

    # 落盘内容精确为 {"widgets": [...]}，顺序一致
    fp = tmp_path / "data" / "user_dashboard.json"
    assert fp.is_file(), "偏好文件未写入"
    assert json.loads(fp.read_text(encoding="utf-8")) == {"widgets": widgets}


def test_user_dashboard_accepts_all_five_v2_ids(client, auth, tmp_path):
    widgets = ["snapshot", "recommendation", "breadth", "event", "backtest"]
    r = client.put("/api/v2/read/user-dashboard", json={"widgets": widgets}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert r.get_json()["data"] == {"widgets": widgets}
    assert json.loads(
        (tmp_path / "data" / "user_dashboard.json").read_text(encoding="utf-8")
    ) == {"widgets": widgets}


@pytest.mark.parametrize("body", [
    {"widgets": "snapshot"},                  # 非 list
    {"widgets": []},                          # 长度 0
    {"widgets": ["snapshot"] * 6},            # 长度 >5（先触发长度校验）
    {"widgets": ["market_state"]},            # v1 widget key 不是 v2 id → 422
    {"widgets": ["unknown"]},                 # 完全未知 id
    {"widgets": ["snapshot", "snapshot"]},   # 重复
    {"widgets": [123]},                       # 非字符串项
    {},                                       # 缺 widgets
    [],                                       # body 非对象
])
def test_user_dashboard_invalid_body_422(client, auth, tmp_path, body):
    r = client.put("/api/v2/read/user-dashboard", json=body, headers=auth)
    _assert_validation_422(r)
    fp = tmp_path / "data" / "user_dashboard.json"
    assert not fp.exists(), "校验失败不得写文件"


def test_user_dashboard_malformed_json_422(client, auth):
    r = client.put(
        "/api/v2/read/user-dashboard",
        data="not-json", content_type="application/json", headers=auth,
    )
    _assert_validation_422(r)


# ───────────────── 4. review-notes PUT ─────────────────
def test_review_notes_put_then_get_readback(client, auth, tmp_path):
    date, content = "2026-09-21", "# 复盘\n\n- 第一点\n- 第二点\n"
    r = client.put("/api/v2/read/review-notes", json={"date": date, "content": content}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert r.get_json()["data"] == {"date": date, "content": content}

    get_r = client.get(f"/api/v2/read/review-notes?date={date}", headers=auth)
    assert get_r.status_code == 200, get_r.text[:300]
    assert get_r.get_json()["data"] == {"date": date, "content": content}

    fp = tmp_path / "data" / f"review_notes_{date}.md"
    assert fp.is_file(), "笔记文件未写入"
    assert fp.read_text(encoding="utf-8") == content


def test_review_notes_overwrite_semantics(client, auth, tmp_path):
    date = "2026-09-22"
    first, second = "旧内容 first", "新内容 second（全文覆盖）"
    r1 = client.put("/api/v2/read/review-notes", json={"date": date, "content": first}, headers=auth)
    assert r1.status_code == 200, r1.text[:300]
    r2 = client.put("/api/v2/read/review-notes", json={"date": date, "content": second}, headers=auth)
    assert r2.status_code == 200, r2.text[:300]

    get_r = client.get(f"/api/v2/read/review-notes?date={date}", headers=auth)
    assert get_r.get_json()["data"]["content"] == second
    fp = tmp_path / "data" / f"review_notes_{date}.md"
    text = fp.read_text(encoding="utf-8")
    assert text == second, f"覆盖写失败/残留旧内容: {text!r}"
    assert first not in text


def test_review_notes_empty_content_still_writes_file(client, auth, tmp_path):
    date = "2026-09-23"
    r = client.put("/api/v2/read/review-notes", json={"date": date, "content": ""}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert r.get_json()["data"] == {"date": date, "content": ""}
    fp = tmp_path / "data" / f"review_notes_{date}.md"
    assert fp.is_file(), "空白笔记也必须落盘"
    assert fp.read_text(encoding="utf-8") == ""
    # 注：既有 GET 对空文件仍按 not_found 处理（_read_text 语义），本批不改 GET。


@pytest.mark.parametrize("body", [
    {"date": "2026-13-99", "content": "x"},   # 假日期
    {"date": "not-a-date", "content": "x"},   # 形状非法
    {"date": "../etc/passwd", "content": "x"},  # 穿越形状
    {"content": "x"},                          # 缺 date
    {"date": "2026-09-24", "content": 123},    # content 非 str
    {"date": "2026-09-24", "content": "x" * 500_001},  # 超长
    [],                                        # body 非对象
])
def test_review_notes_invalid_body_422(client, auth, tmp_path, body):
    r = client.put("/api/v2/read/review-notes", json=body, headers=auth)
    _assert_validation_422(r)
    assert list((tmp_path / "data").glob("review_notes_*.md")) == [], "校验失败不得写文件"


# ───────────────── 5. 鉴权门 ─────────────────
@pytest.mark.parametrize("method,path", [
    ("get", "/api/v2/read/breadth-divergence"),
    ("get", "/api/v2/read/temperature-backtest"),
    ("put", "/api/v2/read/user-dashboard"),
    ("put", "/api/v2/read/review-notes"),
])
def test_endpoints_require_jwt(client, monkeypatch, method, path):
    _install_bd(monkeypatch)
    _install_tb(monkeypatch)
    if method == "put":
        r = client.put(path, json={})
    else:
        r = client.get(path)
    assert r.status_code == 401, f"{path} 缺 token 应 401，实得 {r.status_code}: {r.text[:200]}"
    assert r.get_json()["code"] == "missing_token", r.text[:200]
