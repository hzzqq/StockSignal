"""40/41/45 组合写端点验收（同源 PortfolioManager，临时目录隔离）。

红线：
  * 所有持仓/卖出只写 pytest tmp_path，绝不碰主区 data/portfolio*.csv；
  * 独立 SQLite + 真 JWT；非法参数 422 / 越界 404 / 无 token 401；
  * 卖出只追加 trades，不改买入批次（v1 FIFO 口径不变）。
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.api import portfolio_write_routes as pwr  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from modules.portfolio import PortfolioManager  # noqa: E402

CODE = "600519"
URL = "/api/v2/portfolio"


def _test_manager(tmp_path):
    """绕开默认 data/ 路径，手工装配只指向 tmp_path 的 PortfolioManager。"""
    pm = object.__new__(PortfolioManager)
    pm.file_path = str(tmp_path / "portfolio.csv")
    pm.config = {}
    pm.fetcher = SimpleNamespace(get_stock_name=lambda code: "测试股票")
    pm._ensure_file()
    return pm


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
    if "portfolio_write" not in application.blueprints:
        application.register_blueprint(pwr.bp)
    pm = _test_manager(tmp_path)
    monkeypatch.setattr(pwr, "_manager", lambda: pm)

    with application.app_context():
        db.create_all()
        if User.query.filter_by(username="demo").first() is None:
            u = User(username="demo", role="user")
            u.set_password("Pass@123")
            db.session.add(u)
            db.session.commit()
    application.config["TEST_PM"] = pm
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Pass@123"})
    assert r.status_code == 200, r.text[:300]
    return {"Authorization": f"Bearer {r.get_json()['data']['token']}"}


def _add(client, auth, *, shares=1000, price=20.0, ticker=CODE):
    return client.post(f"{URL}/positions", headers=auth, json={
        "ticker": ticker, "buy_date": "2026-01-05", "buy_price": price,
        "shares": shares, "name": "贵州茅台", "note": "建仓理由",
    })


def test_add_position_writes_same_csv_and_reads_back(client, auth, app):
    r = _add(client, auth)
    assert r.status_code == 200, r.text[:300]
    row = r.get_json()["data"]["position"]
    assert row["ticker"] == CODE and row["shares"] == 1000
    assert row["cost"] == 20000.0 and row["name"] == "贵州茅台"
    pm = app.config["TEST_PM"]
    positions = pm.get_positions()
    assert len(positions) == 1
    assert positions.iloc[0]["note"] == "建仓理由"


def test_sell_valid_appends_trade_without_touching_buy_batch(client, auth, app):
    assert _add(client, auth).status_code == 200
    r = client.post(f"{URL}/sell", headers=auth, json={
        "ticker": CODE, "sell_date": "2026-02-10", "sell_price": 25.0,
        "sell_shares": 400, "name": "贵州茅台", "note": "止盈",
    })
    assert r.status_code == 200, r.text[:300]
    trade = r.get_json()["data"]["trade"]
    assert trade["proceeds"] == 10000.0 and trade["sell_shares"] == 400
    pm = app.config["TEST_PM"]
    assert len(pm.get_trades()) == 1
    assert len(pm.get_positions()) == 1  # 买入批次不动
    assert pm.get_sellable_shares(CODE) == 600


def test_sell_over_holdings_is_422_and_no_partial_write(client, auth, app):
    assert _add(client, auth).status_code == 200
    r = client.post(f"{URL}/sell", headers=auth, json={
        "ticker": CODE, "sell_date": "2026-02-10", "sell_price": 25.0,
        "sell_shares": 1001, "name": "贵州茅台",
    })
    assert r.status_code == 422, r.text[:300]
    assert "可卖股数不足" in r.get_json()["message"]
    assert app.config["TEST_PM"].get_trades().empty


def test_delete_position_by_index(client, auth, app):
    assert _add(client, auth).status_code == 200
    r = client.delete(f"{URL}/positions/0", headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert r.get_json()["data"]["removed"]["ticker"] == CODE
    assert app.config["TEST_PM"].get_positions().empty
    r2 = client.delete(f"{URL}/positions/0", headers=auth)
    assert r2.status_code == 404


@pytest.mark.parametrize("body", [
    {"ticker": "60051", "buy_date": "2026-01-05", "buy_price": 20, "shares": 100},
    {"ticker": CODE, "buy_date": "2026-13-40", "buy_price": 20, "shares": 100},
    {"ticker": CODE, "buy_date": "2026-01-05", "buy_price": -1, "shares": 100},
    {"ticker": CODE, "buy_date": "2026-01-05", "buy_price": 20, "shares": 0},
])
def test_add_position_invalid_body_422(client, auth, body):
    r = client.post(f"{URL}/positions", headers=auth, json=body)
    assert r.status_code == 422, r.text[:300]
    assert r.get_json()["code"] == "validation_error"


@pytest.mark.parametrize("method,path", [
    ("post", f"{URL}/positions"),
    ("post", f"{URL}/sell"),
    ("delete", f"{URL}/positions/0"),
])
def test_portfolio_writes_require_token(client, method, path):
    r = getattr(client, method)(path, json={"ticker": CODE})
    assert r.status_code == 401
