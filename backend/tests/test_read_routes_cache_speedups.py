# -*- coding: utf-8 -*-  # noqa: UP009
"""backend/tests/test_read_routes_cache_speedups.py — 提速缓存回归守卫（缺陷4）。

验证（全离线、零网络、独立测试码段避免跨用例缓存污染）：

  1. _w4b_financial：进程级 TTL 3h 缓存生效（同 code+report 二次调用不再回源），
     None/空结果不缓存（瞬时失败不锁 3h，诚实语义）；
  2. _sp_core_business：TTL 1h 缓存生效（真值只拉一次），
     '' / 异常按空结果处理不缓存；
  3. /research-deep 已砍掉不消费的 income 源（四源 -> 三源并行）：
     - AST 守卫：research_deep 函数体不再引用 _w4b_financial；
     - 行为守卫：即使 _w4b_financial 被替换为炸弹，端点仍 200（证明未调用）。
"""
from __future__ import annotations

import ast
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from modules import cache_utils  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_ttl_cache():
    """前后清空全局 TTL 缓存，避免用例间/与其他测试串扰。"""
    cache_utils.clear_cache()
    yield
    cache_utils.clear_cache()


# ───────────── 1. _w4b_financial TTL 3h ─────────────

def test_w4b_financial_caches_by_code_and_report(monkeypatch):
    import pandas as pd
    calls = {"n": 0}
    tiny = pd.DataFrame({"科目": ["营业总收入"], "2026-09-30": [1.0]})

    def fake_fetch(code, report_type):
        calls["n"] += 1
        return tiny

    monkeypatch.setattr(rr, "_w4b_financial_fetch", fake_fetch)

    a = rr._w4b_financial("999001", "income")
    b = rr._w4b_financial("999001", "income")
    assert calls["n"] == 1, "同 code+report 二次调用应命中缓存，不再回源"
    assert a is b, "缓存命中应返回同一对象"

    rr._w4b_financial("999001", "balance")
    assert calls["n"] == 2, "不同 report 应是不同缓存键，各自回源一次"


def test_w4b_financial_none_not_cached(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(code, report_type):
        calls["n"] += 1
        return None

    monkeypatch.setattr(rr, "_w4b_financial_fetch", fake_fetch)
    assert rr._w4b_financial("999002", "income") is None
    assert rr._w4b_financial("999002", "income") is None
    assert calls["n"] == 2, "None（瞬时失败）不得缓存，每次应诚实重试"


# ───────────── 2. _sp_core_business TTL 1h ─────────────

class _CountingFetcher:
    def __init__(self, ret):
        self.ret = ret
        self.calls = 0

    def get_core_business(self, code):
        self.calls += 1
        return self.ret


def test_sp_core_business_caches_hit(monkeypatch):
    f = _CountingFetcher("茅台酒及系列酒的生产与销售")
    monkeypatch.setattr("backend.api.market_routes.get_fetcher", lambda: f)
    assert rr._sp_core_business("999003") == "茅台酒及系列酒的生产与销售"
    assert rr._sp_core_business("999003") == "茅台酒及系列酒的生产与销售"
    assert f.calls == 1, "同 code 二次调用应命中 1h 缓存"


def test_sp_core_business_empty_and_exception_not_cached(monkeypatch):
    f_empty = _CountingFetcher("")
    monkeypatch.setattr("backend.api.market_routes.get_fetcher", lambda: f_empty)
    assert rr._sp_core_business("999004") is None
    assert rr._sp_core_business("999004") is None
    assert f_empty.calls == 2, "''（取不到）不应缓存，须每次诚实重试"

    class _Boom:
        def get_core_business(self, code):
            raise RuntimeError("同花顺不可用")

    monkeypatch.setattr("backend.api.market_routes.get_fetcher", lambda: _Boom())
    assert rr._sp_core_business("999004") is None


# ───────────── 3. research-deep 砍 income 源 ─────────────

def _research_deep_src():
    src_path = os.path.join(BACKEND_DIR, "api", "read_routes.py")
    tree = ast.parse(open(src_path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "research_deep":
            return node
    raise AssertionError("read_routes.py 中未找到 research_deep 定义")


def test_research_deep_no_financial_source():
    node = _research_deep_src()
    assert "_w4b_financial" not in ast.dump(node), (
        "research-deep 的 income 源输出不消费（白拉一次 akshare），"
        "应保持三源并行（basic/spot/kline），不得回接 _w4b_financial"
    )


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    from backend.app import create_app
    from backend.config import Config

    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'a.db'}"
        )

    application = create_app(_C)
    return application


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def token(app):
    from backend.extensions import db
    from backend.models import User
    from backend.auth.service import issue_token

    with app.app_context():
        db.create_all()
        u = User(username="cachefixuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_research_deep_does_not_call_financial(client, token, monkeypatch):
    """行为守卫：_w4b_financial 即使存在且会炸，research-deep 也不得调用它。"""
    from datetime import date as _d, timedelta as _td
    import pandas as pd

    base = _d(2026, 11, 5)
    n = 70
    dates = [(base + _td(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    kline = pd.DataFrame({
        "date": dates,
        "open": [1.0] * n, "high": [2.0] * n, "low": [0.5] * n,
        "close": [1.5] * n, "volume": [100.0] * n,
    })
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: {
        "name": "贵州茅台", "industry": "白酒", "price": 1688.0,
        "pe_ttm": 28.1, "market_cap": 21000.0})
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: {
        "datetime": "2026-11-07 15:00:00"})

    def _boom_kline(code, period):
        return kline

    monkeypatch.setattr(rr, "_w4b_kline", _boom_kline)

    def _boom_fin(code, rt):
        raise AssertionError("research-deep 不应调用 _w4b_financial（income 源已砍）")

    monkeypatch.setattr(rr, "_w4b_financial", _boom_fin)

    resp = client.get("/api/v2/read/research-deep?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert d["price"] == 1688.0 and d["market_cap"] == 21000.0
    assert d["deep_analysis_available"] is False
