# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_read_routes.py — W1 只读端点回归守卫。

验证：
  1. 每个新端点无 token -> 401（鉴权闸门）；
  2. 有合法 token 且背后数据文件存在 -> 200 + 信封 {status:ok, code:ok, ...}；
  3. 背后文件缺失 -> 200 + status=error（优雅降级，绝不 500）；
  4. 非法 date/user 参数 -> 400 validation_error（防穿越）；
  5. /api/openapi.json 覆盖 /api/v2/read/* 路径。

为避免触碰真实 data/，测试把 read_routes 模块的目录常量 monkeypatch 到临时树。
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
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402


# 实际请求用的具体路径（含参数/具体日期）
ENDPOINTS = [
    "/api/v2/read/six-dim?code=600519",
    "/api/v2/read/daily-snapshot",
    "/api/v2/read/daily-recommendation",
    "/api/v2/read/user-dashboard",
    "/api/v2/read/alert-rules",
    "/api/v2/read/alert-log",
    "/api/v2/read/virtual-users-sim",
    "/api/v2/read/p1-signals",
    "/api/v2/read/snapshot-dates",
    "/api/v2/read/snapshot/2026-08-31",
    "/api/v2/read/paper-trades?user=demo",
    "/api/v2/read/review-notes?date=2026-08-31",
    "/api/v2/read/webapps",
    "/api/v2/read/breadth-timeseries",
    "/api/v2/read/ladder-detail",
    "/api/v2/read/breadth-history",
    "/api/v2/read/event-pool",
    "/api/v2/read/prediction-log",
    "/api/v2/read/p1-sync-status",
    "/api/v2/read/backtest-runs",
    "/api/v2/read/data-refresh-state",
]

# OpenAPI spec 中的路径（<date> 在 spec 里被渲染成 {date}）
SPEC_PATHS = [
    "/api/v2/read/six-dim",
    "/api/v2/read/daily-snapshot",
    "/api/v2/read/daily-recommendation",
    "/api/v2/read/user-dashboard",
    "/api/v2/read/alert-rules",
    "/api/v2/read/alert-log",
    "/api/v2/read/virtual-users-sim",
    "/api/v2/read/p1-signals",
    "/api/v2/read/snapshot-dates",
    "/api/v2/read/snapshot/{date}",
    "/api/v2/read/paper-trades",
    "/api/v2/read/review-notes",
    "/api/v2/read/webapps",
    "/api/v2/read/breadth-timeseries",
    "/api/v2/read/ladder-detail",
    "/api/v2/read/breadth-history",
    "/api/v2/read/event-pool",
    "/api/v2/read/prediction-log",
    "/api/v2/read/p1-sync-status",
    "/api/v2/read/backtest-runs",
    "/api/v2/read/data-refresh-state",
]


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
        u = User(username="rwuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def client(app, tmp_path_factory):
    # 构造隔离的临时数据树并 monkeypatch 模块目录常量
    root = tmp_path_factory.mktemp("readroot")
    data = root / "data"
    reports = root / "reports"
    webapps = root / "webapps"
    for d in (data, reports, webapps):
        d.mkdir(parents=True, exist_ok=True)

    (data / "daily_snapshot.json").write_text(json.dumps({"date": "2026-08-31", "temperature": 42}),
                                              encoding="utf-8")
    (data / "daily_recommendation.json").write_text(json.dumps({"picks": [{"code": "600519"}]}),
                                                   encoding="utf-8")
    (data / "user_dashboard.json").write_text(json.dumps({"layout": "grid"}), encoding="utf-8")
    (data / "alert_rules.json").write_text(json.dumps({"rules": []}), encoding="utf-8")
    (data / "alerts.log").write_text("[2026-08-31] rule fired\n", encoding="utf-8")
    (reports / "virtual_users_sim.json").write_text(json.dumps({"meta": {"n_users": 100}}),
                                                   encoding="utf-8")

    p1 = data / "p1_signals"
    p1.mkdir(exist_ok=True)
    (p1 / "signal_ev.json").write_text(json.dumps({"model": "ev", "top": [{"code": "600519"}]}),
                                       encoding="utf-8")

    snaps = data / "snapshots"
    snaps.mkdir(exist_ok=True)
    (snaps / "2026-08-31.json").write_text(json.dumps({"date": "2026-08-31"}), encoding="utf-8")
    (snaps / "2026-09-01.json").write_text(
        json.dumps({
            "date": "2026-09-01",
            "temperature": 40,
            "indicators": {
                "up_count": 2000,
                "down_count": 1500,
                "limit_up": 50,
                "limit_down": 10,
                "red_ratio": 57.0,
                "median_chg": 0.4,
            },
        }),
        encoding="utf-8",
    )

    (data / "shepherd_ladder_history.json").write_text(
        json.dumps({
            "2026-09-01": {
                "date": "2026-09-01",
                "distribution": {"5": 1, "3": 4, "1": 45},
                "max_boards": 5,
                "total_connect": 18,
                "updated_at": "2026-09-01T15:30",
            }
        }),
        encoding="utf-8",
    )

    # 长周期广度历史（个别字段为 NaN，验证 _sanitize 清洗为 null）
    (data / "shepherd_history.json").write_text(
        json.dumps([
            {
                "date": "2026-08-31",
                "up_count": 3500,
                "down_count": 1500,
                "limit_up": 70,
                "limit_down": 5,
                "red_ratio": 70.0,
                "connect_hl": 7,
                "zt_fail_ratio": 9.0,
                "zt_prev_ret": 2.3,
            },
            {
                "date": "2026-09-01",
                "up_count": 2000,
                "down_count": 1500,
                "limit_up": 50,
                "limit_down": 10,
                "red_ratio": 57.0,
                "connect_hl": float("nan"),
                "zt_fail_ratio": 11.0,
                "zt_prev_ret": 1.0,
            },
        ]),
        encoding="utf-8",
    )

    # W3 后续簇 · 5 个真实数据源（字段名按 2026-11-07 真扫，非臆造）
    (data / "event_pool_brief.json").write_text(
        json.dumps({
            "date": "2026-11-06",
            "model": "ev",
            "source": "P1-QuantFactor EV 事件因子",
            "note": "统计意义上的超额收益概率排序，非买卖指令",
            "count": 1,
            "pool": [{"rank": 1, "symbol": "sh600707", "score": 100.0,
                      "raw_rank": 1.0, "raw_pred": 0.098, "signal": "看多",
                      "source": "P1-ev-top_long"}],
        }),
        encoding="utf-8",
    )
    (data / "prediction_log.json").write_text(
        json.dumps([
            {"date": "2026-09-02", "temp": 33.8, "cycle": "退潮", "bias": "偏空",
             "pct": 10, "realized": 0.02, "hit": False},
            {"date": "2026-11-06", "temp": 33.0, "cycle": "修复试探", "bias": "中性",
             "pct": 29, "event_adj": 2, "event_available": True,
             "realized": None, "hit": None},
        ]),
        encoding="utf-8",
    )
    (data / "p1_sync_status.json").write_text(
        json.dumps({
            "run_at": "2026-11-07T15:19:07",
            "mode": "scheduler",
            "ok": True,
            "target_dir": "E:/secret/top_level",
            "health": {
                "status": "warn",
                "message": "4 个副本超出新鲜度 SLA",
                "rows": [{"file": "signal_ev_h10.json", "model_key": "ev",
                          "latest_date": "2026-10-21", "age_days": 17}],
            },
            # 嵌套在 dict / list 内的敏感 key，验证 _strip_sensitive 是递归的
            "extra_info": {
                "nested_dict": {"target_dir": "E:/secret/nested_dict", "ok": True},
                "nested_list": [{"target_dir": "E:/secret/nested_list", "n": 1}],
            },
        }),
        encoding="utf-8",
    )
    (data / "backtest_runs.json").write_text(
        json.dumps({"runs": [{
            "run_id": "20261023-162048-009d8c07562a",
            "created_at": "2026-10-23T16:20:48",
            "status": "success",
            "params": {"ticker": "601088", "strategy": "multi_factor"},
            "summary": {"total_return_pct": -1.88, "sharpe_ratio": -0.31},
        }]}),
        encoding="utf-8",
    )
    (data / "data_refresh_state.json").write_text(
        json.dumps({
            "attempts_today": 1,
            "last_run_date": "2026-11-05",
            "last_result": "ok",
            "finished_at": "2026-11-05T19:23:31",
            "last_csv_date": "2026-11-02",
            "detail": "exit=0 末行推进",
        }),
        encoding="utf-8",
    )

    (data / "paper_demo.json").write_text(json.dumps({"cash": 100000}), encoding="utf-8")
    (data / "review_notes_2026-08-31.md").write_text("# 复盘\n今日缩量。\n", encoding="utf-8")

    wa = webapps / "foo"
    wa.mkdir(parents=True, exist_ok=True)
    (wa / "meta.json").write_text(
        json.dumps({"title": "Demo WebApp", "entry": "index.html", "added": "2026-08-31"}),
        encoding="utf-8",
    )

    rr._DATA_DIR = data.resolve()
    rr._REPORTS_DIR = reports.resolve()
    rr._WEBAPPS_DIR = webapps.resolve()
    rr._FILE_WHITELIST = {
        "daily_snapshot": data / "daily_snapshot.json",
        "daily_recommendation": data / "daily_recommendation.json",
        "user_dashboard": data / "user_dashboard.json",
        "alert_rules": data / "alert_rules.json",
        "alert_log": data / "alerts.log",
        "virtual_users_sim": reports / "virtual_users_sim.json",
        "ladder_detail": data / "shepherd_ladder_history.json",
        "breadth_history": data / "shepherd_history.json",
        "event_pool": data / "event_pool_brief.json",
        "prediction_log": data / "prediction_log.json",
        "p1_sync_status": data / "p1_sync_status.json",
        "backtest_runs": data / "backtest_runs.json",
        "data_refresh_state": data / "data_refresh_state.json",
    }
    return app.test_client()


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        u = User.query.filter_by(username="rwuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_auth_gate_requires_token(client):
    """所有新端点无 token 必须 401。"""
    for ep in ENDPOINTS:
        resp = client.get(ep)
        assert resp.status_code == 401, f"无 token 应 401: {ep} -> {resp.status_code}"


def test_existing_files_return_ok_envelope(client, token):
    """背后文件存在 -> 200 + status=ok 信封。"""
    # 固定文件类
    for ep, key in (
        ("/api/v2/read/daily-snapshot", "daily_snapshot.json"),
        ("/api/v2/read/daily-recommendation", "daily_recommendation.json"),
        ("/api/v2/read/user-dashboard", "user_dashboard.json"),
        ("/api/v2/read/alert-rules", "alert_rules.json"),
        ("/api/v2/read/alert-log", "alerts.log"),
        ("/api/v2/read/virtual-users-sim", "virtual_users_sim.json"),
    ):
        obj = client.get(ep, headers=_auth(token)).get_json()
        assert obj["status"] == "ok" and obj["code"] == "ok", f"{ep}: {obj}"

    # 目录/参数化类
    obj = client.get("/api/v2/read/p1-signals", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and "signal_ev.json" in obj["data"], obj

    obj = client.get("/api/v2/read/snapshot-dates", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and "2026-08-31" in obj["data"], obj

    obj = client.get("/api/v2/read/snapshot/2026-08-31", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"]["date"] == "2026-08-31", obj

    obj = client.get("/api/v2/read/paper-trades?user=demo", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"]["cash"] == 100000, obj

    obj = client.get("/api/v2/read/review-notes?date=2026-08-31",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and "复盘" in obj["data"]["content"], obj

    obj = client.get("/api/v2/read/webapps", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"][0]["title"] == "Demo WebApp", obj

    # W3 新增只读端点（聚合 snapshots / 读取 shepherd_ladder_history）
    obj = client.get("/api/v2/read/breadth-timeseries", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and isinstance(obj["data"], list) and len(obj["data"]) >= 1, obj
    bt = next((r for r in obj["data"] if r["date"] == "2026-09-01"), None)
    assert bt is not None and bt["up_count"] == 2000, obj

    obj = client.get("/api/v2/read/ladder-detail", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and isinstance(obj["data"], list) and len(obj["data"]) >= 1, obj
    ld = next((r for r in obj["data"] if r["date"] == "2026-09-01"), None)
    assert ld is not None and ld["max_boards"] == 5, obj

    # 长周期广度历史（shepherd_history，含 NaN 字段须被清洗为 null）
    obj = client.get("/api/v2/read/breadth-history", headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and isinstance(obj["data"], list) and len(obj["data"]) >= 1, obj
    bh = next((r for r in obj["data"] if r["date"] == "2026-09-01"), None)
    assert bh is not None and bh["connect_hl"] is None, obj  # NaN -> None（_sanitize）


def _collect_keys(obj, out=None):
    """递归收集响应中出现过的所有 dict key（脱敏验证不做字符串包含判断）。"""
    if out is None:
        out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _collect_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_keys(v, out)
    return out


def test_w3_endpoints_fields_and_sensitive_stripping(client, token):
    """W3 后续簇 5 端点：字段真值 + p1-sync-status 递归剔除 target_dir。"""
    h = _auth(token)

    obj = client.get("/api/v2/read/event-pool", headers=h).get_json()
    assert obj["status"] == "ok", obj
    assert obj["data"]["count"] == 1 and obj["data"]["pool"][0]["symbol"] == "sh600707", obj
    assert obj["data"]["note"] == "统计意义上的超额收益概率排序，非买卖指令", obj

    obj = client.get("/api/v2/read/prediction-log", headers=h).get_json()
    assert obj["status"] == "ok" and isinstance(obj["data"], list) and len(obj["data"]) == 2, obj
    assert obj["data"][0]["date"] == "2026-09-02", obj
    assert obj["data"][1]["hit"] is None and obj["data"][1]["realized"] is None, obj

    obj = client.get("/api/v2/read/p1-sync-status", headers=h).get_json()
    assert obj["status"] == "ok" and obj["data"]["ok"] is True, obj
    assert obj["data"]["health"]["status"] == "warn", obj
    assert "target_dir" not in _collect_keys(obj), "绝对路径 key 未被递归剔除"

    obj = client.get("/api/v2/read/backtest-runs", headers=h).get_json()
    assert obj["status"] == "ok", obj
    assert obj["data"]["runs"][0]["run_id"] == "20261023-162048-009d8c07562a", obj
    assert obj["data"]["runs"][0]["summary"]["total_return_pct"] == -1.88, obj

    obj = client.get("/api/v2/read/data-refresh-state", headers=h).get_json()
    assert obj["status"] == "ok" and obj["data"]["last_result"] == "ok", obj


def test_missing_files_graceful_error(client, token):
    """文件缺失 -> 200 + status=error（优雅，不 500）。"""
    for ep in (
        "/api/v2/read/snapshot/2099-01-01",
        "/api/v2/read/paper-trades?user=nobody",
        "/api/v2/read/review-notes?date=2099-01-01",
    ):
        resp = client.get(ep, headers=_auth(token))
        assert resp.status_code == 200, f"{ep} 缺失应 200 而非 {resp.status_code}: {resp.text[:120]}"
        obj = resp.get_json()
        assert obj["status"] == "error" and obj["code"] == "not_found", f"{ep}: {obj}"


def test_invalid_params_validation_error(client, token):
    """非法 date/user -> 400 validation_error（防穿越）。"""
    for ep in (
        "/api/v2/read/snapshot/2026-13-99",
        "/api/v2/read/paper-trades?user=bad%2Fuser",  # 含 '/'
        "/api/v2/read/review-notes?date=not-a-date",
    ):
        resp = client.get(ep, headers=_auth(token))
        assert resp.status_code == 400, f"{ep} 应 400: {resp.status_code} {resp.text[:120]}"
        obj = resp.get_json()
        assert obj["code"] == "validation_error", f"{ep}: {obj}"


def test_openapi_covers_read_routes(client):
    """spec 必须覆盖全部 /api/v2/read/* 路径且标注 BearerAuth。"""
    spec = client.get("/api/openapi.json").get_json()
    paths = spec["paths"]
    for base in SPEC_PATHS:
        node = paths.get(base)
        assert node is not None, f"spec 缺失路径: {base}"
        assert "get" in node, f"{base} 缺 get"
        assert node["get"].get("security") == [{"BearerAuth": []}], f"{base} 未标注鉴权"


# ───────────── W4-A 六维评分端点：确定性回归（monkeypatch 三取数源，零网络）─────────────
# 仅 patch 模块级 _six_dim_hist/_six_dim_spot/_six_dim_fin，端点内部的
# get_fetcher / akshare / compute_dims 均为真实逻辑或纯函数，绝不触发网络调用。


def _fake_hist_ok():
    """含中文「收盘」+「日期」列的 120 根日线，末根为权威日期来源。"""
    import pandas as pd
    n = 120
    return pd.DataFrame({
        "日期": pd.date_range("2026-01-01", periods=n).strftime("%Y-%m-%d").tolist(),
        "收盘": [100.0 + i * 0.5 for i in range(n)],
    })


def _fake_fin_roe_only():
    """财务摘要只含 ROE 行、不含「净利润同比」行 → fundamental 有值 / growth 缺失。"""
    import pandas as pd
    return pd.DataFrame([
        {"选项": "常用指标", "指标": "净资产收益率(加权)", "2025-09-30": "15.3"},
        {"选项": "常用指标", "指标": "归母净利润", "2025-09-30": "100.0"},
    ])


def _patch_six_dim(monkeypatch, hist, spot, fin):
    monkeypatch.setattr(rr, "_six_dim_hist", lambda code: hist)
    monkeypatch.setattr(rr, "_six_dim_spot", lambda code: spot)
    monkeypatch.setattr(rr, "_six_dim_fin", lambda code: fin)


def test_six_dim_requires_token(client):
    """六维端点无 token -> 401（鉴权闸门先于参数校验与取数）。"""
    resp = client.get("/api/v2/read/six-dim?code=600519")
    assert resp.status_code == 401, resp.get_data(as_text=True)[:200]


def test_six_dim_ok_envelope(client, token, monkeypatch):
    """合法 code + 三源齐备 -> 200 + 标准 ok 信封 + 契约字段齐全。"""
    h = _fake_hist_ok()
    _patch_six_dim(monkeypatch, h,
                   {"换手率": 2.5, "量比": 1.2, "市盈率-动态": 28.1, "市净率": 8.2},
                   _fake_fin_roe_only())
    resp = client.get("/api/v2/read/six-dim?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("code", "dims", "overall", "coverage", "missing", "date", "raw", "note"):
        assert k in d, f"data 缺字段 {k}: {d}"
    assert d["code"] == "600519"
    assert list(d["dims"].keys()) == ["technical", "capital", "value",
                                      "growth", "fundamental", "cycle"]
    assert d["date"] == str(h["日期"].iloc[-1])[:10]  # 取自 K 线末根，非 now()
    assert isinstance(d["raw"], dict) and "state" in d["raw"]
    assert d["raw"]["pe"] == 28.1 and d["raw"]["pb"] == 8.2


def test_six_dim_invalid_and_missing_code(client, token):
    """非法 / 缺失 code -> 400 invalid_param（参数校验先于取数，零网络）。"""
    for qs in ("?code=abc", "?code=60051", "?code=6005199", ""):
        resp = client.get(f"/api/v2/read/six-dim{qs}", headers=_auth(token))
        assert resp.status_code == 400, f"{qs}: {resp.status_code}"
        obj = resp.get_json()
        assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


def test_six_dim_missing_dims_null_and_coverage(client, token, monkeypatch):
    """部分源缺字段 -> 对应维必须为 null（禁止补 0）、missing/coverage 正确、overall 不含缺维。"""
    # spot 仅 pe/pb（无换手率/量比）→ capital 缺；fin 仅 ROE（无同比）→ growth 缺
    _patch_six_dim(monkeypatch, _fake_hist_ok(),
                   {"市盈率-动态": 28.1, "市净率": 8.2},
                   _fake_fin_roe_only())
    d = client.get("/api/v2/read/six-dim?code=600519",
                   headers=_auth(token)).get_json()["data"]
    assert d["dims"]["capital"] is None, "缺失维必须为 null，禁止补 0"
    assert d["dims"]["growth"] is None, "缺失维必须为 null，禁止补 0"
    assert d["missing"] == ["capital", "growth"], d["missing"]
    assert d["coverage"] == 6 - len(d["missing"]) == 4, d["coverage"]
    valid = [v for v in d["dims"].values() if v is not None]
    assert len(valid) == 4 and all(isinstance(v, float) for v in valid), d["dims"]
    assert abs(d["overall"] - round(sum(valid) / 4, 1)) < 1e-9, d


def test_six_dim_all_sources_fail_honest_degradation(client, token, monkeypatch):
    """三源全失败 -> status 仍 ok（不伪装失败/不 500），六维全 null、coverage=0、overall=null。"""
    _patch_six_dim(monkeypatch, None, {}, None)
    resp = client.get("/api/v2/read/six-dim?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert all(v is None for v in d["dims"].values()), d["dims"]
    assert d["coverage"] == 0 and d["overall"] is None, d
    assert d["date"] is None and d["missing"] == list(d["dims"].keys()), d


def test_six_dim_nan_inf_sanitized(client, token, monkeypatch):
    """raw 含 NaN/Inf -> 清洗为 null，响应不含裸 NaN/Infinity 字面量（合法 JSON）。"""
    _patch_six_dim(monkeypatch, _fake_hist_ok(),
                   {"换手率": float("nan"), "量比": float("inf"),
                    "市盈率-动态": 28.1, "市净率": 8.2},
                   _fake_fin_roe_only())
    resp = client.get("/api/v2/read/six-dim?code=600519", headers=_auth(token))
    body = resp.get_data(as_text=True)
    assert "NaN" not in body and "Infinity" not in body, body[:300]
    raw = resp.get_json()["data"]["raw"]
    assert raw["turnover"] is None, raw   # NaN -> null
    assert raw["vol_ratio"] is None, raw  # Inf -> null
    assert raw["pe"] == 28.1, raw


def test_six_dim_in_frontend_spec_file():
    """磁盘 frontend-v2/spec/openapi.json 必须覆盖 /api/v2/read/six-dim 且标注 BearerAuth。"""
    path = os.path.join(PROJECT_ROOT, "frontend-v2", "spec", "openapi.json")
    with open(path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    node = spec["paths"].get("/api/v2/read/six-dim")
    assert node is not None and "get" in node, "spec 缺 /api/v2/read/six-dim"
    assert node["get"].get("security") == [{"BearerAuth": []}], node


def test_six_dim_parallel_source_failure_degrades(client, token, monkeypatch):
    """三源并行路径：某源抛异常（失败）-> 对应维 null、coverage 正确、overall 非 0 兜底。

    走真实 fetch_many（不 patch 它）：_six_dim_spot 抛异常被 _safe 吞成 None，
    端点按 {} 降级；验证 capital/value 为 null（禁止补 0），overall 只对有效维等权平均。
    """
    def boom_spot(code):
        raise RuntimeError("spot source timeout")

    monkeypatch.setattr(rr, "_six_dim_hist", lambda code: _fake_hist_ok())
    monkeypatch.setattr(rr, "_six_dim_spot", boom_spot)
    monkeypatch.setattr(rr, "_six_dim_fin", lambda code: _fake_fin_roe_only())

    resp = client.get("/api/v2/read/six-dim?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert d["dims"]["capital"] is None and d["dims"]["value"] is None, \
        "spot 源失败 -> capital/value 必须为 null（禁止补 0）"
    assert d["coverage"] == 6 - len(d["missing"]), d
    valid = [v for v in d["dims"].values() if v is not None]
    assert valid and abs(d["overall"] - round(sum(valid) / len(valid), 1)) < 1e-9, d


def test_six_dim_parallel_timeout_degrades(client, token, monkeypatch):
    """整批超时/未完成项（预填 None）-> 对应维 null、date=null、coverage 正确、overall 非 0 兜底。

    patch fetch_many 模拟 hist 超时未完成（res['hist']=None）、其余两源已完成，
    验证端点按 None 诚实降级，绝不拿 0 或 now() 兜底。
    """
    def fake_fetch_many(tasks, max_workers=None, timeout=None):
        return {
            "hist": None,  # 超时/未完成
            "spot": {"市盈率-动态": 28.1, "市净率": 8.2},
            "fin": _fake_fin_roe_only(),
        }

    monkeypatch.setattr("modules.fetch_parallel.fetch_many", fake_fetch_many)
    resp = client.get("/api/v2/read/six-dim?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert d["dims"]["technical"] is None and d["dims"]["cycle"] is None, d["dims"]
    assert d["date"] is None, "hist 超时 -> date 必须 null，绝不用 now() 兜底"
    assert d["coverage"] == 6 - len(d["missing"]), d
    valid = [v for v in d["dims"].values() if v is not None]
    assert valid and abs(d["overall"] - round(sum(valid) / len(valid), 1)) < 1e-9, d
