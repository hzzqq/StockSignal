"""
backend/tests/test_api_quote_kline.py
-------------------------------------
针对后端新增行情端点 /api/quote、/api/kline 的契约测试。
与 test_api_contracts.py（16 passed）正交，独立文件，不改动其用例计数。

契约来源：team-lead 冻结版 FETCHER_CONTRACT.md §3 + 后端 2026-07-10 同步。

设计约束：
- 复用独立临时 SQLite + _TestConfig 隔离（与 test_api_contracts 一致），绝不污染 backend/data/app.db。
- 通过 monkeypatch backend.api.market_routes.get_fetcher() 注入伪造 StockFetcher，
  验证行情接口的「成功 / 参数无效 / 降级(None·空DataFrame) / 异常 / 未鉴权」全路径，
  不依赖真实网络与数据层实现。
- 不 import、不修改任何 backend 业务实现；只消费契约。
"""
from __future__ import annotations

import os
import sys

# 把项目根（StockSignal）加入 sys.path，保证 `import backend...` 可行
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd                                          # noqa: E402
import pytest                                                # noqa: E402

from flask import current_app                               # noqa: E402

from backend.app import create_app                          # noqa: E402
from backend.extensions import db                           # noqa: E402
from backend.config import Config                           # noqa: E402
from backend.models import User                             # noqa: E402
from backend.utils.ratelimit import reset_rate_limit        # noqa: E402


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def app(tmp_path):
    # 每个用例独立临时库（tmp_path 唯一）；限流关闭（行情用例无需限流）。
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 't.db'}"
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


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------- 辅助
def _token(client, username="demo", password="Pass@123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _get_json(resp, label):
    """安全解析 JSON（force=True 兼容 Content-Type 带 charset 的情况）。"""
    obj = resp.get_json(force=True)
    assert isinstance(obj, dict), f"[{label}] 响应非 JSON 对象: {resp.text[:200]}"
    return obj


class FakeFetcher:
    """伪造 StockFetcher：用 get_fetcher() 注入，控制 quote/kline 返回值与异常。"""

    def __init__(self, quote_data=None, kline_df=None,
                 raise_on_quote=False, raise_on_kline=False,
                 raise_value_on_kline=False):
        self.quote_data = quote_data
        self.kline_df = kline_df
        self.raise_on_quote = raise_on_quote
        self.raise_on_kline = raise_on_kline
        self.raise_value_on_kline = raise_value_on_kline
        self.quote_calls = []
        self.kline_calls = []

    def get_realtime_quote(self, ticker):
        self.quote_calls.append(ticker)
        if self.raise_on_quote:
            raise RuntimeError("injected quote failure")
        return self.quote_data

    def get_daily(self, symbol, start="2024-01-01", end=None, adjust="qfq"):
        self.kline_calls.append((symbol, start, end, adjust))
        if self.raise_on_kline:
            # 与 modules/fetcher.get_daily 真实降级行为一致：全源+缓存失败时抛 RuntimeError
            raise RuntimeError("injected kline failure (no source)")
        if self.raise_value_on_kline:
            raise ValueError("injected unexpected kline failure")
        return self.kline_df


def _use_fetcher(monkeypatch, **kwargs):
    """monkeypatch market_routes.get_fetcher() 返回伪造实例。"""
    import backend.api.market_routes as mr
    fake = FakeFetcher(**kwargs)
    monkeypatch.setattr(mr, "get_fetcher", lambda: fake)
    return fake


# 成功路径 quote dict 必备字段
_QUOTE_FIELDS = {
    "ticker", "name", "open", "prev_close", "current", "high", "low",
    "volume", "amount", "bid", "ask", "datetime",
}


def _sample_quote():
    return {
        "ticker": "600519", "name": "贵州茅台",
        "open": 1444.0, "prev_close": 1408.0, "current": 1420.0,
        "high": 1450.0, "low": 1400.0, "volume": 50000, "amount": 7.1e9,
        "bid": [{"price": 1419.0, "volume": 1200}],
        "ask": [{"price": 1420.0, "volume": 800}],
        "datetime": "2026-07-10 15:00:00",
    }


def _sample_kline_df():
    return pd.DataFrame([
        {"date": pd.Timestamp("2024-01-02"), "open": 1.0, "close": 2.0,
         "high": 2.5, "low": 0.9, "volume": 10, "amount": 100.0,
         "change_pct": 1.0},
    ])


_KLINE_FIELDS = {"date", "open", "close", "high", "low", "volume", "amount", "change_pct"}


# ================================================================ /api/quote
class TestQuote:

    def test_quote_success(self, client, monkeypatch):
        """成功：dict 含全部必备字段，信封 status=ok。"""
        fake = _use_fetcher(monkeypatch, quote_data=_sample_quote())
        token = _token(client, "demo")
        r = client.get("/api/quote?ticker=600519", headers=_auth_headers(token))
        assert r.status_code == 200
        obj = _get_json(r, "quote_success")
        assert obj["status"] == "ok"
        assert obj["code"] == "ok"
        data = obj["data"]
        assert isinstance(data, dict)
        assert _QUOTE_FIELDS <= set(data.keys())
        assert data["ticker"] == "600519"
        assert data["name"] == "贵州茅台"
        assert isinstance(data["bid"], list) and isinstance(data["ask"], list)
        # 透传：ticker 原样传入 fetcher
        assert fake.quote_calls == ["600519"]

    def test_quote_invalid_param(self, client, monkeypatch):
        """ticker 非 6 位数字 → 400 + invalid_param + "参数无效"。"""
        _use_fetcher(monkeypatch, quote_data=_sample_quote())
        token = _token(client, "demo")
        # 5 位、字母、空 各一例
        for bad in ("60051", "abc", ""):
            r = client.get(f"/api/quote?ticker={bad}", headers=_auth_headers(token))
            assert r.status_code == 400, f"ticker={bad!r} 期望 400"
            obj = _get_json(r, f"quote_bad_{bad}")
            assert obj["status"] == "error"
            assert obj["code"] == "invalid_param"
            assert obj["message"] == "参数无效"
            assert obj["data"] is None

    def test_quote_none_returns_502(self, client, monkeypatch):
        """get_realtime_quote 返回 None → 502 + quote_failed + "行情获取失败"。"""
        fake = _use_fetcher(monkeypatch, quote_data=None)
        token = _token(client, "demo")
        r = client.get("/api/quote?ticker=600519", headers=_auth_headers(token))
        assert r.status_code == 502
        obj = _get_json(r, "quote_none")
        assert obj["status"] == "error"
        assert obj["code"] == "quote_failed"
        assert obj["message"] == "行情获取失败"
        assert obj["data"] is None

    def test_quote_internal_error(self, client, monkeypatch):
        """fetcher 抛异常 → 500 + internal_error + "服务内部错误"。"""
        _use_fetcher(monkeypatch, raise_on_quote=True)
        token = _token(client, "demo")
        r = client.get("/api/quote?ticker=600519", headers=_auth_headers(token))
        assert r.status_code == 500
        obj = _get_json(r, "quote_err")
        assert obj["status"] == "error"
        assert obj["code"] == "internal_error"
        assert obj["message"] == "服务内部错误"

    def test_quote_unauthorized(self, client, monkeypatch):
        """未带 JWT → 401（与现有受保护接口一致）。"""
        _use_fetcher(monkeypatch, quote_data=_sample_quote())
        r = client.get("/api/quote?ticker=600519")
        assert r.status_code == 401


# ================================================================ /api/kline
class TestKline:

    def test_kline_success(self, client, monkeypatch):
        """成功：list of records 含全部必备列，信封 status=ok。"""
        df = _sample_kline_df()
        fake = _use_fetcher(monkeypatch, kline_df=df)
        token = _token(client, "demo")
        r = client.get(
            "/api/kline?symbol=600519&start=2024-01-01&end=2024-03-01&adjust=qfq",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        obj = _get_json(r, "kline_success")
        assert obj["status"] == "ok"
        assert obj["code"] == "ok"
        data = obj["data"]
        assert isinstance(data, list) and len(data) == 1
        assert _KLINE_FIELDS <= set(data[0].keys())
        # 透传：symbol/start/end/adjust 原样传入 fetcher
        assert fake.kline_calls == [("600519", "2024-01-01", "2024-03-01", "qfq")]

    def test_kline_invalid_param(self, client, monkeypatch):
        """symbol 非 6 位数字 → 400 + invalid_param + "参数无效"。"""
        _use_fetcher(monkeypatch, kline_df=_sample_kline_df())
        token = _token(client, "demo")
        for bad in ("60051", "abc", ""):
            r = client.get(f"/api/kline?symbol={bad}", headers=_auth_headers(token))
            assert r.status_code == 400, f"symbol={bad!r} 期望 400"
            obj = _get_json(r, f"kline_bad_{bad}")
            assert obj["status"] == "error"
            assert obj["code"] == "invalid_param"
            assert obj["message"] == "参数无效"
            assert obj["data"] is None

    def test_kline_empty_df_returns_404(self, client, monkeypatch):
        """get_daily 返回空 DataFrame → 404 + no_kline_data + "无行情数据"。"""
        fake = _use_fetcher(monkeypatch, kline_df=pd.DataFrame())
        token = _token(client, "demo")
        r = client.get("/api/kline?symbol=600519", headers=_auth_headers(token))
        assert r.status_code == 404
        obj = _get_json(r, "kline_empty")
        assert obj["status"] == "error"
        assert obj["code"] == "no_kline_data"
        assert obj["message"] == "无行情数据"
        assert obj["data"] is None

    def test_kline_default_params_passthrough(self, client, monkeypatch):
        """省略 start/end/adjust 时，后端以默认值透传 fetcher。"""
        fake = _use_fetcher(monkeypatch, kline_df=_sample_kline_df())
        token = _token(client, "demo")
        r = client.get("/api/kline?symbol=600519", headers=_auth_headers(token))
        assert r.status_code == 200
        # 默认 start=2024-01-01, end=None, adjust=qfq
        assert fake.kline_calls == [("600519", "2024-01-01", None, "qfq")]

    def test_kline_runtime_error_returns_404(self, client, monkeypatch):
        """fetcher 总源失败抛 RuntimeError（与真实降级一致）→ 404 + no_kline_data +
        '无行情数据'（注意：与 quote 不同，kline 将 RuntimeError 视为『无数据』而非 500）。
        详见下方 test_kline_other_exception_returns_500 与对 后端的契约差异说明。"""
        fake = _use_fetcher(monkeypatch, raise_on_kline=True)
        token = _token(client, "demo")
        r = client.get("/api/kline?symbol=600519", headers=_auth_headers(token))
        assert r.status_code == 404
        obj = _get_json(r, "kline_runtime_err")
        assert obj["status"] == "error"
        assert obj["code"] == "no_kline_data"
        assert obj["message"] == "无行情数据"
        assert obj["data"] is None

    def test_kline_other_exception_returns_500(self, client, monkeypatch):
        """fetcher 抛出非 RuntimeError 的意外异常 → 500 + internal_error + '服务内部错误'。"""
        _use_fetcher(monkeypatch, raise_value_on_kline=True)
        token = _token(client, "demo")
        r = client.get("/api/kline?symbol=600519", headers=_auth_headers(token))
        assert r.status_code == 500
        obj = _get_json(r, "kline_err")
        assert obj["status"] == "error"
        assert obj["code"] == "internal_error"
        assert obj["message"] == "服务内部错误"

    def test_kline_unauthorized(self, client, monkeypatch):
        """未带 JWT → 401。"""
        _use_fetcher(monkeypatch, kline_df=_sample_kline_df())
        r = client.get("/api/kline?symbol=600519")
        assert r.status_code == 401
