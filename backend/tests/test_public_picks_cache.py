# -*- coding: utf-8 -*-  # noqa: UP009
"""public-picks P1 解析 TTL 缓存守卫（read_routes.py::public_picks）。

背景：登录页 public-picks 每次请求都逐个解析 data/p1_signals/signal_*.json
（每个 ~10MB），冷启动慢。现与 /p1-signals 同款 cached_ttl（TTL_TIERS["sentiment"]
=300s，键含数据目录）。守卫点：
  1. 同参数（同数据目录）第二次调用命中缓存，不再重复解析文件；
  2. 不同数据目录 -> 不同缓存键，各自独立解析；
  3. 诚实语义：无有效信号 -> stocks=[] / stocks_as_of=None，不补 0 不编造；
  4. 前端契约不变：响应字段仍为 stocks/stocks_as_of/sectors/disclaimer。
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

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402
import backend.services.stock_pool_fallback as spf  # noqa: E402
import modules.fundflow as fundflow_mod  # noqa: E402
from modules import cache_utils  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_ttl_cache():
    """端点有 5min TTL，用例前后清空，避免临时数据树之间串扰。"""
    cache_utils.clear_cache()
    yield
    cache_utils.clear_cache()


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'pp.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="ppuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture
def client(app, tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "p1_signals").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rr, "_DATA_DIR", data)
    monkeypatch.setattr(spf, "load_stock_pool", lambda: (
        {"code": "688313", "name": "仕佳光子"},
    ))

    # 离线确定性：行业资金流上游直接打挂 -> sectors 优雅降级 []（既有语义）。
    def _offline(*_a, **_kw):
        raise ConnectionError("offline test")

    monkeypatch.setattr(fundflow_mod, "get_industry_fund_flow", _offline)
    return app.test_client()


def _write(p1_dir, name, payload):
    fp = p1_dir / name
    fp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return fp


def _get(client):
    r = client.get("/api/v2/read/public-picks")
    return r, r.get_json()


def _sig_payload(latest_date, symbol="sh688313"):
    return {
        "generated_at": f"{latest_date}T10:00:00",
        "latest_date": latest_date,
        "top_long": [{"symbol": symbol, "pred": 0.1079, "rank": 1.0}],
        "top_short": [],
        "daily": [{"date": latest_date, "pred": 0.3}] * 500,
    }


def test_cache_hit_does_not_reread_files(client, tmp_path, monkeypatch):
    """同一数据目录第二次调用命中缓存：解析次数从 2 降到 1，两次响应一致。"""
    p1 = tmp_path / "data" / "p1_signals"
    _write(p1, "signal_a.json", _sig_payload("2026-11-21"))
    real_read = rr._read_json
    calls = []

    def _counting_read(path):
        calls.append(str(path))
        return real_read(path)

    monkeypatch.setattr(rr, "_read_json", _counting_read)
    r1, obj1 = _get(client)
    r2, obj2 = _get(client)
    assert r1.status_code == r2.status_code == 200
    assert len(calls) == 1, f"二次请求应命中缓存只解析一次，实测 {calls}"
    assert obj1 == obj2
    assert any(k.startswith("public_picks_p1:") for k in cache_utils._CACHE), (
        "public-picks 的 P1 解析结果应进入进程级 TTL 缓存"
    )
    # 契约与语义：取 latest_date 最新的文件，名称从池子水合
    assert obj1["data"]["stocks_as_of"] == "2026-11-21"
    assert obj1["data"]["stocks"][0]["name"] == "仕佳光子"


def test_different_data_dir_different_cache_key(client, tmp_path, monkeypatch):
    """不同数据目录 -> 不同缓存键，各自独立解析、互不串数据。"""
    real_read = rr._read_json
    calls = []

    def _counting_read(path):
        calls.append(str(path))
        return real_read(path)

    monkeypatch.setattr(rr, "_read_json", _counting_read)

    base = tmp_path / "data"
    _write(base / "p1_signals", "signal_a.json", _sig_payload("2026-11-21"))
    _, obj_a = _get(client)

    other = tmp_path / "other_data"
    (other / "p1_signals").mkdir(parents=True)
    _write(other / "p1_signals", "signal_b.json", _sig_payload("2026-11-24", "sz000001"))
    monkeypatch.setattr(rr, "_DATA_DIR", other)
    _, obj_b = _get(client)

    keys = [k for k in cache_utils._CACHE if k.startswith("public_picks_p1:")]
    assert len(keys) == 2, f"两个数据目录应产生两个独立缓存键，实测 {keys}"
    assert len(calls) == 2, f"不同键各自解析一次，实测 {calls}"
    assert obj_a["data"]["stocks_as_of"] == "2026-11-21"
    assert obj_b["data"]["stocks_as_of"] == "2026-11-24"
    assert obj_b["data"]["stocks"][0]["code"] == "000001"


def test_missing_data_honest_empty(client):
    """无有效信号文件 -> stocks=[] / stocks_as_of=None，不补 0 不编造。"""
    _, obj = _get(client)
    assert obj["status"] == "ok"
    assert obj["data"]["stocks"] == []
    assert obj["data"]["stocks_as_of"] is None
    assert obj["data"]["sectors"] == []  # 上游打挂优雅降级，不编造板块
    assert obj["data"]["disclaimer"]


def test_corrupt_file_skipped_honestly(client, tmp_path):
    """坏 JSON 文件被跳过，不 500、不编造；响应契约字段不变。"""
    p1 = tmp_path / "data" / "p1_signals"
    (p1 / "signal_bad.json").write_text("{not-json", encoding="utf-8")
    r, obj = _get(client)
    assert r.status_code == 200 and obj["status"] == "ok"
    assert obj["data"]["stocks"] == [] and obj["data"]["stocks_as_of"] is None


def test_response_contract_unchanged(client, tmp_path):
    """前端契约：响应 data 字段仍为 stocks/stocks_as_of/sectors/disclaimer 四键。"""
    p1 = tmp_path / "data" / "p1_signals"
    _write(p1, "signal_a.json", _sig_payload("2026-11-21"))
    _, obj = _get(client)
    assert set(obj["data"]) == {"stocks", "stocks_as_of", "sectors", "disclaimer"}
    assert obj["data"]["stocks"][0].keys() >= {"code", "name", "pred"}
