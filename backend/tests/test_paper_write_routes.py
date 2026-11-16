"""
backend/tests/test_paper_write_routes.py
----------------------------------------
模拟账本写端点真实验收测试（V2 /paper 从只读壳升级）。

覆盖：
  * POST 买入/卖出按 v1 语义更新现金与持仓；
  * 写入后 GET /api/v2/read/paper-trades 回读一致，落盘内容精确一致；
  * 非法请求体 / 业务规则不满足 → 422 validation_error（不是 400，也不是 500）；
  * 无 token → 401 missing_token（POST / DELETE / reset 三个端点）；
  * 删除不存在 id → 404 not_found，账本内容不变（诚实行为）；
  * 按 id 删除成功；原子写落盘后无残留临时文件、无半文件；
  * 按 JWT 用户隔离，两个用户各写各的账本文件。

隔离约束（照 test_batch_b_endpoints.py 范式）：
  * 独立临时 SQLite（不碰 backend/data/app.db）；
  * monkeypatch read_routes._DATA_DIR 到 pytest tmp_path，读写两侧同源重定向，
    任何账本写入只落在临时目录，绝不写主区 data/；
  * 禁止 pytest.skip，禁止仅断言 200 的伪测试。
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
from backend.api.paper_write_routes import bp as paper_write_bp  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402

CODE = "600519"


@pytest.fixture
def app(tmp_path, monkeypatch):
    """真实 Flask app + 独立 SQLite；账本数据根重定向到 tmp_path。"""
    db_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(read_routes, "_DATA_DIR", data_dir)

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file.as_posix()}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    # team-lead 会在 app.py 统一注册；若尚未接 line，这里手动挂上以便独立验收。
    if "paper_write" not in application.blueprints:
        application.register_blueprint(paper_write_bp)
    with application.app_context():
        db.create_all()
        for username in ("demo", "other"):
            if User.query.filter_by(username=username).first() is None:
                u = User(username=username, role="user")
                u.set_password("Pass@123")
                db.session.add(u)
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _auth(client, username):
    r = client.post(
        "/api/auth/login", json={"username": username, "password": "Pass@123"}
    )
    assert r.status_code == 200, f"登录失败: {r.status_code} {r.text[:300]}"
    token = r.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth(client):
    return _auth(client, "demo")


@pytest.fixture
def auth_other(client):
    return _auth(client, "other")


def _book_file(tmp_path, user="demo"):
    return tmp_path / "data" / f"paper_{user}.json"


def _post(client, auth, **overrides):
    body = {"code": CODE, "side": "买", "price": 100.0, "qty": 100, "name": "测试标的"}
    body.update(overrides)
    return client.post("/api/v2/paper-trades", json=body, headers=auth)


def _get_book(client, auth, user="demo"):
    r = client.get(f"/api/v2/read/paper-trades?user={user}", headers=auth)
    assert r.status_code == 200, r.text[:300]
    return r.get_json()


def _assert_422(r):
    assert r.status_code == 422, f"期望 422，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert isinstance(j, dict), f"响应非 JSON: {r.text[:300]}"
    assert j["status"] == "error", j
    assert j["code"] == "validation_error", j
    assert j["data"] is None, f"校验失败不得返回假数据: {j}"


# ───────────────── 1. 写入后 GET 回读一致 ─────────────────
def test_add_buy_then_get_readback_matches_disk(client, auth, tmp_path):
    r = _post(client, auth)
    assert r.status_code == 200, r.text[:300]
    trade = r.get_json()["data"]
    assert trade["id"] == 1, trade
    assert trade["code"] == CODE, trade
    assert trade["side"] == "买", trade
    assert trade["price"] == 100.0 and trade["qty"] == 100, trade
    assert trade["amount"] == 10000.0, trade
    assert trade["name"] == "测试标的", trade
    assert isinstance(trade["time"], str) and trade["time"], trade

    envelope = _get_book(client, auth)
    assert envelope["status"] == "ok", envelope
    book = envelope["data"]
    assert book["cash"] == 990000.0, book
    assert book["positions"][CODE] == {
        "name": "测试标的", "qty": 100, "avg_cost": 100.0,
    }, book
    assert book["trades"] == [trade], book

    fp = _book_file(tmp_path)
    assert fp.is_file(), "账本未落盘"
    assert json.loads(fp.read_text(encoding="utf-8")) == book, "落盘内容与 GET 回读不一致"


def test_add_sell_updates_cash_and_position(client, auth, tmp_path):
    _post(client, auth)
    r = _post(client, auth, side="卖", price=110.0, qty=100)
    assert r.status_code == 200, r.text[:300]
    sell = r.get_json()["data"]
    assert sell["id"] == 2 and sell["side"] == "卖", sell
    assert sell["amount"] == 11000.0, sell

    book = _get_book(client, auth)["data"]
    assert book["cash"] == 1001000.0, book
    assert CODE not in book["positions"], book
    assert [t["id"] for t in book["trades"]] == [1, 2], book


def test_repeated_buy_uses_weighted_average(client, auth):
    _post(client, auth, price=100.0, qty=100)
    _post(client, auth, price=200.0, qty=100)
    book = _get_book(client, auth)["data"]
    assert book["cash"] == 970000.0, book
    assert book["positions"][CODE]["qty"] == 200, book
    assert book["positions"][CODE]["avg_cost"] == 150.0, book


# ───────────────── 2. 非法请求体 422 ─────────────────
@pytest.mark.parametrize("body", [
    {},                                                  # 缺全部字段
    [],                                                  # body 非对象
    {"side": "买", "price": 10, "qty": 100},             # 缺 code
    {"code": "abc", "side": "买", "price": 10, "qty": 100},  # code 非 6 位数字
    {"code": CODE, "price": 10, "qty": 100},             # 缺 side
    {"code": CODE, "side": "X", "price": 10, "qty": 100},    # side 非法
    {"code": CODE, "side": "买", "qty": 100},            # 缺 price
    {"code": CODE, "side": "买", "price": 0, "qty": 100},    # price 为 0
    {"code": CODE, "side": "买", "price": -1, "qty": 100},   # price 负数
    {"code": CODE, "side": "买", "price": "100", "qty": 100},  # price 非数字
    {"code": CODE, "side": "买", "price": 10},            # 缺 qty
    {"code": CODE, "side": "买", "price": 10, "qty": 50},    # qty 非 100 倍数
    {"code": CODE, "side": "买", "price": 10, "qty": 101},   # qty 非 100 倍数
    {"code": CODE, "side": "买", "price": 10, "qty": "100"}, # qty 非整数
])
def test_invalid_body_422(client, auth, tmp_path, body):
    r = client.post("/api/v2/paper-trades", json=body, headers=auth)
    _assert_422(r)
    assert not _book_file(tmp_path).exists(), "校验失败不得写账本"


def test_malformed_json_422(client, auth):
    r = client.post(
        "/api/v2/paper-trades",
        data="not-json", content_type="application/json", headers=auth,
    )
    _assert_422(r)


def test_buy_with_insufficient_cash_422(client, auth):
    r = _post(client, auth, price=20000.0, qty=100)  # 需 200 万 > 100 万初始资金
    _assert_422(r)


def test_sell_without_position_422(client, auth, tmp_path):
    r = _post(client, auth, side="卖", price=100.0, qty=100)
    _assert_422(r)
    assert not _book_file(tmp_path).exists(), "校验失败不得写账本"


def test_sell_more_than_held_422(client, auth):
    _post(client, auth, price=100.0, qty=100)
    r = _post(client, auth, side="卖", price=100.0, qty=200)
    _assert_422(r)
    book = _get_book(client, auth)["data"]
    assert [t["id"] for t in book["trades"]] == [1], book


# ───────────────── 3. 鉴权门 ─────────────────
@pytest.mark.parametrize("method,path", [
    ("post", "/api/v2/paper-trades"),
    ("delete", "/api/v2/paper-trades/1"),
    ("post", "/api/v2/paper-trades/reset"),
])
def test_endpoints_require_jwt(client, method, path):
    r = getattr(client, method)(path, json={})
    assert r.status_code == 401, f"{path} 缺 token 应 401，实得 {r.status_code}: {r.text[:200]}"
    assert r.get_json()["code"] == "missing_token", r.text[:200]


# ───────────────── 4. 删除行为 ─────────────────
def test_delete_nonexistent_id_is_honest_404(client, auth, tmp_path):
    _post(client, auth)
    fp = _book_file(tmp_path)
    before = fp.read_text(encoding="utf-8")

    r = client.delete("/api/v2/paper-trades/999", headers=auth)
    assert r.status_code == 404, r.text[:300]
    assert r.get_json()["code"] == "not_found", r.get_json()
    assert fp.read_text(encoding="utf-8") == before, "删除失败不得改动账本"
    assert len(_get_book(client, auth)["data"]["trades"]) == 1


def test_delete_existing_trade(client, auth, tmp_path):
    _post(client, auth, price=100.0, qty=100)
    _post(client, auth, price=110.0, qty=100)
    r = client.delete("/api/v2/paper-trades/1", headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert r.get_json()["data"] == {"deleted_id": 1, "remaining": 1}, r.get_json()

    book = _get_book(client, auth)["data"]
    assert [t["id"] for t in book["trades"]] == [2], book
    assert json.loads(_book_file(tmp_path).read_text(encoding="utf-8")) == book


# ───────────────── 5. 原子写 ─────────────────
def test_atomic_write_leaves_no_temp_or_half_file(client, auth, tmp_path, monkeypatch):
    from backend.api import paper_write_routes as pwr

    real_dump = pwr.atomic_json_dump
    calls = []

    def spy(obj, path, **kwargs):
        calls.append((obj, path))
        return real_dump(obj, path, **kwargs)

    monkeypatch.setattr(pwr, "atomic_json_dump", spy)

    r = _post(client, auth)
    assert r.status_code == 200, r.text[:300]
    expected_path = str(_book_file(tmp_path))
    assert len(calls) == 1, calls
    assert calls[0][1] == expected_path, calls
    assert calls[0][0]["trades"][0]["id"] == 1, calls

    data_dir = tmp_path / "data"
    leftovers = [p.name for p in data_dir.iterdir() if ".tmp" in p.name or p.name.startswith(".")]
    assert leftovers == [], f"原子写残留临时文件: {leftovers}"

    fp = _book_file(tmp_path)
    on_disk = json.loads(fp.read_text(encoding="utf-8"))  # 能解析 => 非半文件
    assert on_disk == _get_book(client, auth)["data"], on_disk
    assert on_disk["cash"] == 990000.0 and len(on_disk["trades"]) == 1, on_disk


def test_reset_restores_initial_book(client, auth, tmp_path):
    _post(client, auth)
    r = client.post("/api/v2/paper-trades/reset", headers=auth)
    assert r.status_code == 200, r.text[:300]
    book = _get_book(client, auth)["data"]
    assert book == {
        "init_cash": 1000000.0, "cash": 1000000.0,
        "positions": {}, "trades": [], "equity": [],
    }, book
    assert json.loads(_book_file(tmp_path).read_text(encoding="utf-8")) == book


# ───────────────── 6. 按用户隔离 ─────────────────
def test_ledger_isolated_by_jwt_user(client, auth, auth_other, tmp_path):
    _post(client, auth, price=100.0, qty=100)

    other = _get_book(client, auth_other, user="other")
    assert other["status"] == "error" and other["code"] == "not_found", other
    assert not _book_file(tmp_path, "other").exists(), "不应为未写入的用户生成账本"

    r = _post(client, auth_other, code="000001", price=10.0, qty=200)
    assert r.status_code == 200, r.text[:300]
    assert _book_file(tmp_path, "demo").is_file()
    assert _book_file(tmp_path, "other").is_file()
    assert [t["code"] for t in _get_book(client, auth)["data"]["trades"]] == [CODE]
    assert [t["code"] for t in _get_book(client, auth_other, user="other")["data"]["trades"]] == ["000001"]
