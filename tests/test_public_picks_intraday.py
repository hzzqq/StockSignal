# -*- coding: utf-8 -*-  # noqa: UP009
"""登录页公开摘要二批端点守卫（2026-11-21 老板需求）。

  - GET /api/v2/read/public-index-intraday — 上证指数当日 5 分钟分时（无鉴权脱敏）
  - GET /api/v2/read/public-picks          — 今日股票(P1 top_long 前5) + 板块(行业净额前3)

锁五件事：
  1. 无 token 可访问（200），字段形状正确；
  2. 分时：昨收基准取上一交易日收盘 bar（真实数据），当日 rows 只含 time/close；
  3. picks：按数据日 latest_date 降序选最新信号文件（不用 mtime），名称水合未命中 -> None；
  4. 诚实红线：取不到 -> rows=[] / stocks=[] / sectors=[]，绝不编造；
  5. 契约守卫登记（防漂移）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402

import backend.api.read_routes as rr  # noqa: E402
from modules import cache_utils  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 't.db'}"

    app = create_app(_C)
    with app.app_context():
        db.create_all()
        u = User(username="admin", role="admin")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_ttl_cache():
    """TTL 进程级缓存会串测试：每例前后清空（两个新端点都走 cached_ttl）。"""
    cache_utils._CACHE.clear()
    yield
    cache_utils._CACHE.clear()


def _fake_index_df():
    """两个交易日的 5 分钟 bar：11-21 当日 2 根 + 11-20 前日 2 根（末根=昨收）。"""
    return pd.DataFrame([
        {"time": "2026-11-20 14:55:00", "open": 3400.0, "high": 3401.0, "low": 3399.0, "close": 3400.5},
        {"time": "2026-11-20 15:00:00", "open": 3400.5, "high": 3402.0, "low": 3400.0, "close": 3401.0},
        {"time": "2026-11-21 09:35:00", "open": 3402.0, "high": 3404.0, "low": 3401.0, "close": 3403.0},
        {"time": "2026-11-21 09:40:00", "open": 3403.0, "high": 3405.0, "low": 3402.0, "close": 3404.5},
    ])


def test_index_intraday_no_auth_shape(client, monkeypatch):
    monkeypatch.setattr(rr, "_public_index_intraday_fetch", _fake_index_df)
    r = client.get("/api/v2/read/public-index-intraday")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok", body
    data = body["data"]
    assert data["code"] == "sh000001" and data["name"] == "上证指数"
    assert data["date"] == "2026-11-21"
    assert data["prev_close"] == 3401.0, "昨收=上一交易日末根 close（真实数据）"
    rows = data["rows"]
    assert [x["time"] for x in rows] == ["2026-11-21 09:35:00", "2026-11-21 09:40:00"]
    assert rows[0]["close"] == 3403.0
    assert set(rows[0].keys()) == {"time", "close"}, "脱敏：只透传 time/close"


def test_index_intraday_honest_empty(client, monkeypatch):
    monkeypatch.setattr(rr, "_public_index_intraday_fetch", lambda: None)
    r = client.get("/api/v2/read/public-index-intraday")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["date"] is None and data["prev_close"] is None and data["rows"] == []


def _write_signal(path: Path, latest_date: str, codes: list[str]):
    path.write_text(json.dumps({
        "generated_at": f"{latest_date}T15:00:00",
        "latest_date": latest_date,
        "model": "v41blend_w30",
        "horizon": 10,
        "top_long": [{"symbol": s, "pred": 0.1, "rank": 1.0} for s in codes],
        "top_short": [],
        "daily": [],
    }, ensure_ascii=False), encoding="utf-8")


def test_picks_latest_by_data_date_not_mtime(client, monkeypatch, tmp_path):
    """选择口径：按 latest_date 降序选最新（mtime 仅并列次键）——mtime 旧的文件数据更新。"""
    sig = tmp_path / "p1_signals"
    sig.mkdir()
    f_old_data_new = sig / "signal_a.json"
    f_new_data_old = sig / "signal_b.json"
    _write_signal(f_old_data_new, "2026-11-20", ["sh688519"])
    _write_signal(f_new_data_old, "2026-11-17", ["sz300394"])
    import os
    os.utime(f_old_data_new, (1, 1))  # mtime 更旧，但数据日更新 -> 必须选它
    os.utime(f_new_data_old, (2e9, 2e9))
    monkeypatch.setattr(rr, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(rr, "_public_stock_name_map", lambda: {"688519": "某芯片"})
    monkeypatch.setattr(rr, "_public_top_sectors", lambda: [])
    r = client.get("/api/v2/read/public-picks")
    data = r.get_json()["data"]
    assert data["stocks_as_of"] == "2026-11-20"
    assert [s["code"] for s in data["stocks"]] == ["688519"]
    assert data["stocks"][0]["name"] == "某芯片"


def test_picks_name_miss_is_none(client, monkeypatch, tmp_path):
    sig = tmp_path / "p1_signals"
    sig.mkdir()
    _write_signal(sig / "signal_a.json", "2026-11-20", ["sh999999"])
    monkeypatch.setattr(rr, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(rr, "_public_stock_name_map", lambda: {})
    monkeypatch.setattr(rr, "_public_top_sectors", lambda: [{"industry": "电池", "chg_pct": -1.2, "net": "-12.50亿"}])
    r = client.get("/api/v2/read/public-picks")
    data = r.get_json()["data"]
    assert data["stocks"][0]["name"] is None, "名称水合未命中 -> None（前端显示 —），绝不编造"
    assert data["sectors"][0]["industry"] == "电池"
    assert "不构成投资建议" in data["disclaimer"]


def test_picks_no_signals_graceful(client, monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(rr, "_public_top_sectors", lambda: [])
    r = client.get("/api/v2/read/public-picks")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["stocks"] == [] and data["stocks_as_of"] is None and data["sectors"] == []


def test_picks_sectors_honest_when_source_fails(client, monkeypatch, tmp_path):
    """行业资金流源异常 -> sectors=[]（_public_top_sectors 内部兜底口径）。"""
    sig = tmp_path / "p1_signals"
    sig.mkdir()
    _write_signal(sig / "signal_a.json", "2026-11-20", ["sh688519"])
    monkeypatch.setattr(rr, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(rr, "_public_stock_name_map", lambda: {})
    monkeypatch.setattr(rr, "_public_top_sectors", lambda: [])
    r = client.get("/api/v2/read/public-picks")
    data = r.get_json()["data"]
    assert data["sectors"] == []


def test_picks_sectors_float_net_gets_yi_unit(monkeypatch):
    """净额列 float64（单位亿）-> 纯数值补「亿」文本；带单位原文原样透传。"""
    import modules.fundflow as ff

    df = pd.DataFrame([
        {"行业": "银行", "涨跌幅": 0.21, "净额": 43.12},
        {"行业": "保险", "涨跌幅": 0.39, "净额": "-12.50亿"},  # 若上游改文本口径
    ])
    monkeypatch.setattr("modules.fundflow.get_industry_fund_flow", lambda: df)
    cache_utils._CACHE.clear()
    try:
        out = rr._public_top_sectors()
    finally:
        cache_utils._CACHE.clear()
    assert out[0]["industry"] == "银行"
    assert out[0]["net"] == "43.12亿", out[0]["net"]
    assert out[0]["chg_pct"] == 0.21
    assert out[1]["net"] == "-12.50亿", "带单位原文不重复补单位"


def test_new_endpoints_registered_in_contract_guard():
    src = (ROOT / "tests" / "test_read_contract_drift.py").read_text(encoding="utf-8")
    assert "/api/v2/read/public-index-intraday" in src
    assert "/api/v2/read/public-picks" in src
    fe = (ROOT / "frontend-v2" / "src" / "api" / "schemas" / "read.ts").read_text(encoding="utf-8")
    assert "PublicIndexIntradaySchema" in fe and "PublicPicksSchema" in fe
