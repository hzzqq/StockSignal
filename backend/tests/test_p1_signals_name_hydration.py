# -*- coding: utf-8 -*-  # noqa: UP009
"""P1 信号名称水合守卫（read_routes.py::p1_signals）。

真实 JSON 的 top_long/top_short 每项只有 symbol/pred/rank，没有 name；
本测试钉住「本地零网络股票池补 name、未命中写 None、绝不逐票联网查名、
池异常仍 200（全部留空）、原文件不写回」。

为避免依赖真实 data/cache.db，所有用例 monkeypatch load_stock_pool 返回受控 tuple。
"""
from __future__ import annotations

import json
import logging
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
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402
import backend.services.stock_pool_fallback as spf  # noqa: E402
from modules import cache_utils  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_ttl_cache():
    """端点有 5min TTL 缓存，用例前后清空，避免不同临时数据树互相串扰。"""
    cache_utils.clear_cache()
    yield
    cache_utils.clear_cache()


# 受控真实股票池（code 6 位 + name），取自 data/cache.db::all_stocks 真实值
POOL = (
    {"code": "688313", "name": "仕佳光子"},
    {"code": "300814", "name": "中富电路"},
    {"code": "003036", "name": "泰坦股份"},
)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'hyd.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="hyduser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        u = User.query.filter_by(username="hyduser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def client(app, tmp_path, monkeypatch):
    """隔离数据树：p1_signals 目录可写受控 signal_*.json。"""
    data = tmp_path / "data"
    p1 = data / "p1_signals"
    p1.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rr, "_DATA_DIR", data)
    # 默认受控池；个别用例再覆盖
    monkeypatch.setattr(spf, "load_stock_pool", lambda: POOL)
    # 红线守卫：任何用例一旦走逐票网络查名立刻失败（p1_signals 不得调用该层）。
    def _forbidden_qq(code):
        raise AssertionError(f"p1-signals 不得调用 _qq_spot_single 查名: {code}")

    monkeypatch.setattr(rr, "_qq_spot_single", _forbidden_qq)
    return app.test_client()


def _write_signal(p1_dir, name, payload):
    """写一份信号文件；返回绝对路径（用于反证原文件未被写回）。"""
    fp = p1_dir / name
    fp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return fp


def _sig(long_items=None, short_items=None, **extra):
    base = {
        "generated_at": "2026-11-18T13:44:37",
        "latest_date": "2026-11-17",
        "model": "baseline20",
        "top_long": long_items or [],
        "top_short": short_items or [],
    }
    base.update(extra)
    return base


def _item(symbol, pred, rank):
    return {"symbol": symbol, "pred": pred, "rank": rank}


def _get(client, token):
    resp = client.get("/api/v2/read/p1-signals", headers=_auth(token))
    return resp, resp.get_json()


def test_name_hydrated_and_fields_preserved(client, token, tmp_path):
    """命中池：补真实 name，归一取 symbol 尾 6 位，pred/rank 与消费字段不变，原文件不写回。

    瘦身边界：daily/model/horizon 等无人消费的原始字段不得透出。
    """
    p1 = tmp_path / "data" / "p1_signals"
    fp = _write_signal(
        p1,
        "signal_ev.json",
        _sig(
            long_items=[_item("sh688313", 0.1079, 1.0)],
            short_items=[_item("sz300814", 0.1066, 0.9986)],
            horizon=20,
        ),
    )
    raw_before = fp.read_text(encoding="utf-8")

    resp, obj = _get(client, token)
    assert resp.status_code == 200 and obj["status"] == "ok", obj
    sig = obj["data"]["signal_ev.json"]

    long0 = sig["top_long"][0]
    short0 = sig["top_short"][0]
    assert long0["name"] == "仕佳光子", long0          # sh688313 -> 688313
    assert short0["name"] == "中富电路", short0        # sz300814 -> 300814
    # pred / rank 原样保留
    assert long0["pred"] == 0.1079 and long0["rank"] == 1.0
    assert short0["pred"] == 0.1066 and short0["rank"] == 0.9986
    # 消费字段原样保留；大字段全部剔除（前端 schema 里是 optional，不消费）
    assert sig["generated_at"] == "2026-11-18T13:44:37"
    assert sig["latest_date"] == "2026-11-17"
    assert set(sig) == {"generated_at", "latest_date", "top_long", "top_short"}, sig
    for dropped in ("daily", "model", "horizon", "quality"):
        assert dropped not in sig, dropped
    # 原 JSON 文件未被写回（无 name 字段）
    assert fp.read_text(encoding="utf-8") == raw_before
    assert "name" not in json.loads(raw_before)["top_long"][0]


def test_normalization_tail6_with_and_without_prefix(client, token, tmp_path):
    """归一口径：无论 sh/sz 前缀还是裸代码，都取尾 6 位查映射。"""
    p1 = tmp_path / "data" / "p1_signals"
    _write_signal(
        p1,
        "signal_norm.json",
        _sig(
            long_items=[
                _item("688313", 0.1, 1.0),   # 裸 6 位
                _item("sz003036", 0.2, 2.0),  # 带 sz 前缀
            ],
        ),
    )
    _, obj = _get(client, token)
    sig = obj["data"]["signal_norm.json"]
    assert sig["top_long"][0]["name"] == "仕佳光子"
    assert sig["top_long"][1]["name"] == "泰坦股份"  # sz003036 -> 003036


def test_missing_code_name_is_none(client, token, tmp_path):
    """池缺该代码且腾讯实时层也查不到 -> name=None（诚实空，绝不编造/补空字符串）。"""
    p1 = tmp_path / "data" / "p1_signals"
    _write_signal(
        p1,
        "signal_missing.json",
        _sig(long_items=[_item("sh600519", 0.3, 1.0)]),  # 600519 不在受控池
    )
    _, obj = _get(client, token)
    item = obj["data"]["signal_missing.json"]["top_long"][0]
    assert item["name"] is None, item
    assert item["symbol"] == "sh600519" and item["pred"] == 0.3


def test_missing_new_listing_name_is_none_no_network(client, token, tmp_path):
    """池子快照滞后于新股上市（实证 sh688825 长鑫科技）-> name=None（诚实空）。

    钉两件事：① 池子命中的代码补真名；② 池子未命中的代码不再逐票联网查名，
    即便腾讯层存在也不调用（client fixture 把它设成「调用即失败」）。
    """
    p1 = tmp_path / "data" / "p1_signals"
    _write_signal(
        p1,
        "signal_new_listing.json",
        _sig(
            long_items=[
                _item("sh688313", 0.1079, 1.0),  # 池子命中
                _item("sh688825", 0.0954, 0.989),  # 池子缺（新股，可能查得到真名也不查）
            ],
        ),
    )
    resp, obj = _get(client, token)
    assert resp.status_code == 200 and obj["status"] == "ok", obj
    items = obj["data"]["signal_new_listing.json"]["top_long"]
    assert items[0]["name"] == "仕佳光子"  # 池子命中，补真名
    assert items[1]["name"] is None, items[1]  # 池子未命中，诚实留空
    assert items[1]["symbol"] == "sh688825" and items[1]["pred"] == 0.0954


def test_empty_pool_all_none(client, token, tmp_path, monkeypatch):
    """空池 -> 端点仍 ok，所有项 name=None。"""
    monkeypatch.setattr(spf, "load_stock_pool", lambda: ())
    p1 = tmp_path / "data" / "p1_signals"
    _write_signal(
        p1,
        "signal_empty_pool.json",
        _sig(
            long_items=[_item("sh688313", 0.1, 1.0)],
            short_items=[_item("sz300814", 0.2, 0.5)],
        ),
    )
    _, obj = _get(client, token)
    assert obj["status"] == "ok", obj
    sig = obj["data"]["signal_empty_pool.json"]
    assert all(it["name"] is None for it in sig["top_long"] + sig["top_short"])


def test_multi_signal_both_sides(client, token, tmp_path):
    """多信号文件、top_long 与 top_short 都覆盖。"""
    p1 = tmp_path / "data" / "p1_signals"
    _write_signal(
        p1,
        "signal_a.json",
        _sig(
            long_items=[_item("sh688313", 0.11, 1.0)],
            short_items=[_item("sz300814", 0.12, 0.9)],
        ),
    )
    _write_signal(
        p1,
        "signal_b.json",
        _sig(
            long_items=[_item("sz003036", 0.21, 1.0)],
            short_items=[_item("sh600519", 0.22, 0.9)],
        ),
    )
    _, obj = _get(client, token)
    a = obj["data"]["signal_a.json"]
    b = obj["data"]["signal_b.json"]
    assert a["top_long"][0]["name"] == "仕佳光子"
    assert a["top_short"][0]["name"] == "中富电路"
    assert b["top_long"][0]["name"] == "泰坦股份"
    assert b["top_short"][0]["name"] is None  # 600519 不在受控池


def test_pool_exception_degrades_to_none_names_with_warning(
    client, token, tmp_path, monkeypatch, caplog
):
    """本地股票池抛异常 -> 端点仍 200、所有 name=None（诚实空）、warning 留痕。"""
    def _boom():
        raise RuntimeError("pool exploded (simulated)")

    monkeypatch.setattr(spf, "load_stock_pool", _boom)
    p1 = tmp_path / "data" / "p1_signals"
    _write_signal(
        p1,
        "signal_boom.json",
        _sig(long_items=[_item("sh688313", 0.1079, 1.0)], horizon=10),
    )

    with caplog.at_level(logging.WARNING, logger="backend.api.read_routes"):
        resp, obj = _get(client, token)

    assert resp.status_code == 200 and obj["status"] == "ok", obj
    item = obj["data"]["signal_boom.json"]["top_long"][0]
    assert item["name"] is None, item  # 池不可用即查不到，不编造、不联网
    assert item["symbol"] == "sh688313" and item["pred"] == 0.1079 and item["rank"] == 1.0
    sig = obj["data"]["signal_boom.json"]
    assert "horizon" not in sig and "daily" not in sig and "model" not in sig
    assert any("本地股票池不可用" in r.getMessage() for r in caplog.records), caplog.text
