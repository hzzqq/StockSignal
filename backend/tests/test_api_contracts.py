"""
backend/tests/test_api_contracts.py
-----------------------------------
针对后端三项 API 变更的契约测试（与 test_security.py 正交，不动 12/12）：

  P1-A 认证限流   ：/api/auth/login、/api/auth/register 滑动窗口 60s/5 次，
                   超限 HTTP 429 + 统一信封；提供测试接缝可关闭/重置/读计数。
  P1-C 自选批量   ：POST/DELETE /api/watchlist/batch，严格越权
                   （他人项进 forbidden、deleted 绝不含他人项）。
  P1-B asset_type ：/search、/list、/<code> 返回含 asset_type（默认 "stock"）；
                   /stats 增量新增 asset_type_counts(dict)。

设计约束：
  - 用独立临时 SQLite + _TestConfig 隔离，绝不污染 backend/data/app.db。
  - 限流默认关闭（_TestConfig.RATE_LIMIT_ENABLED=False），仅限流用例单独开启，
    并用 reset_rate_limit() 清场，避免跨用例/跨套件干扰。
  - 不 import、不修改任何 backend 业务实现；只消费契约。
"""
from __future__ import annotations

import os
import sys
import tempfile

# 把项目根（StockSignal）加入 sys.path，保证 `import backend...` 可行
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flask import current_app                          # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from backend.app import create_app                    # noqa: E402
from backend.extensions import db                    # noqa: E402
from backend.config import Config                    # noqa: E402
from backend.models import User, Stock, Watchlist  # noqa: E402
from backend.utils.ratelimit import (                 # noqa: E402
    reset_rate_limit,
    get_hit_count,
    make_key,
)

import pytest                                            # noqa: E402


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def app(tmp_path):
    # 每个用例独立临时库（tmp_path 唯一）+ 限流默认关闭（单测按需开启）。
    # 必须在 create_app 之前把 URI 写进配置类，否则共享引擎不会重绑。
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 't.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        # 种子用户：admin / demo(user) / alice(user)
        for uname, role in (("admin", "admin"), ("demo", "user"), ("alice", "user")):
            if User.query.filter_by(username=uname).first() is None:
                u = User(username=uname, role=role)
                u.set_password("Pass@123")
                db.session.add(u)
        # 种子股票：显式 asset_type + 一个不传 asset_type（验证默认 "stock"）
        seeded = {
            "600519": dict(name="贵州茅台", market="SH", asset_type="stock",
                            pinyin_initials="gzmt", pinyin_full="guizhoumaotai"),
            "000001": dict(name="上证指数", market="SH", asset_type="index",
                            pinyin_initials="szzs", pinyin_full="shangzhengzhishu"),
            "510050": dict(name="50ETF", market="SH", asset_type="etf",
                            pinyin_initials="50etf", pinyin_full="50etf"),
            "999999": dict(name="默认类型股", market="SZ"),  # 不传 asset_type
        }
        for code, kw in seeded.items():
            if Stock.query.filter_by(code=code).first() is None:
                db.session.add(Stock(code=code, **kw))
        db.session.commit()
    yield application
    reset_rate_limit()


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------- 辅助
def _login(client, username, password="Pass@123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _token(client, username="demo", password="Pass@123"):
    r = _login(client, username, password)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _assert_json_envelope(resp, label):
    """断言响应是合法 JSON 信封，并返回解析后的对象。"""
    assert resp.status_code != 404, f"[{label}] 意外 404: {resp.text[:200]}"
    ctype = resp.headers.get("Content-Type", "")
    assert "application/json" in ctype, f"[{label}] 非 JSON: {ctype!r}"
    # force=True：兼容 Content-Type 未带 charset 时 get_json() 返回 None 的情况
    obj = resp.get_json(force=True)
    assert isinstance(obj, dict), f"[{label}] 响应非 JSON 对象: {resp.text[:200]}"
    for k in ("status", "code", "message", "data"):
        assert k in obj, f"[{label}] 缺字段 {k!r}: {obj}"
    return obj


def _get_json(resp, label):
    """安全解析 JSON（force），用于 get_json() 因 Content-Type 问题返回 None 的路由。"""
    obj = resp.get_json(force=True)
    assert isinstance(obj, dict), f"[{label}] 响应非 JSON 对象: {resp.text[:200]}"
    return obj


# ================================================================ P1-A 限流
class TestRateLimit:

    def test_limiter_off_by_default_allows_many(self, client):
        """默认关闭时，连续 10 次登录不应出现 429（隔离性保证）。"""
        for i in range(10):
            r = _login(client, "ratetest_off", password="wrong")
            assert r.status_code != 429, f"第 {i + 1} 次意外被限流"

    def test_rate_limited_after_threshold(self, app, client):
        """同 IP+用户名 60s 内第 6 次请求触发 429 + 统一信封。"""
        app.config["RATE_LIMIT_ENABLED"] = True
        reset_rate_limit()

        ip = "127.0.0.1"
        user = "ratetest_user"
        key = make_key(ip, user)

        statuses = []
        for i in range(6):
            r = _login(client, user, password="wrong")
            statuses.append(r.status_code)

        # 前 5 次非 429（用户不存在 -> 401 信封），第 6 次 429
        assert statuses[:5] == [401, 401, 401, 401, 401], statuses
        assert statuses[5] == 429, statuses

        # 计数接缝：窗口内命中应为 5（第 6 次被拒不再计数）。
        # get_hit_count 内部读 current_app.config，必须在 app 上下文内调用。
        with app.app_context():
            assert get_hit_count(key) == 5, get_hit_count(key)

        # 429 响应结构：统一信封 + JSON
        obj = _assert_json_envelope(client.post(
            "/api/auth/login", json={"username": user, "password": "wrong"}
        ), "rate_limited_body")
        assert obj["status"] == "error"
        assert obj["code"] == "rate_limited"
        assert obj["message"] == "请求过于频繁，请稍后再试"
        assert obj["data"] is None
        reset_rate_limit()

    def test_per_user_isolation(self, app, client):
        """不同用户独立计数：A 触发限流不应影响 B。"""
        app.config["RATE_LIMIT_ENABLED"] = True
        reset_rate_limit()

        # user A 打满 5 次
        for _ in range(5):
            _login(client, "userA", password="wrong")
        assert _login(client, "userA", password="wrong").status_code == 429

        # user B 仍可正常（独立计数）
        assert _login(client, "userB", password="wrong").status_code == 401
        reset_rate_limit()


# ================================================================ P1-C 自选批量
class TestWatchlistBatch:

    def _own(self, client, token, code):
        """让当前用户持有某自选股，返回其 id。"""
        r = client.post("/api/watchlist", json={"stock_code": code},
                        headers=_auth_headers(token))
        assert r.status_code == 200, r.text[:200]
        return _get_json(r, "own")["data"]["id"]

    def test_post_batch_add(self, client):
        token = _token(client, "demo")
        r = client.post("/api/watchlist/batch",
                        json={"codes": ["600519", "000001"], "note": "批量"},
                        headers=_auth_headers(token))
        obj = _assert_json_envelope(r, "watchlist_batch_post")
        assert r.status_code == 200
        assert set(obj["data"]["added"]) == {"600519", "000001"}
        assert obj["data"]["skipped"] == []
        assert obj["data"]["failed"] == []

    def test_post_batch_skip_existing(self, client):
        token = _token(client, "demo")
        # 先加 600519
        self._own(client, token, "600519")
        # 再批量加 600519(已存在->skipped) + 999999(新增->added)
        r = client.post("/api/watchlist/batch",
                        json={"codes": ["600519", "999999"]},
                        headers=_auth_headers(token))
        obj = r.get_json()
        assert "600519" in obj["data"]["skipped"]
        assert "999999" in obj["data"]["added"]

    def test_post_batch_invalid_code_failed(self, client):
        token = _token(client, "demo")
        r = client.post("/api/watchlist/batch",
                        json={"codes": [None, "", 600519]},  # 含非法项
                        headers=_auth_headers(token))
        obj = r.get_json()
        # 非法项进入 failed 且含 reason；合法项照常 added
        assert any(f["code"] in (None, "", 600519) for f in obj["data"]["failed"])
        assert all("reason" in f for f in obj["data"]["failed"])

    def test_post_batch_rejects_non_array(self, client):
        token = _token(client, "demo")
        r = client.post("/api/watchlist/batch", json={"codes": "600519"},
                        headers=_auth_headers(token))
        assert r.status_code == 422  # ValidationError -> 统一信封

    def test_delete_batch_by_ids(self, client):
        token = _token(client, "demo")
        wid = self._own(client, token, "600519")
        r = client.delete("/api/watchlist/batch", json={"ids": [wid]},
                         headers=_auth_headers(token))
        obj = r.get_json()
        assert r.status_code == 200
        assert "600519" in obj["data"]["deleted"]
        assert obj["data"]["forbidden"] == []
        # 数据库层面确实删除
        with client.application.app_context():
            from backend.extensions import db as _db
            from backend.models import Watchlist as _W
            assert _db.session.get(_W, wid) is None

    def test_delete_batch_by_codes(self, client):
        token = _token(client, "demo")
        self._own(client, token, "000001")
        r = client.delete("/api/watchlist/batch", json={"codes": ["000001"]},
                         headers=_auth_headers(token))
        obj = r.get_json()
        assert "000001" in obj["data"]["deleted"]

    def test_delete_strict_ownership_forbidden(self, client):
        """严格越权：alice 尝试删除 demo 的自选股 -> forbidden，绝不进 deleted。"""
        demo_token = _token(client, "demo")
        alice_token = _token(client, "alice")
        # demo 持有 600519
        demo_id = self._own(client, demo_token, "600519")

        # alice 用 id 删 demo 的项
        r = client.delete("/api/watchlist/batch", json={"ids": [demo_id]},
                         headers=_auth_headers(alice_token))
        obj = r.get_json()
        assert r.status_code == 200
        assert obj["data"]["deleted"] == [], "越权项绝不应出现在 deleted"
        assert any(
            f.get("code") == "600519" and f.get("reason") == "无权限访问"
            for f in obj["data"]["forbidden"]
        ), obj["data"]["forbidden"]

        # alice 用 code 删 demo 的项（同样应 forbidden）
        r2 = client.delete("/api/watchlist/batch", json={"codes": ["600519"]},
                          headers=_auth_headers(alice_token))
        obj2 = r2.get_json()
        assert obj2["data"]["deleted"] == []
        assert any(
            f.get("code") == "600519" and f.get("reason") == "无权限访问"
            for f in obj2["data"]["forbidden"]
        )

    def test_delete_not_found_by_id(self, client):
        token = _token(client, "demo")
        # 仅传 ids（避免与 codes 混用被 ids 优先逻辑忽略）
        r = client.delete("/api/watchlist/batch", json={"ids": [99999]},
                         headers=_auth_headers(token))
        obj = _get_json(r, "delete_not_found_id")
        assert r.status_code == 200
        assert "99999" in obj["data"]["not_found"]
        assert obj["data"]["deleted"] == []
        assert obj["data"]["forbidden"] == []

    def test_delete_not_found_by_code(self, client):
        token = _token(client, "demo")
        r = client.delete("/api/watchlist/batch", json={"codes": ["888888"]},
                         headers=_auth_headers(token))
        obj = _get_json(r, "delete_not_found_code")
        assert r.status_code == 200
        assert "888888" in obj["data"]["not_found"]
        assert obj["data"]["deleted"] == []
        assert obj["data"]["forbidden"] == []


# ================================================================ P1-B asset_type
class TestAssetType:

    def test_search_returns_asset_type(self, client):
        token = _token(client, "demo")
        r = client.get("/api/stocks/search?q=600519",
                       headers=_auth_headers(token))
        obj = _assert_json_envelope(r, "stocks_search")
        assert r.status_code == 200
        hits = obj["data"]
        assert isinstance(hits, list) and len(hits) >= 1
        item = next(h for h in hits if h["code"] == "600519")
        assert "asset_type" in item
        assert isinstance(item["asset_type"], str) and item["asset_type"]
        assert item["asset_type"] == "stock"

    def test_list_returns_asset_type(self, client):
        token = _token(client, "admin")
        r = client.get("/api/stocks/list?per_page=50",
                       headers=_auth_headers(token))
        obj = _assert_json_envelope(r, "stocks_list")
        items = obj["data"]["items"]
        assert len(items) >= 1
        # 所有项都带非空 asset_type
        for it in items:
            assert "asset_type" in it
            assert isinstance(it["asset_type"], str) and it["asset_type"]

    def test_detail_asset_type_and_default(self, client):
        token = _token(client, "demo")
        # 显式类型
        r1 = client.get("/api/stocks/000001", headers=_auth_headers(token))
        assert r1.get_json()["data"]["asset_type"] == "index"
        # 未传 asset_type 的种子股 -> 默认 "stock"
        r2 = client.get("/api/stocks/999999", headers=_auth_headers(token))
        obj2 = _assert_json_envelope(r2, "stocks_detail_default")
        assert obj2["data"]["asset_type"] == "stock"

    def test_stats_asset_type_counts_additive(self, client):
        token = _token(client, "admin")
        r = client.get("/api/stocks/stats", headers=_auth_headers(token))
        obj = _assert_json_envelope(r, "stocks_stats")
        d = obj["data"]
        # 原结构不变
        assert {"total", "sh", "sz"} <= set(d.keys())
        # 增量字段：asset_type_counts 为 dict
        assert "asset_type_counts" in d
        assert isinstance(d["asset_type_counts"], dict)
        # 我们种子的类型应出现
        assert d["asset_type_counts"].get("stock", 0) >= 1
        assert d["asset_type_counts"].get("index", 0) >= 1


# ================================================================ 健康检查
class TestHealth:
    def test_health_envelope_and_components(self, client):
        r = client.get("/api/health")
        obj = _assert_json_envelope(r, "health")
        data = obj["data"]
        assert data["service"] == "stocksignal-backend"
        assert data["status"] in ("alive", "degraded")
        # 真实 DB 探针：测试用临时库已 create_all，database 应 ok
        comp = data.get("components", {})
        assert comp.get("backend") == "alive"
        assert comp.get("database") == "ok"
