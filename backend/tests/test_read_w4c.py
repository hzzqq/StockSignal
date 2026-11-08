# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_read_w4c.py — W4-C 三端点（compare-one / research-deep / stock-intraday）回归守卫。

严格镜像 W4-B 测试范式：monkeypatch 模块级 _w4b_* / _w4c_* 取数源，零网络，
绝不真调 akshare / 新浪 / 东财 / BaoStock。验证：

  1. 每个端点无 token -> 401（鉴权闸门）；
  2. 有合法 token + 取数源齐备 -> 200 + 标准 ok 信封 + 契约字段齐全 + 真值正确；
  3. 非法 / 缺失 code -> 400 invalid_param（校验先于取数，零网络）；
  4. 某字段 / 某源取不到 -> 对应字段 null（禁止补 0 / 50 /「持有」等编造）；
  5. 取数源抛异常 / 整批超时 -> 对应字段 null 且 status 仍 ok（绝不 500）；
  6. date 必须是 null 或权威数据日，绝不为 now()；
  7. stock-intraday 底层源存在 -> 无数据时诚实返回 rows=[] / date=null / status ok
     （不走 not_found，因底层 fetcher 已落地）。
"""
from __future__ import annotations

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


# ───────────── fixtures（与 test_read_routes.py 同款，隔离 DB/token）─────────────

@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'a.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="w4cuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        u = User.query.filter_by(username="w4cuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ───────────── 假取数源（零网络）─────────────

def _fake_basic():
    return {"name": "贵州茅台", "industry": "白酒", "price": 1688.0,
            "pe_ttm": 28.1, "market_cap": 21000.0}


def _fake_spot():
    return {"datetime": "2026-11-07 15:00:00", "current": 1688.0}


def _fake_kline(n=3):
    """n 根日线（date/open/high/low/close/volume），末根为权威数据日。"""
    from datetime import date as _d, timedelta as _td
    import pandas as pd
    base = _d(2026, 11, 5)
    dates = [(base + _td(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    return pd.DataFrame({
        "date": dates,
        "open": [float(i) for i in range(1, 1 + n)],
        "high": [float(i) + 0.5 for i in range(1, 1 + n)],
        "low": [float(i) - 0.5 for i in range(1, 1 + n)],
        "close": [float(i) + 0.1 for i in range(1, 1 + n)],
        "volume": [100.0 * (i + 1) for i in range(n)],
    })


def _fake_kline_long(n=70):
    """>=60 根，用于 research-deep 的 ma60 / amplitude 真值断言。close=1..n。"""
    from datetime import date as _d, timedelta as _td
    import pandas as pd
    base = _d(2026, 11, 5)
    dates = [(base + _td(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    closes = [float(i) for i in range(1, 1 + n)]
    return pd.DataFrame({
        "date": dates,
        "open": [c - 0.1 for c in closes],
        "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes],
        "close": closes,
        "volume": [100.0 * (i + 1) for i in range(n)],
    })


def _fake_intraday_df():
    """分时 DataFrame（time/open/high/low/close/volume/amount），列名原样。"""
    import pandas as pd
    return pd.DataFrame({
        "time": ["2026-11-07 09:31:00", "2026-11-07 09:32:00", "2026-11-07 15:00:00"],
        "open": [1688.0, 1689.0, 1690.0],
        "high": [1689.0, 1690.0, 1691.0],
        "low": [1687.0, 1688.0, 1689.0],
        "close": [1688.5, 1689.5, 1690.5],
        "volume": [1000.0, 1100.0, 1200.0],
        "amount": [1.6e6, 1.7e6, 1.8e6],
    })


# ───────────── compare-one ─────────────

def test_compare_one_requires_token(client):
    assert client.get("/api/v2/read/compare-one?code=600519").status_code == 401


def test_compare_one_ok_envelope(client, token, monkeypatch):
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: _fake_basic())
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: _fake_spot())
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": _fake_kline())
    resp = client.get("/api/v2/read/compare-one?code=600519&period=daily",
                      headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    # 顶层契约字段
    for k in ("code", "name", "industry", "period", "date", "note"):
        assert k in d, f"data 缺字段 {k}: {d}"
    # 31 个对比字段齐全
    for f in rr._W4C_COMPARE_FIELDS:
        assert f in d, f"compare-one 缺对比字段 {f}"
    assert len([k for k in d if k in rr._W4C_COMPARE_FIELDS]) == 31
    # 真值（取自 _fake_kline 3 根：date 11-07，close 1.1/2.2/3.3，volume 100/200/300）
    assert d["code"] == "600519" and d["name"] == "贵州茅台" and d["industry"] == "白酒"
    assert d["period"] == "daily"
    assert d["date"] == "2026-11-07"  # K 线末根权威日，非 now()
    assert d["current_price"] == 1688.0  # basic.price
    # close=[1.1,2.1,3.1] -> 前收=2.1, 涨跌幅=(3.1-2.1)/2.1*100
    assert d["prev_close"] == 2.1 and d["change_pct"] == round(1.0 / 2.1 * 100, 2)
    assert d["support"] == 0.5 and d["resistance"] == 3.5
    assert d["lo52"] == 0.5 and d["hi52"] == 3.5
    assert d["ma5v"] == 200.0 and d["ma10v"] == 200.0 and d["ma20v"] == 200.0
    assert d["vol_now"] == 300.0 and d["vol_avg"] == 200.0 and d["vol_chg"] == 50.0
    # 无干净来源的字段必须 null（诚实缺失，禁止补 0）
    for f in ("entry_price", "target_price", "stop_price", "atr14", "trapped",
              "q_open", "q_high", "q_low", "q_prev", "tech_score", "news_score",
              "macro_score", "vol_score", "sector_score", "composite", "pos_pct",
              "neg_pct", "pos52"):
        assert d[f] is None, f"{f} 应诚实为 null，实测 {d[f]}"
    assert d["note"] == rr._W4C_NOTE


def test_compare_one_invalid_and_missing_code(client, token):
    for qs in ("?code=abc", "?code=60051", "?code=6005199", ""):
        resp = client.get(f"/api/v2/read/compare-one{qs}", headers=_auth(token))
        assert resp.status_code == 400, f"{qs}: {resp.status_code}"
        obj = resp.get_json()
        assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


def test_compare_one_invalid_period(client, token):
    resp = client.get("/api/v2/read/compare-one?code=600519&period=hourly",
                      headers=_auth(token))
    assert resp.status_code == 400, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


def test_compare_one_all_sources_fail_null_no_zero(client, token, monkeypatch):
    """全源失败 -> status 仍 ok，31 字段全 null、date null（绝不补 0 / now()）。"""
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: None)
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: None)
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": None)
    resp = client.get("/api/v2/read/compare-one?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for f in rr._W4C_COMPARE_FIELDS:
        assert d[f] is None, f"缺失源时 {f} 必须为 null，实测 {d[f]}"
    assert d["date"] is None, "全源失败 -> date 必须 null，绝不用 now()"
    # 强断言：响应体里没有任何 0 充当编造值（current_price/prev_close 等）
    assert d["name"] is None and d["industry"] is None


def test_compare_one_source_exception_honest_degradation(client, token, monkeypatch):
    """某源抛异常 -> 对应字段 null、其余字段仍真值（fetch_many._safe 吞异常，绝不 500）。"""
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: _fake_basic())
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: _fake_spot())
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": _fake_kline())

    def boom(code):
        raise RuntimeError("kline timeout")

    monkeypatch.setattr(rr, "_w4b_kline", boom)
    resp = client.get("/api/v2/read/compare-one?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    # kline 源失败 -> 全部 kline 派生字段 null
    for f in ("prev_close", "change_pct", "support", "resistance", "lo52", "hi52",
              "ma5v", "ma10v", "ma20v", "vol_now", "vol_avg", "vol_chg"):
        assert d[f] is None, f"kline 失败时 {f} 必须 null，实测 {d[f]}"
    assert d["date"] == "2026-11-07"  # kline 失败、spot 仍在 -> spot_date 兜底（权威，非 now()）
    # basic/spot 仍有真值（逐字段独立降级）
    assert d["current_price"] == 1688.0


def test_compare_one_parallel_timeout_degrades(client, token, monkeypatch):
    """整批超时/未完成（res 全 None）-> 字段全 null、date null、status ok（不拿 0 / now()）。"""
    def fake_fetch_many(tasks, max_workers=None, timeout=None):
        return {"basic": None, "spot": None, "kline": None}

    monkeypatch.setattr("modules.fetch_parallel.fetch_many", fake_fetch_many)
    resp = client.get("/api/v2/read/compare-one?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert all(d[f] is None for f in rr._W4C_COMPARE_FIELDS), d
    assert d["date"] is None, "整批超时 -> date 必须 null，绝不 now()"


# ───────────── research-deep ─────────────

def test_research_deep_requires_token(client):
    assert client.get("/api/v2/read/research-deep?code=600519").status_code == 401


def test_research_deep_ok_envelope(client, token, monkeypatch):
    kl = _fake_kline_long()
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: _fake_basic())
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: _fake_spot())
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": kl)
    monkeypatch.setattr(rr, "_w4b_financial", lambda code, rt: None)
    resp = client.get("/api/v2/read/research-deep?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("code", "name", "industry", "date", "price", "pe_ttm", "pb",
              "market_cap", "ma5", "ma10", "ma20", "ma60", "amplitude",
              "turnover", "deep_analysis_available", "note"):
        assert k in d, f"data 缺字段 {k}: {d}"
    assert d["code"] == "600519" and d["name"] == "贵州茅台"
    assert d["price"] == 1688.0 and d["pe_ttm"] == 28.1 and d["market_cap"] == 21000.0
    # pb 无源 -> null；turnover 无源 -> null（诚实不编造）
    assert d["pb"] is None, "pb 必须 null（get_fundamentals 不返回）"
    assert d["turnover"] is None, "turnover 必须 null（需流通股本，无源）"
    # 技术面真值（_fake_kline_long：close=1..70）
    assert d["ma5"] == 68.0 and d["ma10"] == 65.5 and d["ma20"] == 60.5 and d["ma60"] == 40.5
    # amplitude：末根 high=70.5, low=69.5, prev_close=69.0 -> (1.0)/69*100
    assert d["amplitude"] == round(1.0 / 69.0 * 100, 2)
    assert d["date"] == str(kl["date"].iloc[-1])[:10]  # K 线末根权威日，非 now()
    # 重要豁免：异步深度分析不接入
    assert d["deep_analysis_available"] is False
    assert "deep_analysis_available=false" in d["note"]


def test_research_deep_invalid_code(client, token):
    for qs in ("?code=abc", "?code=60051", ""):
        resp = client.get(f"/api/v2/read/research-deep{qs}", headers=_auth(token))
        assert resp.status_code == 400, f"{qs}: {resp.status_code}"
        obj = resp.get_json()
        assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


def test_research_deep_all_sources_fail_null(client, token, monkeypatch):
    """全源失败 -> status 仍 ok；price 等 null、技术面 null、date null；deep 仍 False。"""
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: None)
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: None)
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": None)
    monkeypatch.setattr(rr, "_w4b_financial", lambda code, rt: None)
    resp = client.get("/api/v2/read/research-deep?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("price", "pe_ttm", "market_cap", "ma5", "ma10", "ma20", "ma60",
              "amplitude"):
        assert d[k] is None, f"缺失源时 {k} 必须 null，实测 {d[k]}"
    assert d["pb"] is None and d["turnover"] is None
    assert d["date"] is None, "全源失败 -> date 必须 null，绝不 now()"
    assert d["deep_analysis_available"] is False


# ───────────── stock-intraday ─────────────

def test_stock_intraday_requires_token(client):
    assert client.get("/api/v2/read/stock-intraday?code=600519").status_code == 401


def test_stock_intraday_ok_envelope(client, token, monkeypatch):
    monkeypatch.setattr(rr, "_w4c_intraday",
                        lambda code: (_fake_intraday_df(), 1687.0, "2026-11-07"))
    resp = client.get("/api/v2/read/stock-intraday?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("code", "date", "rows", "note"):
        assert k in d, f"data 缺字段 {k}: {d}"
    assert d["code"] == "600519"
    assert d["date"] == "2026-11-07"  # 分时 trade_date 权威日，非 now()
    assert isinstance(d["rows"], list) and len(d["rows"]) == 3
    # 列名原样
    assert set(d["rows"][0].keys()) == {
        "time", "open", "high", "low", "close", "volume", "amount"}


def test_stock_intraday_invalid_code(client, token):
    for qs in ("?code=abc", "?code=60051", ""):
        resp = client.get(f"/api/v2/read/stock-intraday{qs}", headers=_auth(token))
        assert resp.status_code == 400, f"{qs}: {resp.status_code}"
        obj = resp.get_json()
        assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


def test_stock_intraday_no_data_honest(client, token, monkeypatch):
    """底层 fetcher 返回 (None,None,None)（无数据）-> rows=[], date=null, status 仍 ok。

    注意：底层 fetcher 已落地（get_stock_intraday_sina），故此处走「诚实空响应」而非
    not_found（not_found 分支仅当底层不存在时触发，本环境下不成立）。
    """
    monkeypatch.setattr(rr, "_w4c_intraday", lambda code: (None, None, None))
    resp = client.get("/api/v2/read/stock-intraday?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert d["rows"] == [] and d["date"] is None, d
    assert d["code"] == "600519"


def test_stock_intraday_source_exception_honest(client, token, monkeypatch):
    """取数源抛异常（被 fetch_many._safe 吞成 None）-> rows=[], date=null, status ok。"""
    def boom(code):
        raise RuntimeError("sina intraday timeout")

    monkeypatch.setattr(rr, "_w4c_intraday", boom)
    resp = client.get("/api/v2/read/stock-intraday?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert d["rows"] == [] and d["date"] is None, d
