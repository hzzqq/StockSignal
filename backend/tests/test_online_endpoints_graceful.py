"""
backend/tests/test_online_endpoints_graceful.py
-------------------------------------------------
在线端点「上游失败时优雅降级、绝不 500」确定性守卫（延续 §25 market-sentiment 真缺陷的同类防御）：

  真实缺陷教训（§25）：/market-sentiment 在底层模块返回含非维度注入键的 meta 时 500，
  根因是后处理未做类型防御。在线端点（akshare/实时行情）另一类常见风险是：**上游网络
  / akshare 调用抛异常时，若未被 try/except 接住，整个端点 500**——生产环境网络抖动、
  数据源限流、akshare 改版都会触发，native 页直接整页报错。

  本测试不依赖联网：用 monkeypatch 把 requests / urllib 网络调用**立即抛 ConnectionError**
  （模拟离线/超时），打真实 Flask app + 真实 JWT，断言：
    1. 任意在线端点 status_code 绝不 500（核心契约：上游失败 → 200 优雅信封，而非 500）；
    2. 若返回 200，响应必为统一信封（含 status/code/message/data 四字段）。

  为何确定性：网络层打挂使 akshare 调用瞬间失败（无真实超时等待），无网环境也能稳定复现；
  命中端点若未接住异常 → 500 → 断言失败，精准暴露真实缺陷。

设计约束：独立临时 SQLite + _TestConfig 隔离，绝不污染 backend/data/app.db。
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

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.models import User  # noqa: E402


# 在线端点 + 合法参数（合法参数使端点真正尝试网络调用，再被优雅降级捕获）。
# value 为空串表示无必需参数；带 ? 的为 query 参数。
ONLINE_ENDPOINTS = [
    ("market-sentiment", ""),
    ("momentum-breadth", ""),
    ("limit-up-review", ""),
    ("earnings-calendar", "?period=2026-03-31"),
    ("six-dim", "?code=600519"),
    ("fundamentals", "?code=600519"),
    ("financials", "?code=600519"),
    ("stock-kline", "?code=600519&period=daily"),
    ("compare-one", "?code=600519"),
    ("research-deep", "?code=600519"),
    ("stock-intraday", "?code=600519"),
    ("index-quotes", ""),
    ("index-kline", "?code=000001"),
    ("factor-analysis", "?code=600519"),
    ("market-panorama", ""),
    ("portfolio", ""),
    ("fund-flow", "?code=600519"),
    ("sector-rotation", ""),
    ("watch", ""),
    ("trading-account", ""),
    ("macro-data", ""),
    ("dragon-tiger", ""),
    ("theme", ""),
    ("theme-transmission", ""),
    ("strong", ""),
    ("quote-board", ""),
    ("breadth-timeseries", "?dim=zt_num&window=250"),
    ("backtest", ""),
]


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


@pytest.fixture(autouse=True)
def _kill_network(monkeypatch):
    """把 requests / urllib 的网络调用立即打挂，模拟离线/超时/数据源不可达。"""
    def _boom(*_a, **_k):
        raise ConnectionError("simulated offline (graceful-degradation guard)")

    import requests  # noqa: WPS433 (局部导入便于 monkeypatch)
    import urllib.request  # noqa: WPS433

    for target in (
        "requests.get", "requests.post", "requests.put", "requests.head",
        "requests.Session.get", "requests.Session.post", "requests.Session.put",
        "requests.Session.request",
    ):
        module, attr = target.rsplit(".", 1)
        monkeypatch.setattr(f"{module}.{attr}", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    # 部分 akshare/模块可能经自定义 http 包装；socket 不参与，避免误伤 in-process 测试客户端。
    yield


@pytest.mark.parametrize("name,q", ONLINE_ENDPOINTS)
def test_online_endpoint_never_500_on_upstream_failure(client, name, q):
    tok = _token(client)
    ep = f"/api/v2/read/{name}{q}"
    r = client.get(ep, headers={"Authorization": f"Bearer {tok}"})
    # 核心契约：上游失败绝不 500（400 属参数校验、200 属优雅降级，均合法）。
    assert r.status_code != 500, (
        f"{name} 在上游失败时返回 500（应优雅降级为 200 信封）："
        f"{r.status_code} {r.text[:300]}"
    )
    # 若端点尝试了网络并返回 200，响应必须是统一信封。
    if r.status_code == 200:
        j = r.get_json()
        assert isinstance(j, dict), f"{name} 200 但响应非 JSON dict: {r.text[:200]}"
        for k in ("status", "code", "message", "data"):
            assert k in j, f"{name} 信封缺字段 {k}: {j}"
