# -*- coding: utf-8 -*-
"""
backend/tests/test_stock_profile_score.py
—— v2 个股研究页两个新只读端点的守卫测试。

严格镜像 test_read_w4c.py 的 client/fixture 范式：monkeypatch 取数源，零网络。
覆盖：
  1. 两端点未鉴权 -> 401；非法 / 缺失 code -> 400 invalid_param（校验先于取数）；
  2. stock-profile data 字段全集逐字一致（一个不多一个不少），真值正确；
  3. core_business 同花顺失败 -> None（底层异常 / '' 均不冒充），其余字段仍返回、HTTP 200；
  4. name 本地股票池尾6位归一；date 取 fundamentals 数据日，取不到 null，绝不为 now()；
  5. technical-score data 字段全集逐字一致；technical/periods 真值是真计算而非占位；
  6. technical 异常 -> technical=None 且 note 注明、不 500；periods 异常 -> None 且 note 注明；
  7. mutation 反证：把 core_business 失败分支改成返回 '' 冒充时，守卫必须变红。
"""
from __future__ import annotations

import os
import sys
from datetime import date as _date, datetime as _dt, timedelta as _td

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


# ───────────── fixtures（与 test_read_w4c.py 同款，隔离 DB/token）─────────────

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
        u = User(username="psuser", role="user")
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
        u = User.query.filter_by(username="psuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ───────────── 契约字段全集（逐字，不多不少）─────────────

_SP_FIELDS = {
    "code", "name", "industry", "board", "core_business",
    "price", "market_cap", "date", "note",
}
_TS_FIELDS = {"code", "technical", "periods", "date", "note"}
_TECH_FIELDS = {"trend", "momentum", "volume", "patterns", "overall"}
_PERIOD_FIELDS = {"short", "mid", "long", "composite"}


# ───────────── 假取数源（零网络）─────────────

def _fake_fundamentals(with_date=True):
    d = {"industry": "白酒", "price": 1688.0, "market_cap": 21000.0, "pe_ttm": 28.1}
    if with_date:
        d["date"] = "2026-11-07"
    return d


def _fake_pool():
    return ({"code": "600519", "name": "贵州茅台"},)


def _fake_kline_full(n=70):
    """>=60 根 OHLCV+均线+收益率，保证 technical / periods 均算出真值。"""
    import pandas as pd
    base = _date(2026, 11, 5)
    dates = [(base + _td(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    closes = [100.0 + i * 1.5 for i in range(n)]
    ma5 = [sum(closes[max(0, i - 4):i + 1]) / len(closes[max(0, i - 4):i + 1])
           for i in range(n)]
    ma20 = [sum(closes[max(0, i - 19):i + 1]) / len(closes[max(0, i - 19):i + 1])
            for i in range(n)]
    return pd.DataFrame({
        "date": dates,
        "open": [c - 0.5 for c in closes],
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
        "close": closes,
        "volume": [1000.0 + i * 20.0 for i in range(n)],
        "ma5": ma5,
        "ma20": ma20,
        "return_1d": [0.5] * n,
        "return_5d": [3.0] * n,
        "return_20d": [8.0] * n,
        "change_pct": [0.5] * n,
        "ticker": ["600519"] * n,
    })


def _patch_profile_sources(monkeypatch, fund=None, core="茅台酒及系列酒的生产与销售"):
    monkeypatch.setattr(rr, "_sp_name_from_pool", lambda code: "贵州茅台")
    monkeypatch.setattr(
        rr, "_sp_fundamentals",
        lambda code: (_fake_fundamentals() if fund is None else fund),
    )
    monkeypatch.setattr(rr, "_sp_board", lambda code: "沪市主板")
    monkeypatch.setattr(rr, "_sp_core_business", lambda code: core)


# ───────────── 鉴权 / 参数校验 ─────────────

def test_stock_profile_requires_token(client):
    assert client.get("/api/v2/read/stock-profile?code=600519").status_code == 401


def test_technical_score_requires_token(client):
    assert client.get("/api/v2/read/technical-score?code=600519").status_code == 401


@pytest.mark.parametrize("qs", ["?code=abc", "?code=60051", "?code=6005199", ""])
def test_stock_profile_invalid_code(client, token, qs):
    resp = client.get(f"/api/v2/read/stock-profile{qs}", headers=_auth(token))
    assert resp.status_code == 400, f"{qs}: {resp.status_code}"
    obj = resp.get_json()
    assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


@pytest.mark.parametrize("qs", ["?code=abc", "?code=60051", "?code=6005199", ""])
def test_technical_score_invalid_code(client, token, qs):
    resp = client.get(f"/api/v2/read/technical-score{qs}", headers=_auth(token))
    assert resp.status_code == 400, f"{qs}: {resp.status_code}"
    obj = resp.get_json()
    assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


# ───────────── stock-profile ─────────────

def test_stock_profile_ok_envelope_and_exact_fields(client, token, monkeypatch):
    _patch_profile_sources(monkeypatch)
    resp = client.get("/api/v2/read/stock-profile?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert set(d) == _SP_FIELDS, f"data 字段全集不符（多/少字段）: {sorted(d)}"
    assert d["code"] == "600519"
    assert d["name"] == "贵州茅台"
    assert d["industry"] == "白酒"
    assert d["board"] == "沪市主板"
    assert d["core_business"] == "茅台酒及系列酒的生产与销售"
    assert d["price"] == 1688.0 and d["market_cap"] == 21000.0
    assert d["date"] == "2026-11-07"
    assert d["note"] == rr._SP_NOTE
    assert "名称来自本地股票池" in d["note"] and "缺失为 null 不补值" in d["note"]


def test_stock_profile_core_business_failure_is_none_others_intact(client, token, monkeypatch):
    """同花顺底层 get_core_business 抛异常 -> core_business=None，其余字段仍真值、200。"""
    # 注意：此处不 patch rr._sp_core_business，必须让真实函数走到异常分支（mutation 反证有效）
    monkeypatch.setattr(rr, "_sp_name_from_pool", lambda code: "贵州茅台")
    monkeypatch.setattr(rr, "_sp_fundamentals", lambda code: _fake_fundamentals())
    monkeypatch.setattr(rr, "_sp_board", lambda code: "沪市主板")

    class _BoomFetcher:
        def get_core_business(self, code):
            raise RuntimeError("同花顺主营构成接口不可用")

    # 让真实的 _sp_core_business 走到异常分支（不 monkeypatch 它本身，保证 mutation 反证有效）
    monkeypatch.setattr("backend.api.market_routes.get_fetcher", lambda: _BoomFetcher())
    resp = client.get("/api/v2/read/stock-profile?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    obj = resp.get_json()
    assert obj["status"] == "ok", obj
    d = obj["data"]
    assert set(d) == _SP_FIELDS, f"data 字段全集不符: {sorted(d)}"
    assert d["core_business"] is None, f"同花顺失败必须 None，实测 {d['core_business']!r}"
    # 逐字段独立降级：其余字段仍是真值
    assert d["name"] == "贵州茅台" and d["industry"] == "白酒" and d["board"] == "沪市主板"
    assert d["price"] == 1688.0 and d["market_cap"] == 21000.0 and d["date"] == "2026-11-07"


def test_stock_profile_core_business_empty_string_is_none(client, token, monkeypatch):
    """底层取不到返回 '' -> 端点必须规整为 None，绝不把空串冒充简介。"""
    _patch_profile_sources(monkeypatch, core="")
    resp = client.get("/api/v2/read/stock-profile?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["core_business"] is None, f"'' 必须规整为 None，实测 {d['core_business']!r}"


def test_stock_profile_name_tail6_normalization(client, token, monkeypatch):
    """本地池 code 尾6位归一：sh600519 / sz000001 均能按 600519 / 000001 水合。"""
    monkeypatch.setattr(
        "backend.services.stock_pool_fallback.load_stock_pool",
        lambda: (
            {"code": "sh600519", "name": "贵州茅台"},
            {"code": "sz000001", "name": "平安银行"},
        ),
    )
    monkeypatch.setattr(rr, "_sp_fundamentals", lambda code: _fake_fundamentals())
    monkeypatch.setattr(rr, "_sp_board", lambda code: "沪市主板")
    monkeypatch.setattr(rr, "_sp_core_business", lambda code: None)
    resp = client.get("/api/v2/read/stock-profile?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["name"] == "贵州茅台", f"尾6位归一失败: {d['name']!r}"

    resp2 = client.get("/api/v2/read/stock-profile?code=000001", headers=_auth(token))
    assert resp2.status_code == 200
    assert resp2.get_json()["data"]["name"] == "平安银行"


def test_stock_profile_date_is_fund_date_or_none_never_now(client, token, monkeypatch):
    today = _dt.now().strftime("%Y-%m-%d")
    _patch_profile_sources(monkeypatch, fund=_fake_fundamentals(with_date=False))
    resp = client.get("/api/v2/read/stock-profile?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["date"] is None, f"fundamentals 无数据日时必须 null，实测 {d['date']!r}"
    assert d["date"] != today, "绝不能用 now() 兜底"

    _patch_profile_sources(monkeypatch, fund=_fake_fundamentals(with_date=True))
    resp2 = client.get("/api/v2/read/stock-profile?code=600519", headers=_auth(token))
    d2 = resp2.get_json()["data"]
    assert d2["date"] == "2026-11-07" and d2["date"] != today


def test_stock_profile_all_sources_fail_honest_null(client, token, monkeypatch):
    _patch_profile_sources(monkeypatch, fund={}, core=None)
    monkeypatch.setattr(rr, "_sp_name_from_pool", lambda code: None)
    monkeypatch.setattr(rr, "_sp_board", lambda code: None)
    resp = client.get("/api/v2/read/stock-profile?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert set(d) == _SP_FIELDS
    for k in ("name", "industry", "board", "core_business", "price", "market_cap", "date"):
        assert d[k] is None, f"全源失败时 {k} 必须 null，实测 {d[k]!r}"
    assert d["note"] == rr._SP_NOTE


# ───────────── technical-score ─────────────

def test_technical_score_ok_envelope_and_exact_fields(client, token, monkeypatch):
    kl = _fake_kline_full()
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": kl)
    resp = client.get("/api/v2/read/technical-score?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert set(d) == _TS_FIELDS, f"data 字段全集不符（多/少字段）: {sorted(d)}"

    tech = d["technical"]
    assert isinstance(tech, dict) and set(tech) == _TECH_FIELDS, tech
    for k in ("trend", "momentum", "volume", "overall"):
        v = tech[k]
        assert isinstance(v, (int, float)) and not isinstance(v, bool), f"{k} 应为数值: {v!r}"
        assert v == v and 0 <= v <= 100, f"{k} 应在 0-100: {v!r}"
    assert isinstance(tech["patterns"], list)
    assert all(isinstance(p, str) for p in tech["patterns"]), tech["patterns"]

    periods = d["periods"]
    assert isinstance(periods, dict) and set(periods) == _PERIOD_FIELDS, periods
    # 契约里 periods 没有 trend —— 防多字段
    assert "trend" not in periods
    for k in ("short", "mid", "long", "composite"):
        v = periods[k]
        assert isinstance(v, (int, float)) and not isinstance(v, bool), f"{k} 应为数值: {v!r}"
        assert v == v and 0 <= v <= 100, f"{k} 应在 0-100: {v!r}"

    assert d["date"] == str(kl["date"].iloc[-1])[:10]
    assert d["date"] != _dt.now().strftime("%Y-%m-%d"), "date 必须是 K 线末根真实日，非 now()"
    assert isinstance(d["note"], str) and "不实例化" in d["note"]


def test_technical_score_analysis_exception_degrades_to_null(client, token, monkeypatch):
    """full_analysis 抛异常 -> technical=None 且 note 注明、periods 仍计算、不 500。"""
    kl = _fake_kline_full()
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": kl)

    def boom(df):
        raise RuntimeError("技术分析模块故障")

    monkeypatch.setattr("modules.technical.full_analysis", boom)
    resp = client.get("/api/v2/read/technical-score?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    obj = resp.get_json()
    assert obj["status"] == "ok", obj
    d = obj["data"]
    assert set(d) == _TS_FIELDS
    assert d["technical"] is None, f"技术面异常必须 technical=null，实测 {d['technical']!r}"
    assert "technical=null" in d["note"] and "不补值" in d["note"]
    # 逐块独立降级：periods 不受影响
    assert isinstance(d["periods"], dict) and set(d["periods"]) == _PERIOD_FIELDS
    assert d["date"] == str(kl["date"].iloc[-1])[:10]


def test_technical_score_periods_exception_honest_note(client, token, monkeypatch):
    """多周期画像异常 -> periods=None 且 note 诚实注明，不 500、不补 50。"""
    kl = _fake_kline_full()
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": kl)

    def boom(df):
        raise RuntimeError("SignalEngine 画像计算故障")

    monkeypatch.setattr(rr, "_sp_periods_block", boom)
    resp = client.get("/api/v2/read/technical-score?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert set(d) == _TS_FIELDS
    assert d["periods"] is None, f"画像异常必须 periods=null，实测 {d['periods']!r}"
    assert "periods=null" in d["note"] and "不补值" in d["note"]
    assert isinstance(d["technical"], dict), "技术面块不应被画像异常拖垮"


def test_technical_score_no_kline_honest_null(client, token, monkeypatch):
    """无 K 线 -> technical=None、periods=None、date=None，全部诚实 null。"""
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": None)
    resp = client.get("/api/v2/read/technical-score?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]
    assert set(d) == _TS_FIELDS
    assert d["technical"] is None and d["periods"] is None and d["date"] is None
    assert "technical=null" in d["note"] and "periods=null" in d["note"]


def test_technical_score_all_analysis_blocks_error_no_fabrication(client, token, monkeypatch):
    """full_analysis 子块全 error -> 三维为 null、patterns=[]、overall=null，绝不补 50/编造。"""
    kl = _fake_kline_full()
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": kl)
    monkeypatch.setattr(
        "modules.technical.full_analysis",
        lambda df: {
            "trend": {"error": "trend failed"},
            "momentum": {"error": "momentum failed"},
            "volume": {"error": "volume failed"},
            "patterns": {"error": "patterns failed"},
        },
    )
    resp = client.get("/api/v2/read/technical-score?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    tech = resp.get_json()["data"]["technical"]
    assert set(tech) == _TECH_FIELDS
    assert tech["trend"] is None and tech["momentum"] is None and tech["volume"] is None
    assert tech["patterns"] == []
    assert tech["overall"] is None, "三维全失败时 overall 必须 null，绝不补 50"
