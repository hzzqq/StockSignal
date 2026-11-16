"""自然语言选股执行端点验收测试（POST /api/v2/nl-screen/execute）。

测试夹具说明：
  * 全程**零联网**：monkeypatch 注入 _UNIVERSE_SOURCES 假源（合成候选池，非真实行情），
    并对 modules.risk_gate.scan_and_gate 注入假闸（真实闸会拉市场级网络数据）；
  * 真 Flask test_client + 独立临时 SQLite + 真 JWT；禁止 pytest.skip，禁止仅断言 200；
  * 诚实红线：候选池失败 / 全未理解 / 闸异常 三条业务降级路径均验证 available=false
    或如实标注，绝不出现伪造筛选结果。
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

import backend.api.nl_execute_routes as ner  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402

URL = "/api/v2/nl-screen/execute"

# ── 合成确定性候选池（10 只假股，非真实行情）──
FAKE_UNIVERSE = [
    {"code": "300001", "name": "假股甲", "pe": 25.0, "pb": 3.0, "mktcap": 80.0,
     "float_mktcap": 60.0, "rev_growth": 30.0, "profit_growth": 25.0, "roe": 12.0,
     "gross_margin": 40.0, "turnover": 5.0, "concepts": ["半导体", "芯片"]},
    {"code": "300002", "name": "假股乙", "pe": 40.0, "pb": 2.0, "mktcap": 50.0,
     "float_mktcap": 30.0, "rev_growth": 5.0, "profit_growth": 3.0, "roe": 6.0,
     "gross_margin": 20.0, "turnover": 1.0, "concepts": []},
    {"code": "688001", "name": "假股丙", "pe": 20.0, "pb": 4.0, "mktcap": 120.0,
     "float_mktcap": 90.0, "rev_growth": 25.0, "profit_growth": 18.0, "roe": 10.0,
     "gross_margin": 55.0, "turnover": 3.0, "concepts": ["芯片"]},
    {"code": "600001", "name": "假股丁", "pe": 15.0, "pb": 1.5, "mktcap": 300.0,
     "float_mktcap": 250.0, "rev_growth": 10.0, "profit_growth": 8.0, "roe": 9.0,
     "gross_margin": 30.0, "turnover": 2.0, "concepts": []},
    {"code": "600002", "name": "假股戊", "pe": 50.0, "pb": 5.0, "mktcap": 200.0,
     "float_mktcap": 150.0, "rev_growth": 40.0, "profit_growth": 35.0, "roe": 15.0,
     "gross_margin": 60.0, "turnover": 8.0, "concepts": ["人工智能"]},
    {"code": "000001", "name": "假股己", "pe": 8.0, "pb": 0.8, "mktcap": 900.0,
     "float_mktcap": 800.0, "rev_growth": 2.0, "profit_growth": 1.0, "roe": 11.0,
     "gross_margin": 25.0, "turnover": 0.5, "concepts": []},
    {"code": "000002", "name": "假股庚", "pe": 30.0, "pb": 2.2, "mktcap": 160.0,
     "float_mktcap": 120.0, "rev_growth": 21.0, "profit_growth": 15.0, "roe": 8.0,
     "gross_margin": 35.0, "turnover": 4.0, "concepts": []},
    {"code": "300003", "name": "假股辛", "pe": 10.0, "pb": 1.2, "mktcap": 70.0,
     "float_mktcap": 55.0, "rev_growth": 50.0, "profit_growth": 45.0, "roe": 18.0,
     "gross_margin": 65.0, "turnover": 9.0, "concepts": ["白酒"]},
    {"code": "688002", "name": "假股壬", "pe": 45.0, "pb": 6.0, "mktcap": 90.0,
     "float_mktcap": 70.0, "rev_growth": 12.0, "profit_growth": -5.0, "roe": 4.0,
     "gross_margin": 45.0, "turnover": 6.0, "concepts": []},
    {"code": "600003", "name": "假股癸", "pe": 12.0, "pb": 1.0, "mktcap": 110.0,
     "float_mktcap": 95.0, "rev_growth": 7.0, "profit_growth": 6.0, "roe": 7.0,
     "gross_margin": 28.0, "turnover": float("nan"), "chg_pct": float("inf"),
     "concepts": []},
]


def _pass_gate(candidates, top_k=1, **_kw):
    """假二道闸：不拦截、不触网。"""
    return list(candidates), {"kicked": []}


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file.as_posix()}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    # team-lead 会在 backend/app.py 统一注册本 blueprint；此处条件注册保证测试在当前
    # worktree（app.py 尚未改）也能跑，且未来 app.py 注册后不会重复注册。
    if "nl_execute" not in application.blueprints:
        application.register_blueprint(ner.bp)

    with application.app_context():
        db.create_all()
        if User.query.filter_by(username="demo").first() is None:
            u = User(username="demo", role="user")
            u.set_password("Pass@123")
            db.session.add(u)
            db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Pass@123"})
    assert r.status_code == 200, f"登录失败: {r.status_code} {r.text[:300]}"
    token = r.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _install_sources(monkeypatch, universe=FAKE_UNIVERSE, fail=False, per_source=None):
    """注入假取数源（零联网）。fail=True 时全部源抛异常；per_source 可按源名给不同池。"""

    def _make(name):
        if per_source is not None and name in per_source:
            fixed = per_source[name]
            if callable(fixed):
                return fixed
            return lambda custom_codes: list(fixed)
        if fail:
            def _boom(custom_codes):
                raise RuntimeError("网络不可达（测试注入）")
            return _boom

        def _fake(custom_codes):
            return list(universe)
        return _fake

    monkeypatch.setattr(ner, "_UNIVERSE_SOURCES", {
        "local_api": _make("local_api"),
        "akspot": _make("akspot"),
        "custom": _make("custom"),
    })


def _assert_validation_422(r):
    assert r.status_code == 422, f"期望 422，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert j["status"] == "error" and j["code"] == "validation_error", j
    assert j["data"] is None, j


# ───────────── ① 正常执行 ─────────────
def test_execute_happy_path(client, auth, monkeypatch):
    _install_sources(monkeypatch)
    monkeypatch.setattr("modules.risk_gate.scan_and_gate", _pass_gate)
    r = client.post(URL, json={
        "query": "创业板 市盈率小于30 且 营收增长大于20% 的票，按营收增长排序，取前10",
        "scope": "local_api",
    }, headers=auth)
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok" and j["code"] == "ok", j
    d = j["data"]
    assert d["available"] is True, d
    # 解析透明：spec 原样摊开
    assert d["spec"]["boards"] == ["cyb"], d["spec"]
    assert {"field": "pe", "op": "lt", "value": 30.0} in [
        {"field": f["field"], "op": f["op"], "value": f["value"]} for f in d["spec"]["filters"]
    ], d["spec"]
    assert d["spec"]["sort"] == "rev_growth" and d["spec"]["sort_dir"] == "desc", d["spec"]
    assert d["spec"]["limit"] == 10, d["spec"]
    assert d["spec"]["unparsed"] == [], d["spec"]
    # 计数与真实链路
    assert d["n_universe"] == 10, d
    assert d["n_matched"] == 2, d  # 300001(pe25,rg30) 与 300003(pe10,rg50)
    assert [row["code"] for row in d["rows"]] == ["300003", "300001"], d["rows"]
    assert d["rows"][0]["name"] == "假股辛", d["rows"]
    assert d["source_used"] == "local_api", d
    assert d["gated_out"]["count"] == 0, d
    assert isinstance(d["elapsed_ms"], int) and d["elapsed_ms"] >= 0, d
    assert d["note"], d


def test_execute_rows_truncated_to_100(client, auth, monkeypatch):
    big = [{"code": f"{600100 + i:06d}", "name": f"假股{i}", "pe": 10.0,
            "rev_growth": 1.0, "concepts": []} for i in range(120)]
    _install_sources(monkeypatch, universe=big)
    monkeypatch.setattr("modules.risk_gate.scan_and_gate", _pass_gate)
    r = client.post(URL, json={"query": "市盈率小于30"}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True and d["n_universe"] == 120 and d["n_matched"] == 120, d
    assert len(d["rows"]) == 100 and d["n_rows"] == 100, len(d["rows"])


def test_execute_scope_all_merges_sources(client, auth, monkeypatch):
    left = [{"code": "600001", "name": "假股丁", "pe": 15.0, "concepts": []}]
    right = [{"code": "000001", "name": "假股己", "pe": 8.0, "concepts": []}]
    def _absent(custom_codes):
        raise RuntimeError("该源未在测试中提供")

    _install_sources(monkeypatch, per_source={
        "local_api": left, "akspot": right, "custom": _absent,
    })
    monkeypatch.setattr("modules.risk_gate.scan_and_gate", _pass_gate)
    r = client.post(URL, json={"query": "市盈率小于30", "scope": "all"}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True, d
    assert d["source_used"] == "local_api+akspot", d
    assert d["n_universe"] == 2, d  # 按 code 去重合并
    assert {row["code"] for row in d["rows"]} == {"600001", "000001"}, d


# ───────────── ② 全未理解 → available=false，不执行 ─────────────
def test_execute_unparsed_query_not_executed(client, auth, monkeypatch):
    _install_sources(monkeypatch)
    r = client.post(URL, json={"query": "今天天气怎么样"}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok", j
    d = j["data"]
    assert d["available"] is False, d
    assert d["reason"] == "未能从语句解析出任何选股条件", d
    assert d["spec"]["unparsed"] == ["今天天气怎么样"], d["spec"]  # 未理解词如实标注
    assert d["n_universe"] == 0 and d["rows"] == [], d  # 不执行、不伪造


# ───────────── ③ 候选池全源失败 → available=false + 真实原因 ─────────────
def test_execute_universe_all_sources_fail(client, auth, monkeypatch):
    _install_sources(monkeypatch, fail=True)
    r = client.post(URL, json={"query": "市盈率小于30"}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is False, d
    assert "候选池获取失败" in d["reason"], d
    # 真实逐源原因：三级降级链的每一源都如实记录
    assert "local_api" in d["reason"] and "akspot" in d["reason"], d
    assert d["n_universe"] == 0 and d["n_matched"] == 0 and d["rows"] == [], d


# ───────────── ④⑤ 校验失败 422 ─────────────
@pytest.mark.parametrize("body", [
    {},                                  # query 缺失
    {"query": ""},                       # query 空串
    {"query": "   "},                    # query 全空白
    {"query": 123},                      # query 非字符串
    {"query": "市" * 201},               # query 超长
    {"query": "市盈率小于30", "scope": "自选股"},   # scope 非法（v1 中文枚举不收）
    {"query": "市盈率小于30", "scope": 123},        # scope 非字符串
    {"query": "市盈率小于30", "custom_codes": 123}, # custom_codes 非字符串
    ["not-a-dict"],                      # body 非对象
])
def test_execute_validation_422(client, auth, monkeypatch, body):
    _install_sources(monkeypatch)
    r = client.post(URL, json=body, headers=auth)
    _assert_validation_422(r)


# ───────────── ⑥ 无 token 401 ─────────────
def test_execute_no_token_401(client, monkeypatch):
    _install_sources(monkeypatch)
    r = client.post(URL, json={"query": "市盈率小于30"})
    assert r.status_code == 401, f"期望 401，实得 {r.status_code}: {r.text[:300]}"
    assert r.get_json()["status"] == "error", r.get_json()


# ───────────── ⑦ NaN/Inf → None（合法 JSON）─────────────
def test_execute_nan_inf_become_none(client, auth, monkeypatch):
    _install_sources(monkeypatch)
    monkeypatch.setattr("modules.risk_gate.scan_and_gate", _pass_gate)
    # 假股癸 pe=12 命中「市盈率小于30」，其 turnover=NaN / chg_pct=Inf 须清洗为 None
    r = client.post(URL, json={"query": "市盈率小于30"}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True, d
    row = next(x for x in d["rows"] if x["code"] == "600003")
    assert row["turnover"] is None, row
    assert row["chg_pct"] is None, row
    assert row["pe"] == 12.0, row  # 正常值不受影响


# ───────────── ⑧ 二道闸异常不崩（业务降级路径）─────────────
def test_execute_gate_exception_degrades_gracefully(client, auth, monkeypatch):
    _install_sources(monkeypatch)

    def _boom(candidates, top_k=1, **_kw):
        raise RuntimeError("排雷服务不可用（测试注入）")

    monkeypatch.setattr("modules.risk_gate.scan_and_gate", _boom)
    r = client.post(URL, json={"query": "创业板 市盈率小于30 且 营收增长大于20%"}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True, d  # 降级放行，不崩
    assert {row["code"] for row in d["rows"]} == {"300003", "300001"}, d  # 条件命中原样保留
    assert d["gated_out"]["count"] == 0 and d["gated_out"]["note"], d
    assert "二道闸异常" in d["gated_out"]["note"], d


def test_execute_gate_kick_removes_rows(client, auth, monkeypatch):
    """二道闸拦截标的不进结果（gated_out 计数与原因摘要如实返回）。"""
    _install_sources(monkeypatch)

    def _kick(candidates, top_k=1, **_kw):
        return list(candidates), {"kicked": [
            {"code": "300003", "name": "假股辛", "reasons": ["测试拦截：六维红旗"]},
        ]}

    monkeypatch.setattr("modules.risk_gate.scan_and_gate", _kick)
    r = client.post(URL, json={"query": "创业板 市盈率小于30 且 营收增长大于20%"}, headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True, d
    assert d["n_matched"] == 2, d  # 排雷前命中 2 只
    assert [row["code"] for row in d["rows"]] == ["300001"], d  # 拦截标的不进结果
    assert d["gated_out"]["count"] == 1, d
    assert d["gated_out"]["items"][0]["code"] == "300003", d
    assert "测试拦截" in d["gated_out"]["items"][0]["reasons"][0], d


# ───────────── custom_codes 优先池 ─────────────
def test_execute_custom_codes_pool(client, auth, monkeypatch):
    _install_sources(monkeypatch, universe=FAKE_UNIVERSE)

    captured = {}

    def _custom(custom_codes):
        captured["custom_codes"] = custom_codes
        return [{"code": "600001", "name": "假股丁", "pe": 15.0, "concepts": []}]

    monkeypatch.setattr(ner, "_UNIVERSE_SOURCES", {
        "local_api": lambda c: list(FAKE_UNIVERSE),
        "akspot": lambda c: list(FAKE_UNIVERSE),
        "custom": _custom,
    })
    monkeypatch.setattr("modules.risk_gate.scan_and_gate", _pass_gate)
    r = client.post(URL, json={
        "query": "市盈率小于30", "scope": "local_api", "custom_codes": "600001, 000002",
    }, headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True, d
    assert captured["custom_codes"] == "600001, 000002", captured
    assert d["source_used"] == "custom" and d["n_universe"] == 1, d  # 显式代码池优先
    assert [row["code"] for row in d["rows"]] == ["600001"], d
