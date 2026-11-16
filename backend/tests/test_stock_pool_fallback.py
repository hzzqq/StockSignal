"""
股票搜索兜底守卫（2026-11-16，截图反馈「完善股票搜索机制」）。

实证背景：`stocks` 表在真实部署为 0 行，导致 /api/stocks/search 对
代码 / 中文名 / 拼音首字母一律返回 []。本组用例锁住三件事：
  1. 兜底池来自 v1 真实股票池，字段与 Stock.to_dict() 契约一致；
  2. 代码 / 名称 / 首字母 / 全拼四种输入都能命中同一只票，评分口径不漂移；
  3. 池缺失 / 空查询 / 无匹配时诚实返回空，绝不编造、不补零；
  4. stocks 表一旦有数据，兜底不得插手（避免改变既有排序语义）。
"""
from __future__ import annotations

import pytest

from backend.app import create_app
from backend.config import Config
from backend.extensions import db
from backend.models import Stock, User
from backend.services import stock_pool_fallback as pool


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 't.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        u = User(username="demo", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    yield application


def _token(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Pass@123"})
    assert r.status_code == 200, r.text[:200]
    return r.get_json()["data"]["token"]


# ---------------------------------------------------------------- 纯函数
def test_pool_is_real_and_contract_shaped():
    pool.load_stock_pool.cache_clear()
    items = pool.load_stock_pool()
    assert len(items) >= 5000, "真实股票池应来自 data/cache.db::all_stocks"
    mt = next((x for x in items if x["code"] == "600519"), None)
    assert mt is not None
    assert mt["name"] == "贵州茅台"
    assert mt["market"] == "SH"
    assert mt["pinyin_initials"] == "gzmt"
    assert mt["pinyin_full"] == "guizhoumaotai"
    # 与 Stock.to_dict() 字段集合一致（不含 score）
    expected = {"code", "name", "market", "asset_type", "pinyin_initials", "pinyin_full"}
    assert set(mt) == expected


@pytest.mark.parametrize(
    "query, expect_score",
    [
        ("600519", 1000),          # 代码精确
        ("贵州茅台", 900),          # 名称精确
        ("gzmt", 600),             # 拼音首字母精确
        ("guizhoumaotai", 500),    # 全拼前缀
    ],
)
def test_four_match_channels_hit_same_stock(query, expect_score):
    pool.load_stock_pool.cache_clear()
    hits = pool.search_stock_pool(query, limit=10)
    assert hits, f"{query} 应命中真实股票"
    mt = next((h for h in hits if h["code"] == "600519"), None)
    assert mt is not None, f"{query} 未命中 600519"
    assert mt["score"] >= expect_score - 100, (query, mt["score"])
    assert mt["asset_type"] == "stock"


def test_code_prefix_and_name_contains():
    pool.load_stock_pool.cache_clear()
    assert any(h["code"].startswith("60051") for h in pool.search_stock_pool("60051", limit=10))
    assert any(h["code"] == "600519" for h in pool.search_stock_pool("茅台", limit=10))


def test_no_match_and_empty_query_are_honest_empty():
    pool.load_stock_pool.cache_clear()
    assert pool.search_stock_pool("", limit=10) == []
    assert pool.search_stock_pool("zzzzzz", limit=10) == []
    assert pool.search_stock_pool("不存在的股票xyz", limit=10) == []


def test_missing_pool_file_returns_empty_without_fabrication(monkeypatch, tmp_path):
    monkeypatch.setattr(pool, "_CACHE_DB", tmp_path / "missing.db")
    pool.load_stock_pool.cache_clear()
    assert pool.load_stock_pool() == ()
    assert pool.pool_size() == 0
    assert pool.search_stock_pool("600519", limit=10) == []
    pool.load_stock_pool.cache_clear()  # 还原缓存，避免污染后续用例


# ---------------------------------------------------------------- 端点集成
def test_endpoint_uses_pool_when_stocks_table_empty(app):
    pool.load_stock_pool.cache_clear()
    c = app.test_client()
    with app.app_context():
        assert Stock.query.count() == 0
    token = _token(c)
    headers = {"Authorization": f"Bearer {token}"}
    for q in ("600519", "%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0", "gzmt"):
        r = c.get(f"/api/stocks/search?q={q}", headers=headers)
        assert r.status_code == 200, r.text[:200]
        obj = r.get_json()
        assert obj["status"] == "ok"
        assert any(h["code"] == "600519" for h in obj["data"]), (q, obj["data"][:2])


def test_endpoint_prefers_table_when_seeded(app):
    """表内有数据 -> 走原 search_stocks；兜底不得把 v1 池混进来改排序。"""
    pool.load_stock_pool.cache_clear()
    with app.app_context():
        db.session.add(Stock(
            code="600519", name="自定义名称", market="SH", asset_type="stock",
            pinyin_initials="zdy", pinyin_full="zidingyimingcheng",
        ))
        db.session.commit()
    c = app.test_client()
    token = _token(c)
    r = c.get("/api/stocks/search?q=600519", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    hits = r.get_json()["data"]
    assert hits and hits[0]["code"] == "600519"
    assert hits[0]["name"] == "自定义名称", "不得被 v1 股票池覆盖"
