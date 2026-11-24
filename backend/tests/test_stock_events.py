# -*- coding: utf-8 -*-
"""backend/tests/test_stock_events.py — 个股事件追踪端点（v1 pages/23 → v2）回归守卫。

零网络：只 monkeypatch NewsFetcher.fetch_stock_events / SentimentAnalyzer.analyze_news，
情感五档的真值来自 modules/event_levels.py::level_from_score（单一真理源）。
覆盖：正常取数与字段逐字、抓取异常空态、code/limit 非法、五档边界、
source/url 按行位置合并保真与非 http 置 null。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402
from modules._news_io import NewsFetcher  # noqa: E402
from modules._news_nlp import SentimentAnalyzer  # noqa: E402
from modules.event_levels import level_from_score  # noqa: E402

PATH = "/api/v2/read/stock-events"
DATA_FIELDS = {"code", "name", "date", "available", "events", "distribution", "count", "note"}
EVENT_FIELDS = {"date", "title", "source", "url", "sentiment", "level", "score", "is_major"}
DIST_KEYS = {"正面", "负面", "中性"}


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'stock_events.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="stock_event_tester", role="user")
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
        return issue_token(User.query.filter_by(username="stock_event_tester").first())


@pytest.fixture(autouse=True)
def _isolate_sources(monkeypatch):
    """默认把抓取与名称水合换成确定性桩，杜绝任何测试触网。"""
    monkeypatch.setattr(rr, "_sp_name_from_pool", lambda code: "贵州茅台")
    monkeypatch.setattr(
        NewsFetcher, "fetch_stock_events",
        lambda self, **kw: pd.DataFrame(columns=["date", "title", "content", "source", "url"]),
    )


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _frame(rows):
    return pd.DataFrame(
        rows, columns=["date", "title", "content", "source", "url"]
    )


def _patch_fetch(monkeypatch, rows, calls=None):
    df = _frame(rows)

    def fake(self, **kwargs):
        if calls is not None:
            calls.append(kwargs)
        return df.copy()

    monkeypatch.setattr(NewsFetcher, "fetch_stock_events", fake)


# ── 1. 正常取数：字段逐字 + 真算情感 + 最新真实日期 ──────────────────────────────
def test_normal_events_contract_and_real_sentiment(client, token, monkeypatch):
    pos_title = "贵州茅台业绩大增、净利润翻倍、超预期、获得大单、技术突破"
    neg_title = "贵州茅台亏损、高管离职、财务造假、被处罚、订单取消"
    calls = []
    _patch_fetch(monkeypatch, [
        {"date": pd.Timestamp("2026-11-20"), "title": pos_title, "content": "",
         "source": "eastmoney_announcement", "url": "https://example.com/a/1"},
        {"date": pd.Timestamp("2026-11-18"), "title": neg_title, "content": "",
         "source": "财新", "url": "https://example.com/n/2"},
    ], calls)

    resp = client.get(PATH + "?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    env = resp.get_json()
    assert env["status"] == "ok" and env["code"] == "ok"
    data = env["data"]
    assert set(data) == DATA_FIELDS, f"data 字段集合不符: {set(data)}"
    assert data["code"] == "600519"
    assert data["name"] == "贵州茅台"
    assert data["date"] == "2026-11-20"      # 最新一条真实事件日，非 now()
    assert data["available"] is True
    assert data["count"] == 2
    assert len(data["events"]) == 2
    assert set(data["distribution"]) == DIST_KEYS
    assert sum(data["distribution"].values()) == 2
    assert "启发式" in data["note"] and "仅供参考" in data["note"] and "填充" in data["note"]

    # 传给真源的契约参数：code/name/keywords/limit 四件齐全，limit 缺省 50
    assert calls == [{
        "stock_code": "600519", "stock_name": "贵州茅台",
        "keywords": None, "limit": 50,
    }]

    for ev, title, source, url in (
        (data["events"][0], pos_title, "eastmoney_announcement", "https://example.com/a/1"),
        (data["events"][1], neg_title, "财新", "https://example.com/n/2"),
    ):
        assert set(ev) == EVENT_FIELDS, f"events[] 字段集合不符: {set(ev)}"
        assert ev["title"] == title
        assert ev["source"] == source
        assert ev["url"] == url
        expected = SentimentAnalyzer().analyze_news(title, "")  # 真算，非硬编码
        assert ev["sentiment"] == expected["sentiment"]
        assert ev["level"] == expected["level"]
        assert ev["score"] == expected["score"]
        assert ev["is_major"] == expected["is_major"]
    assert data["events"][0]["sentiment"] == "正面"
    assert data["events"][0]["level"] == "大利好"
    assert data["events"][1]["sentiment"] == "负面"
    assert data["events"][1]["level"] == "大利空"


# ── 2. 抓取异常：空态 200，绝不 500 / 编造事件 ──────────────────────────────────
def test_fetch_exception_degrades_to_honest_empty_state(client, token, monkeypatch):
    def boom(self, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(NewsFetcher, "fetch_stock_events", boom)
    resp = client.get(PATH + "?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["events"] == []
    assert data["available"] is False
    assert data["date"] is None
    assert data["count"] == 0
    assert data["distribution"] == {"正面": 0, "负面": 0, "中性": 0}
    assert data["note"]


# ── 3. code 非法 -> 400 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["abc", "12345", "", "1234567", "6005a9"])
def test_invalid_code_returns_400(client, token, bad):
    resp = client.get(PATH + "?code=" + bad, headers=_auth(token))
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["status"] == "error" and body["code"] == "invalid_param"


# ── 4. limit 白名单 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["5", "99", "x", "0", "-1", "3.5"])
def test_invalid_limit_returns_400(client, token, monkeypatch, bad):
    calls = []
    _patch_fetch(monkeypatch, [], calls)
    resp = client.get(PATH + "?code=600519&limit=" + bad, headers=_auth(token))
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_param"
    assert calls == []  # 参数校验先于取数，不得触达真源


@pytest.mark.parametrize("good", [10, 20, 30, 50])
def test_valid_limit_returns_200(client, token, monkeypatch, good):
    calls = []
    _patch_fetch(monkeypatch, [], calls)
    resp = client.get(PATH + f"?code=600519&limit={good}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert calls[0]["limit"] == good


# ── 5. 五档边界（真值以 level_from_score 为准）──────────────────────────────────
@pytest.mark.parametrize("score,level", [
    (0.4, "大利好"),
    (0.3, "小利好"),
    (0.15, "中性"),
    (-0.15, "中性"),
    (-0.3, "小利空"),
    (-0.4, "大利空"),
])
def test_level_from_score_boundaries(score, level):
    assert level_from_score(score) == level


def test_endpoint_five_levels_boundaries(client, token, monkeypatch):
    scores = [0.4, 0.3, 0.15, -0.15, -0.3, -0.4]
    rows = [
        {"date": pd.Timestamp(f"2026-11-{20 + i:02d}"),
         "title": f"SCORE={s}", "content": "",
         "source": f"源{i}", "url": f"https://example.com/{i}"}
        for i, s in enumerate(scores)
    ]
    _patch_fetch(monkeypatch, rows)

    def fake_analyze(self, title, content=""):
        s = float(str(title).split("=", 1)[1])
        return {
            "sentiment": "正面" if s > 0.15 else ("负面" if s < -0.15 else "中性"),
            "level": level_from_score(s), "score": s,
            "is_major": abs(s) >= 0.4,
            "pos_words": [], "neg_words": [], "intensity": 1.0,
        }

    monkeypatch.setattr(SentimentAnalyzer, "analyze_news", fake_analyze)
    resp = client.get(PATH + "?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert [e["level"] for e in data["events"]] == [
        "大利好", "小利好", "中性", "中性", "小利空", "大利空",
    ]
    assert [e["score"] for e in data["events"]] == scores
    assert [e["is_major"] for e in data["events"]] == [
        True, False, False, False, False, True,
    ]
    assert data["distribution"] == {"正面": 2, "负面": 2, "中性": 2}
    assert data["date"] == "2026-11-25"  # 乱序输入也取真实最大日期


# ── 6. source/url 按行位置合并保真 + 非 http 置 null ───────────────────────────
def test_source_url_merge_and_non_http_nulled(client, token, monkeypatch):
    _patch_fetch(monkeypatch, [
        {"date": "2026-11-19", "title": "标题一", "content": "",
         "source": "公告源A", "url": "https://example.com/a"},
        {"date": "2026-11-18", "title": "标题二", "content": "",
         "source": "新闻源B", "url": "/relative/path"},
        {"date": "2026-11-17", "title": "标题三", "content": "",
         "source": "来源C", "url": "javascript:alert(1)"},
        {"date": None, "title": "标题四", "content": "",
         "source": None, "url": None},
    ])

    def neutral(self, title, content=""):
        return {
            "sentiment": "中性", "level": "中性", "score": 0.0,
            "is_major": False, "pos_words": [], "neg_words": [], "intensity": 1.0,
        }

    monkeypatch.setattr(SentimentAnalyzer, "analyze_news", neutral)
    resp = client.get(PATH + "?code=600519", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    events = data["events"]
    assert len(events) == 4
    assert [(e["source"], e["url"]) for e in events] == [
        ("公告源A", "https://example.com/a"),
        ("新闻源B", None),
        ("来源C", None),
        (None, None),
    ]
    assert [e["date"] for e in events] == ["2026-11-19", "2026-11-18", "2026-11-17", None]
    assert data["date"] == "2026-11-19"
    assert data["distribution"] == {"正面": 0, "负面": 0, "中性": 4}
