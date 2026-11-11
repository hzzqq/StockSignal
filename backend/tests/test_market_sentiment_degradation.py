"""
backend/tests/test_market_sentiment_degradation.py
-------------------------------------------------
锁死 2026-11-12 发现的真实缺陷：

  /api/v2/read/market-sentiment 在底层 modules.market_drivers 返回含「非维度注入键」
  （进程缓存过期时写入的 _swr_stale/_swr_age_s/_swr_note，值分别为 bool/int/str）
  的 meta 时，_flatten_unavailable 对其调 .get("unavailable") → AttributeError →
  端点 500，违背「优雅降级」契约（其余联网端点均正确降级为 200 ok）。

  生产中进程缓存过期是高频事件 —— 只要缓存过期，/market-sentiment（v2 native 页）
  必定 500。修复：_flatten_unavailable 跳过非 dict 的 info，unavailable 取值非列表
  时以 [] 兜底。

  本测试双重锁定：
    1. 直接单测 _flatten_unavailable 面对 _swr_* 注入键 / 非 dict / None 的健壮性；
    2. 集成测试：monkeypatch get_market_drivers 返回带 _swr_* 注入键的 meta
       （精确复现缓存过期触发条件），断言端点 200（非 500）且信封合法、unavailable 正确拍平。

设计约束：用独立临时 SQLite + _TestConfig 隔离，绝不污染 backend/data/app.db；
不依赖联网（fake 直接注入 meta），确定性可重复。
"""
from __future__ import annotations

import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.models import User  # noqa: E402
from backend.api import read_routes  # noqa: E402


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def app():
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 't.db')}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        for uname, role in (("admin", "admin"), ("demo", "user")):
            if User.query.filter_by(username=uname).first() is None:
                u = User(username=uname, role=role)
                u.set_password("Pass@123")
                db.session.add(u)
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _token(client, username="demo", password="Pass@123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


# ---------------------------------------------------------------- 单元层：_flatten_unavailable 健壮性
def test_flatten_skips_swdr_injected_keys():
    """meta 含 _swr_* 注入键（bool/int/str）时不得崩溃，且这些键不参与拍平。"""
    meta = {
        "情绪": {"available": ["m1"], "unavailable": []},
        "资金": {"available": [], "unavailable": [("north_flow", "抓取失败")]},
        "_swr_stale": True,
        "_swr_age_s": 123,
        "_swr_note": "进程缓存已过期 123s，本次先展示旧值，后台重试。",
    }
    out = read_routes._flatten_unavailable(meta)
    assert isinstance(out, list)
    # 只有维度 dict 参与了拍平；_swr_* 注入键被安全跳过
    assert out == [{"dim": "资金", "key": "north_flow", "reason": "抓取失败"}]


def test_flatten_tolerates_non_dict_and_none():
    assert read_routes._flatten_unavailable(None) == []
    assert read_routes._flatten_unavailable("not a dict") == []
    # unavailable 取值不是列表时兜底为空，不二次崩溃
    assert read_routes._flatten_unavailable({"x": {"available": [], "unavailable": "oops"}}) == []
    # 空 meta 返回空
    assert read_routes._flatten_unavailable({}) == []


# ---------------------------------------------------------------- 集成层：端点不得 500（缓存过期触发条件）
def _fake_gmd_with_swdr_injection(days=180, empty=False):
    """精确复现 modules.market_drivers 在进程缓存过期时返回的 meta 形状。"""
    if empty:
        df = pd.DataFrame(columns=["date"])
    else:
        df = pd.DataFrame({"date": ["2026-11-10", "2026-11-11"], "adr_10": [1.0, 1.1]})
    meta = {
        "情绪": {"available": ["adr_10"], "unavailable": []},
        "资金": {"available": [], "unavailable": [("north_flow", "抓取失败")]},
        "估值": {"available": [], "unavailable": [("pe_median", "抓取失败")]},
        # —— 真实注入键（进程缓存过期时由 market_drivers 写入）——
        "_swr_stale": True,
        "_swr_age_s": 123,
        "_swr_note": "进程缓存已过期 123s，本次先展示旧值，后台重试。",
    }
    return df, meta


def test_market_sentiment_ok_when_cache_stale(client, monkeypatch):
    """主路径（df 非空）：缓存过期注入 _swr_* 键时端点须 200 ok，不 500。"""
    monkeypatch.setattr(
        "modules.market_drivers.get_market_drivers",
        lambda days=180: _fake_gmd_with_swdr_injection(days=days, empty=False),
    )
    tok = _token(client)
    r = client.get("/api/v2/read/market-sentiment", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok", j
    assert isinstance(j["data"], dict)
    assert isinstance(j["data"]["unavailable"], list)
    # 维度 unavailable 正确拍平，_swr_* 键被跳过
    keys = {u["key"] for u in j["data"]["unavailable"]}
    assert "north_flow" in keys and "pe_median" in keys


def test_market_sentiment_ok_empty_branch_when_cache_stale(client, monkeypatch):
    """df 为空分支（available=False）：同样须 200 ok，不 500。"""
    monkeypatch.setattr(
        "modules.market_drivers.get_market_drivers",
        lambda days=180: _fake_gmd_with_swdr_injection(days=days, empty=True),
    )
    tok = _token(client)
    r = client.get("/api/v2/read/market-sentiment", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok"
    assert j["data"]["available"] is False
    assert isinstance(j["data"]["unavailable"], list)
