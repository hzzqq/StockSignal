# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_policy_transmission_body_match.py — 政策传导「正文补充命中」回归守卫。

零网络：monkeypatch policy_store.read_recent / sector_map.list_sectors /
sector_map.resolve_sector；event_graph 的 build_transmission / display_rows 是纯函数。

覆盖：
- 标题无行业词、正文含行业词 → 行业进入 sectors，matched_by 以 body_ 开头；
- 标题优先，同行业不被正文重复添加；
- body_text 缺失/非字符串 → 不编造行业命中；
- failed 行业即使正文命中也进 members_unavailable、不展开标的；
- 正文仅截前 3000 字；derived_note 含正文命中诚实说明。
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
import modules.event_graph as evg  # noqa: E402


PID = "c" * 32
URL = f"/api/v2/read/policy-transmission?policy_id={PID}"

# 标题无任何行业词（党建/行政/民生类真实标题风格）；正文含「半导体」「电池」「物流」
BODY = "本次政策推动半导体制造能力提升，完善电池产业链，促进商贸物流降本增效。"

# name 在正文 → body_name；name 不在正文但 keyword「电池」在正文 → body_keyword
SEMI = ("半导体", "半导体,芯片")
BATTERY = ("动力电池", "电池,锂电")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db_body_match') / 'policy_bm.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="policybodymatch", role="user")
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
        u = User.query.filter_by(username="policybodymatch").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _doc(**over):
    d = {
        "policy_id": PID,
        "title": "关于深入推进再生资源回收体系建设的若干意见",  # 无行业词
        "publish_date": "2026-11-10",
        "source_url": f"https://example.gov.cn/policy/{PID}",
        "source": "ndrc",
        "body_text": BODY,
        "body_source": "html",
        "content_hash": "d" * 32,
        "crawled_at": "2026-11-12T10:00:00",
    }
    d.update(over)
    return d


def _sector(name, keywords, status="ok", codes="600111,600222", mc=2):
    return {
        "board_name": name,
        "board_code": "BK-" + name,
        "board_type": "industry",
        "keywords": keywords,
        "stock_codes": codes,
        "member_count": mc,
        "source": "rule_l1",
        "fetch_status": status,
        "updated_at": "2026-11-01 00:00:00",
    }


def _resolved(name, status="ok", codes="600111,600222", mc=2):
    return {
        "name": name,
        "keywords": "",
        "stock_codes": codes,
        "member_count": mc,
        "source": "rule_l1",
        "fetch_status": status,
        "description": None,
    }


def _wire(monkeypatch, doc, sectors):
    """注入受控政策与行业表，resolve_sector 按 board_name 返回对应结果。"""
    monkeypatch.setattr(rr.policy_store, "read_recent", lambda limit=200: [doc])
    monkeypatch.setattr(rr.sector_map, "list_sectors", lambda status=None: list(sectors))
    by_name = {s["board_name"]: s for s in sectors}

    def _resolve(name):
        s = by_name.get(name)
        if not s:
            return None
        return _resolved(name, s["fetch_status"], s["stock_codes"], s["member_count"])

    monkeypatch.setattr(rr.sector_map, "resolve_sector", _resolve)


def _sector_hit(d, name):
    return next((x for x in d["sectors"] if x["name"] == name), None)


# ───────────── 1. 正文补充命中 ─────────────

def test_body_match_enters_sectors_with_body_prefix(client, token, monkeypatch):
    _wire(monkeypatch, _doc(), [
        _sector(*SEMI),
        _sector(*BATTERY, status="failed", codes="", mc=0),
    ])

    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]

    semi_hit = _sector_hit(d, "半导体")
    bat_hit = _sector_hit(d, "动力电池")
    assert semi_hit is not None and bat_hit is not None
    assert semi_hit["matched_by"] == "body_name"
    assert bat_hit["matched_by"] == "body_keyword"
    # 标题无行业词，所有命中均来自正文，且 derived 标注保留
    assert d["sectors"]
    assert all(s["matched_by"].startswith("body_") for s in d["sectors"])
    assert all(s["derived"] is True for s in d["sectors"])


# ───────────── 2. 标题优先 / 不重复 ─────────────

def test_title_priority_no_body_duplicate(client, token, monkeypatch):
    doc = _doc(
        title="关于促进半导体产业高质量发展的若干政策",  # 标题含「半导体」
        body_text=BODY,                                   # 正文也含「半导体」
    )
    _wire(monkeypatch, doc, [
        _sector(*SEMI),
        _sector(*BATTERY, status="failed", codes="", mc=0),
    ])

    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]

    # 标题命中的「半导体」不被正文改写、也不重复添加
    semi_hits = [s for s in d["sectors"] if s["name"] == "半导体"]
    assert len(semi_hits) == 1
    assert semi_hits[0]["matched_by"] == "name"
    # 仅正文命中的「动力电池」仍走正文补充
    bat_hit = _sector_hit(d, "动力电池")
    assert bat_hit is not None and bat_hit["matched_by"] == "body_keyword"


# ───────────── 3. 无正文不编造 ─────────────

def test_body_missing_no_fabrication(client, token, monkeypatch):
    for doc in (
        _doc(body_text=None),
        _doc(body_text=""),
        _doc(body_text=12345),  # 非字符串
    ):
        _wire(monkeypatch, doc, [
            _sector(*SEMI),
            _sector(*BATTERY, status="failed", codes="", mc=0),
        ])

        resp = client.get(URL, headers=_auth(token))
        assert resp.status_code == 200
        d = resp.get_json()["data"]
        assert d["sectors"] == [], "无正文（或正文非字符串）时不得编造行业命中"
        assert d["entries"] == []
        assert d["members_unavailable"] == []


# ───────────── 4. failed 行业正文命中也不展开 ─────────────

def test_failed_sector_body_match_not_expanded(client, token, monkeypatch):
    _wire(monkeypatch, _doc(), [_sector(*BATTERY, status="failed", codes="", mc=0)])

    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]

    assert d["entries"] == [], "failed 行业不得展开成分股、不得编造标的"
    mu = [m for m in d["members_unavailable"] if m["name"] == "动力电池"]
    assert len(mu) == 1
    assert mu[0]["matched_by"].startswith("body_")
    assert mu[0]["fetch_status"] == "failed"
    assert mu[0]["derived"] is True
    assert mu[0]["stock_codes_count"] == 0


# ───────────── 5. 正文仅截前 3000 字 ─────────────

def test_body_match_only_first_3000_chars(client, token, monkeypatch):
    # 「电池」仅出现在 3000 字之后 → 不应命中（截断是诚实边界）
    doc = _doc(body_text="x" * 3100 + "电池")
    _wire(monkeypatch, doc, [_sector(*BATTERY)])

    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["sectors"] == []


# ───────────── 6. derived_note 诚实说明 ─────────────

def test_derived_note_documents_body_source(client, token, monkeypatch):
    _wire(monkeypatch, _doc(), [_sector(*SEMI)])

    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    note = resp.get_json()["data"]["derived_note"]
    assert "正文前 3000 字" in note
    assert "body_name" in note and "body_keyword" in note
    assert "非 LLM 判定" in note
    assert "非收益预测" in note


# ───────────── 7. 正文命中行业 → 外部预匹配 → 真正产出标的 ─────────────

def test_body_match_feeds_prematched_concepts_and_produces_entries(client, token, monkeypatch):
    """修复「看得见命中行业但出不了标的」最后一环：正文命中且有真实成分股的行业
    被作为 pre_matched_concepts 传入 build_transmission，最终产出非空 entries。"""
    captured = {}
    real_build = evg.build_transmission

    def _spy(titles, concept_index, pre_matched_concepts=None):
        captured["titles"] = list(titles)
        captured["concept_index"] = dict(concept_index)
        captured["pre_matched_concepts"] = pre_matched_concepts
        return real_build(titles, concept_index, pre_matched_concepts=pre_matched_concepts)

    monkeypatch.setattr(evg, "build_transmission", _spy)
    _wire(monkeypatch, _doc(), [
        _sector(*SEMI),                                       # ok，有真实成分股
        _sector(*BATTERY, status="failed", codes="", mc=0),   # failed，不进 idx
    ])

    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()["data"]

    # 调用方确实把「已命中且有真实成分股的行业名」作为外部预匹配传入
    assert captured.get("pre_matched_concepts") == {"半导体"}
    assert list(captured["concept_index"].keys()) == ["半导体"]
    # 标题无任何行业词（标题路径未命中），但正文命中 → 仍产出真实标的
    assert "半导体" not in captured["titles"][0]
    assert "电池" not in captured["titles"][0]
    assert d["entries"], "正文命中行业有真实成分股却未产出标的"
    assert all(e["code"] in ("600111", "600222") for e in d["entries"])
    # 诚实红线：failed 行业仍不进 idx、仍列 members_unavailable
    mu = [m for m in d["members_unavailable"] if m["name"] == "动力电池"]
    assert len(mu) == 1 and mu[0]["fetch_status"] == "failed"
    assert mu[0]["matched_by"].startswith("body_")
