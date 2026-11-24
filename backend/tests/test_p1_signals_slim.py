# -*- coding: utf-8 -*-  # noqa: UP009
"""P1 信号端点瘦身 + 零网络查名 + TTL 缓存守卫（read_routes.py::p1_signals）。

诚实红线：池子未命中的代码 name 一律 None，绝不逐票联网查名、绝不编造；
前端只消费 generated_at/latest_date/top_long/top_short，大字段 daily 等必须剔除。
"""
from __future__ import annotations

import ast
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
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402
import backend.services.stock_pool_fallback as spf  # noqa: E402
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
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'slim.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="slimuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        return issue_token(User.query.filter_by(username="slimuser").first())


@pytest.fixture
def client(app, tmp_path, monkeypatch):
    data = tmp_path / "data"
    p1 = data / "p1_signals"
    p1.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rr, "_DATA_DIR", data)
    monkeypatch.setattr(spf, "load_stock_pool", lambda: (
        {"code": "688313", "name": "仕佳光子"},
    ))

    def _forbidden_qq(code):
        raise AssertionError(f"p1-signals 不得逐票联网查名: {code}")

    monkeypatch.setattr(rr, "_qq_spot_single", _forbidden_qq)
    return app.test_client()


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _write(p1_dir, name, payload):
    fp = p1_dir / name
    fp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return fp


def _get(client, token):
    r = client.get("/api/v2/read/p1-signals", headers=_auth(token))
    return r, r.get_json()


def _p1_ast():
    from pathlib import Path

    src = (Path(BACKEND_DIR) / "api" / "read_routes.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "p1_signals":
            return node
    raise AssertionError("read_routes.py 中未找到 p1_signals 定义")


def test_no_per_stock_network_lookup_in_source():
    """AST 守卫：p1_signals 函数体不得再调用 _qq_spot_single（零网络红线）。

    只看标识符引用，不看文档字符串（说明「不得调用」时会提到该函数名）。
    """
    node = _p1_ast()
    referenced = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    referenced |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    assert "_qq_spot_single" not in referenced, (
        "p1-signals 名称水合必须只用本地股票池，不得逐票联网查名"
    )


def test_unmatched_code_never_calls_qq(client, token, tmp_path):
    """行为守卫：池子未命中的新股即便能在腾讯查到真名，也不得调用（诚实留空）。"""
    p1 = tmp_path / "data" / "p1_signals"

    # client fixture 已把 _qq_spot_single 设为「调用即失败」，无需重复打桩。
    _write(p1, "signal_new.json", {
        "generated_at": "2026-11-24T10:00:00",
        "latest_date": "2026-11-21",
        "top_long": [{"symbol": "sh688825", "pred": 0.12, "rank": 1.0}],
        "top_short": [],
        "daily": [{"date": "2026-11-21", "x": 1}],
        "model": "baseline20",
        "horizon": 20,
    })
    resp, obj = _get(client, token)
    assert resp.status_code == 200 and obj["status"] == "ok", obj
    item = obj["data"]["signal_new.json"]["top_long"][0]
    assert item["name"] is None, item
    assert item["symbol"] == "sh688825" and item["pred"] == 0.12 and item["rank"] == 1.0


def test_slim_response_keeps_only_consumed_fields(client, token, tmp_path):
    """响应体剔除 daily/model/horizon/quality；消费字段与项内 symbol/pred/rank 完整。"""
    p1 = tmp_path / "data" / "p1_signals"
    _write(p1, "signal_slim.json", {
        "generated_at": "2026-11-24T10:00:00",
        "latest_date": "2026-11-21",
        "model": "baseline20",
        "horizon": 20,
        "quality": {"score": 0.9},
        "daily": [{"date": "2026-11-21", "pred": 0.3}] * 500,
        "top_long": [{"symbol": "sh688313", "pred": 0.1079, "rank": 1.0}],
        "top_short": [{"symbol": "sz300814", "pred": -0.02, "rank": 0.9}],
    })
    _, obj = _get(client, token)
    sig = obj["data"]["signal_slim.json"]
    assert set(sig) == {"generated_at", "latest_date", "top_long", "top_short"}, sig
    assert sig["generated_at"] == "2026-11-24T10:00:00"
    assert sig["latest_date"] == "2026-11-21"
    long0 = sig["top_long"][0]
    assert long0 == {
        "symbol": "sh688313", "pred": 0.1079, "rank": 1.0, "name": "仕佳光子",
    }, long0  # 池子命中补真名
    short0 = sig["top_short"][0]
    assert short0["name"] is None and short0["symbol"] == "sz300814"  # 未命中留空
    assert "daily" not in json.dumps(obj), "大字段 daily 不得出现在响应体"


def test_cache_hit_does_not_reread_files(client, token, tmp_path, monkeypatch):
    """TTL 缓存命中时不再重复解析文件；两次响应一致。"""
    p1 = tmp_path / "data" / "p1_signals"
    _write(p1, "signal_cached.json", {
        "generated_at": "2026-11-24T10:00:00",
        "latest_date": "2026-11-21",
        "top_long": [{"symbol": "sh688313", "pred": 0.5, "rank": 1.0}],
        "top_short": [],
        "daily": [1] * 1000,
    })
    real_read = rr._read_json
    calls = []

    def _counting_read(path):
        calls.append(str(path))
        return real_read(path)

    monkeypatch.setattr(rr, "_read_json", _counting_read)
    _, first = _get(client, token)
    _, second = _get(client, token)
    assert len(calls) == 1, f"二次请求应命中缓存，只读一次文件，实测 {calls}"
    assert first == second
    assert any(k.startswith("p1_signals:") for k in cache_utils._CACHE), (
        "端点结果应进入进程级 TTL 缓存"
    )


def test_missing_dir_still_honest_not_found(client, token, tmp_path):
    """目录不存在 -> not_found(200)，与瘦身/缓存无关，语义不变。"""
    (tmp_path / "data" / "p1_signals").rmdir()
    resp, obj = _get(client, token)
    assert resp.status_code == 200 and obj["status"] == "error", obj
