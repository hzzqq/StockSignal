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
    "/api/v2/read/fundamentals?code=600519",
    "/api/v2/read/financials?code=600519",
    "/api/v2/read/stock-kline?code=600519",
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
    "/api/v2/read/factor-analysis?codes=600519,000001,300750&days=60&factor=momentum&n_layers=5&forward=1",
    "/api/v2/read/backtest?ticker=600519&start=2024-01-01&end=2024-12-31&strategy=multi_factor",
    "/api/v2/read/market-panorama?k=8",
    "/api/v2/read/portfolio",
    "/api/v2/read/fund-flow",
    "/api/v2/read/trading-account",
    "/api/v2/read/macro-data",
]

# OpenAPI spec 中的路径（<date> 在 spec 里被渲染成 {date}）
SPEC_PATHS = [
    "/api/v2/read/six-dim",
    "/api/v2/read/fundamentals",
    "/api/v2/read/financials",
    "/api/v2/read/stock-kline",
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
    "/api/v2/read/factor-analysis",
    "/api/v2/read/backtest",
    "/api/v2/read/market-panorama",
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
            "signal_dir": "E:/secret/top_level_signal",
            "status_file": "E:/secret/top_level_status",
            "health": {
                "status": "warn",
                "message": "4 个副本超出新鲜度 SLA",
                "signal_dir": "E:/secret/health_signal",
                "status_file": "E:/secret/health_status",
                "rows": [{"file": "signal_ev_h10.json", "model_key": "ev",
                          "latest_date": "2026-10-21", "age_days": 17}],
            },
            # 嵌套在 dict / list 内的敏感 key，验证 _strip_sensitive 是递归的
            "extra_info": {
                "nested_dict": {"target_dir": "E:/secret/nested_dict",
                                "signal_dir": "E:/secret/nested_sd", "ok": True},
                "nested_list": [{"target_dir": "E:/secret/nested_list",
                                 "status_file": "E:/secret/nested_sf", "n": 1}],
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


def test_daily_recommendation_boundary_gate_drops_high(client, token):
    """T-245：输出边界二道闸——即便 JSON 含 overall_level==high 的标的，也被剔除。

    验证 unknown≠guilty：low / not_scanned 一律保留；仅已确认 high 被剔除，且
    在返回信封注明剔除数（不静默）。还原模块级临时文件，避免污染同模块其它用例。
    """
    import json as _json
    path = rr._FILE_WHITELIST["daily_recommendation"]
    original = path.read_text(encoding="utf-8")
    payload = {"picks": [
        {"code": "600519", "name": "安全", "risk_scan": {"status": "scanned", "overall_level": "low"}},
        {"code": "600666", "name": "高危", "risk_scan": {"status": "scanned", "overall_level": "high"}},
        {"code": "600888", "name": "未扫", "risk_scan": {"status": "not_scanned"}},
    ]}
    try:
        path.write_text(_json.dumps(payload), encoding="utf-8")
        obj = client.get("/api/v2/read/daily-recommendation", headers=_auth(token)).get_json()
        assert obj["status"] == "ok" and obj["code"] == "ok", obj
        codes = [p["code"] for p in obj["data"]["picks"]]
        assert "600666" not in codes, "高危标的应被输出边界二道闸剔除"
        assert "600519" in codes and "600888" in codes, "low / not_scanned 应保留（unknown≠guilty）"
        assert obj["data"].get("risk_gate_boundary_dropped") == 1
    finally:
        path.write_text(original, encoding="utf-8")

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
    keys = _collect_keys(obj)
    for banned in ("target_dir", "signal_dir", "status_file"):
        assert banned not in keys, f"敏感 key {banned} 未被递归剔除"
    # 防御性：任何 E: 绝对路径泄露都不允许（含被转义的反斜杠形式）
    dump = json.dumps(obj, ensure_ascii=False)
    assert ("E:/" not in dump) and ("E:\\" not in dump), f"响应泄露绝对路径: {dump[:200]}"

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


# ───────────── W4-B 三端点确定性回归（monkeypatch _w4b_* 取数源，零网络）─────────────
# 仅 patch 模块级 _w4b_basic/_w4b_spot/_w4b_kline/_w4b_financial（端点内 lambda 引用
# 模块全局，patch 对 fetch_many 线程池可见，与 W4-A _patch_six_dim 同款，已验证）。
# perf / financials rows 均走真实纯逻辑（_w4b_compute_perf / _w4b_financial_rows），
# 只用假 DataFrame 喂入，绝不真调 akshare / 新浪 / 东财 / BaoStock。

_W4B_OK_NOTE = "逐字段独立取数、独立降级；缺失为 null 且不补 0"


def _w4b_fake_basic():
    return {"name": "贵州茅台", "industry": "白酒", "price": 1688.0,
            "pe_ttm": 28.1, "market_cap": 21000.0}


def _w4b_fake_spot():
    return {"datetime": "2026-11-07 15:00:00", "current": 1688.0}


def _w4b_fake_kline(with_bad=False):
    import pandas as pd
    df = pd.DataFrame({
        "date": ["2026-11-05", "2026-11-06", "2026-11-07"],
        "open": [1.0, 2.0, 3.0],
        "close": [1.1, 2.2, 3.3],
        "high": [1.2, 2.3, 3.4],
        "low": [0.9, 1.9, 2.9],
        "volume": [100, 200, 300],
    })
    if with_bad:
        df.loc[1, "close"] = float("nan")   # 原生 NaN：验证 _sanitize 清洗
        df.loc[1, "open"] = float("inf")    # 原生 Inf：验证 _sanitize 清洗
    return df


def _w4b_fake_fin_tables():
    """income/balance/cash 三表（行=报告期、列=科目），2 期，喂真实 _w4b_* 纯逻辑。"""
    import pandas as pd
    inc = pd.DataFrame({
        "报告期": ["2026-09-30", "2025-09-30"],
        "营业总收入": [1.2e11, 1.0e11],
        "净利润": [6.0e10, 5.0e10],
        "营业成本": [1.0e10, 0.9e10],
        "基本每股收益": [47.0, 39.0],
        "扣除非经常性损益后的净利润": [5.8e10, 4.8e10],
    })
    bal = pd.DataFrame({
        "报告期": ["2026-09-30", "2025-09-30"],
        "资产总计": [2.5e11, 2.2e11],
        "负债合计": [5.0e10, 4.5e10],
        "所有者权益合计": [2.0e11, 1.75e11],
        "流动资产合计": [1.5e11, 1.3e11],
        "流动负债合计": [4.5e10, 4.0e10],
        "实收资本(或股本)": [1.256e9, 1.256e9],
    })
    cash = pd.DataFrame({
        "报告期": ["2026-09-30", "2025-09-30"],
        "经营活动产生的现金流量净额": [6.5e10, 5.5e10],
        "每股经营活动产生的现金流量净额": [51.7, 43.8],
    })
    return {"income": inc, "balance": bal, "cash": cash}


def _patch_w4b_all_ok(monkeypatch):
    """五源齐备（basic/spot/kline/income/balance/cash），用于 ok 信封真值断言。"""
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: _w4b_fake_basic())
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: _w4b_fake_spot())
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": _w4b_fake_kline())
    _tables = _w4b_fake_fin_tables()
    monkeypatch.setattr(rr, "_w4b_financial", lambda code, rt: _tables.get(rt))


def _patch_w4b_all_fail(monkeypatch):
    """所有源失败（返回 None）—— 诚实降级态：字段 null / rows [] / date null / status ok。"""
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: None)
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: None)
    monkeypatch.setattr(rr, "_w4b_kline", lambda code, period="daily": None)
    monkeypatch.setattr(rr, "_w4b_financial", lambda code, rt: None)


# ───────────── 端点 1：GET /api/v2/read/fundamentals ─────────────

def test_fundamentals_requires_token(client):
    """无 token -> 401（鉴权闸门先于参数校验与取数，零网络）。"""
    assert client.get("/api/v2/read/fundamentals?code=600519").status_code == 401


def test_fundamentals_ok_envelope(client, token, monkeypatch):
    """五源齐备 -> 标准 ok 信封 + 契约字段齐全 + perf 9 字段真值 + 双日期独立。"""
    _patch_w4b_all_ok(monkeypatch)
    resp = client.get("/api/v2/read/fundamentals?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("code", "name", "industry", "price", "pe_ttm", "market_cap",
              "spot_date", "kline_date", "perf", "priceDomain", "date", "note"):
        assert k in d, f"data 缺字段 {k}: {d}"
    assert d["code"] == "600519" and d["name"] == "贵州茅台" and d["industry"] == "白酒"
    assert d["price"] == 1688.0 and d["pe_ttm"] == 28.1 and d["market_cap"] == 21000.0
    assert d["priceDomain"] == "market" and d["note"] == _W4B_OK_NOTE
    assert d["spot_date"] == "2026-11-07" and d["kline_date"] == "2026-11-07"
    assert d["date"] == d["spot_date"]  # date 明确取 spot_date
    assert set(d["perf"].keys()) == {
        "revenue_yi", "revenue_yoy", "net_profit_yi", "profit_yoy",
        "gross_margin", "roe", "alr", "current_ratio", "equity_ratio",
    }
    assert d["perf"]["revenue_yi"] == 1200.0  # 1.2e11 / 1e8，真实计算非编造
    assert d["perf"]["net_profit_yi"] == 600.0
    assert d["perf"]["roe"] == 30.0 and d["perf"]["alr"] == 20.0


def test_fundamentals_invalid_and_missing_code(client, token):
    """非法 / 缺失 code -> 400 invalid_param（校验先于取数，零网络）。"""
    for qs in ("?code=abc", "?code=60051", "?code=6005199", "?code=60051x", ""):
        resp = client.get(f"/api/v2/read/fundamentals{qs}", headers=_auth(token))
        assert resp.status_code == 400, f"{qs}: {resp.status_code}"
        obj = resp.get_json()
        assert obj["status"] == "error" and obj["code"] == "invalid_param", obj


def test_fundamentals_source_exception_honest_degradation(client, token, monkeypatch):
    """某源抛异常 -> 对应字段 null 且 status 仍 ok（fetch_many._safe 吞异常，绝不 500）。"""
    _patch_w4b_all_ok(monkeypatch)

    def boom(code):
        raise RuntimeError("get_fundamentals timeout")

    monkeypatch.setattr(rr, "_w4b_basic", boom)
    resp = client.get("/api/v2/read/fundamentals?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert d["name"] is None and d["industry"] is None and d["price"] is None
    assert d["pe_ttm"] is None and d["market_cap"] is None
    # 其余源不受影响：spot_date / perf 仍有真值（逐字段独立降级）
    assert d["spot_date"] == "2026-11-07" and d["perf"]["revenue_yi"] == 1200.0


def test_fundamentals_all_sources_fail_honest(client, token, monkeypatch):
    """全源失败 -> status 仍 ok，所有字段 null、perf 全 None、date null（不用 now()）。"""
    _patch_w4b_all_fail(monkeypatch)
    resp = client.get("/api/v2/read/fundamentals?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("name", "industry", "price", "pe_ttm", "market_cap",
              "spot_date", "kline_date", "date"):
        assert d[k] is None, f"{k} 必须 null，禁止 now()/补 0 兜底: {d[k]}"
    assert all(v is None for v in d["perf"].values()), d["perf"]
    assert d["priceDomain"] == "market"  # 常量字段保留


def test_fundamentals_nan_inf_sanitized(client, token, monkeypatch):
    """basic 含 NaN/Inf -> 响应清洗为 null，body 不含裸 NaN/Infinity 字面量。"""
    _patch_w4b_all_ok(monkeypatch)
    bad = _w4b_fake_basic()
    bad["price"] = float("nan")
    bad["pe_ttm"] = float("inf")
    monkeypatch.setattr(rr, "_w4b_basic", lambda code: bad)
    resp = client.get("/api/v2/read/fundamentals?code=600519", headers=_auth(token))
    body = resp.get_data(as_text=True)
    assert "NaN" not in body and "Infinity" not in body, body[:300]
    d = resp.get_json()["data"]
    assert d["price"] is None and d["pe_ttm"] is None, d


def test_fundamentals_date_never_now_and_spot_independent(client, token, monkeypatch):
    """spot 失败而 kline 成功：date 必须 null（不用 now()、不用 kline_date 顶替），
    kline_date 仍独立有值 —— 验证契约「两者独立、禁止互相兜底」。"""
    _patch_w4b_all_ok(monkeypatch)
    monkeypatch.setattr(rr, "_w4b_spot", lambda code: None)  # spot 取数失败
    d = client.get("/api/v2/read/fundamentals?code=600519",
                   headers=_auth(token)).get_json()["data"]
    assert d["spot_date"] is None and d["date"] is None, d
    assert d["kline_date"] == "2026-11-07", "kline_date 不受 spot 失败影响，但不得顶替 date"
    assert d["perf"]["revenue_yi"] == 1200.0  # 财务源仍正常


# ───────────── 端点 2：GET /api/v2/read/financials ─────────────

def test_financials_requires_token(client):
    assert client.get("/api/v2/read/financials?code=600519").status_code == 401


def test_financials_ok_envelope(client, token, monkeypatch):
    """三表齐备 -> ok 信封 + rows 真实列名 + 倒序 + date=最新报告期 + report 默认 income。"""
    _patch_w4b_all_ok(monkeypatch)
    resp = client.get("/api/v2/read/financials?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("code", "report", "rows", "date", "note"):
        assert k in d, f"data 缺字段 {k}: {d}"
    assert d["code"] == "600519" and d["report"] == "income" and d["note"] == _W4B_OK_NOTE
    assert isinstance(d["rows"], list) and len(d["rows"]) == 2, d["rows"]
    r0 = d["rows"][0]
    for col in ("报告期", "标签", "营业总收入", "归母净利润", "扣非净利润", "每股收益",
                "净资产收益率", "销售净利率", "销售毛利率", "资产负债率", "每股经营现金流"):
        assert col in r0, f"rows 缺契约列 {col}: {list(r0.keys())}"
    assert any(c.endswith("_同比") for c in r0) and any(c.endswith("_环比") for c in r0)
    assert d["date"] == "2026-09-30" == r0["报告期"]  # 权威数据日 = 最新报告期
    assert r0["营业总收入"] == 1200.0  # 真实计算，非编造演示行


def test_financials_invalid_code_and_report(client, token):
    """非法 / 缺 code、非法 report -> 400 invalid_param（校验先于取数）。"""
    for qs in ("?code=abc", "?code=60051", ""):
        resp = client.get(f"/api/v2/read/financials{qs}", headers=_auth(token))
        assert resp.status_code == 400, f"{qs}: {resp.status_code}"
        assert resp.get_json()["code"] == "invalid_param", qs
    resp = client.get("/api/v2/read/financials?code=600519&report=foo", headers=_auth(token))
    assert resp.status_code == 400 and resp.get_json()["code"] == "invalid_param", resp.get_json()


def test_financials_report_variants_echo(client, token, monkeypatch):
    """report ∈{income,balance,cash} 均合法并原样回显（零网络）。"""
    _patch_w4b_all_ok(monkeypatch)
    for rep in ("income", "balance", "cash", "INCOME"):
        resp = client.get(f"/api/v2/read/financials?code=600519&report={rep}",
                          headers=_auth(token))
        assert resp.status_code == 200, f"{rep}: {resp.status_code}"
        d = resp.get_json()["data"]
        assert d["report"] == rep.lower(), d


def test_financials_partial_source_degrades(client, token, monkeypatch):
    """balance/cash 失败 -> 跨表衍生列为 null，income 相关列仍有值，status ok（不补 0）。"""
    _patch_w4b_all_ok(monkeypatch)
    _tables = _w4b_fake_fin_tables()
    monkeypatch.setattr(rr, "_w4b_financial",
                        lambda code, rt: _tables.get(rt) if rt == "income" else None)
    obj = client.get("/api/v2/read/financials?code=600519",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    rows = obj["data"]["rows"]
    assert rows, "income 在 -> 仍应产出 rows（按报告期）"
    assert rows[0]["营业总收入"] == 1200.0, rows[0]
    assert rows[0]["资产负债率"] is None, "balance 缺失 -> 资产负债率必须 null，禁止补 0"


def test_financials_all_sources_fail_honest(client, token, monkeypatch):
    """三表全失败 -> rows=[]、date=null、status ok（不造演示行、不用 now()）。"""
    _patch_w4b_all_fail(monkeypatch)
    obj = client.get("/api/v2/read/financials?code=600519",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    assert obj["data"]["rows"] == [] and obj["data"]["date"] is None, obj["data"]


def test_financials_nan_inf_sanitized(client, token, monkeypatch):
    """rows 含原生 NaN/Inf -> _sanitize 洗成 null，body 不含裸字面量。"""
    _patch_w4b_all_ok(monkeypatch)
    monkeypatch.setattr(rr, "_w4b_financial_rows", lambda inc, bal, cash: [
        {"报告期": "2026-09-30", "营业总收入": float("nan"),
         "归母净利润": float("inf"), "资产负债率": 20.0},
    ])
    resp = client.get("/api/v2/read/financials?code=600519", headers=_auth(token))
    body = resp.get_data(as_text=True)
    assert "NaN" not in body and "Infinity" not in body, body[:300]
    d = resp.get_json()["data"]
    assert d["rows"][0]["营业总收入"] is None and d["rows"][0]["归母净利润"] is None, d
    assert d["date"] == "2026-09-30", d


def test_financials_limit_truncates(client, token, monkeypatch):
    """limit=1 -> 仅最新 1 行（倒序截断），date 仍为最新报告期。"""
    _patch_w4b_all_ok(monkeypatch)
    d = client.get("/api/v2/read/financials?code=600519&limit=1",
                   headers=_auth(token)).get_json()["data"]
    assert len(d["rows"]) == 1 and d["rows"][0]["报告期"] == "2026-09-30", d
    assert d["date"] == "2026-09-30", d


# ───────────── 端点 3：GET /api/v2/read/stock-kline ─────────────

def test_stock_kline_requires_token(client):
    assert client.get("/api/v2/read/stock-kline?code=600519").status_code == 401


def test_stock_kline_ok_envelope(client, token, monkeypatch):
    """kline 齐备 -> ok 信封 + 英文列 + rows 按 date 升序 + date=末根[:10]。"""
    _patch_w4b_all_ok(monkeypatch)
    resp = client.get("/api/v2/read/stock-kline?code=600519", headers=_auth(token))
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    for k in ("code", "period", "rows", "date", "note"):
        assert k in d, f"data 缺字段 {k}: {d}"
    assert d["code"] == "600519" and d["period"] == "daily" and d["note"] == _W4B_OK_NOTE
    assert len(d["rows"]) == 3, d["rows"]
    for col in ("date", "open", "close", "high", "low", "volume"):
        assert col in d["rows"][0], f"rows 缺英文列 {col}: {list(d['rows'][0].keys())}"
    assert [r["date"] for r in d["rows"]] == ["2026-11-05", "2026-11-06", "2026-11-07"]
    assert d["date"] == "2026-11-07", d  # 权威数据日 = 最后一根


def test_stock_kline_invalid_code_and_period(client, token):
    """非法 / 缺 code、非法 period -> 400 invalid_param。"""
    for qs in ("?code=abc", "?code=60051", ""):
        resp = client.get(f"/api/v2/read/stock-kline{qs}", headers=_auth(token))
        assert resp.status_code == 400, f"{qs}: {resp.status_code}"
        assert resp.get_json()["code"] == "invalid_param", qs
    resp = client.get("/api/v2/read/stock-kline?code=600519&period=tick", headers=_auth(token))
    assert resp.status_code == 400 and resp.get_json()["code"] == "invalid_param", resp.get_json()


def test_stock_kline_source_fail_honest(client, token, monkeypatch):
    """kline 失败 -> rows=[]、date=null、status ok（不用 now()、不 500）。"""
    _patch_w4b_all_fail(monkeypatch)
    obj = client.get("/api/v2/read/stock-kline?code=600519",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    assert obj["data"]["rows"] == [] and obj["data"]["date"] is None, obj["data"]


def test_stock_kline_nan_inf_sanitized(client, token, monkeypatch):
    """端点存在主因：kline 含原生 NaN/Inf -> _sanitize 洗成 null，body 无裸字面量
    （/api/kline 直接 df.to_dict 有 NaN 裸奔风险，本端点必须修复）。"""
    _patch_w4b_all_ok(monkeypatch)
    monkeypatch.setattr(rr, "_w4b_kline",
                        lambda code, period="daily": _w4b_fake_kline(with_bad=True))
    resp = client.get("/api/v2/read/stock-kline?code=600519", headers=_auth(token))
    body = resp.get_data(as_text=True)
    assert "NaN" not in body and "Infinity" not in body, body[:300]
    rows = resp.get_json()["data"]["rows"]
    mid = next(r for r in rows if r["date"] == "2026-11-06")
    assert mid["close"] is None and mid["open"] is None, mid


def test_stock_kline_limit_ascending(client, token, monkeypatch):
    """limit=2 -> tail(2) 取最近 2 根且仍升序，date 仍为末根。"""
    _patch_w4b_all_ok(monkeypatch)
    d = client.get("/api/v2/read/stock-kline?code=600519&limit=2",
                   headers=_auth(token)).get_json()["data"]
    assert [r["date"] for r in d["rows"]] == ["2026-11-06", "2026-11-07"], d["rows"]
    assert d["date"] == "2026-11-07", d


def test_stock_kline_date_never_now(client, token, monkeypatch):
    """全源失败：date 必须 null，绝不拿 datetime.now() 兜底。"""
    _patch_w4b_all_fail(monkeypatch)
    d = client.get("/api/v2/read/stock-kline?code=600519",
                   headers=_auth(token)).get_json()["data"]
    assert d["date"] is None and d["rows"] == [], d


# ───────────── 并发超时降级（照 six-dim parallel_timeout_degrades）─────────────

def test_w4b_parallel_timeout_degrades(client, token, monkeypatch):
    """fetch_many 整批超时/未完成项（预填 None）-> 三端点均诚实降级、status ok、
    date=null、绝不 500 / 补 0 / now() 兜底。"""
    def fake_fetch_many(tasks, max_workers=None, timeout=None):
        return {key: None for key, _ in tasks}  # 全部超时未完成

    monkeypatch.setattr("modules.fetch_parallel.fetch_many", fake_fetch_many)

    obj = client.get("/api/v2/read/fundamentals?code=600519",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    assert obj["data"]["date"] is None and obj["data"]["spot_date"] is None, obj["data"]
    assert all(v is None for v in obj["data"]["perf"].values()), obj["data"]["perf"]

    obj = client.get("/api/v2/read/financials?code=600519",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"]["rows"] == [] and obj["data"]["date"] is None, obj

    obj = client.get("/api/v2/read/stock-kline?code=600519",
                     headers=_auth(token)).get_json()
    assert obj["status"] == "ok" and obj["data"]["rows"] == [] and obj["data"]["date"] is None, obj


# ───────────── 磁盘 openapi.json 覆盖（照 test_six_dim_in_frontend_spec_file）─────────────

def test_w4b_in_frontend_spec_file():
    """磁盘 frontend-v2/spec/openapi.json 必须覆盖三个新 path 且标注 BearerAuth。"""
    path = os.path.join(PROJECT_ROOT, "frontend-v2", "spec", "openapi.json")
    with open(path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    for base in ("/api/v2/read/fundamentals", "/api/v2/read/financials",
                 "/api/v2/read/stock-kline"):
        node = spec["paths"].get(base)
        assert node is not None and "get" in node, f"spec 缺 {base}"
        assert node["get"].get("security") == [{"BearerAuth": []}], f"{base} 未标注鉴权"


def test_factor_analysis_endpoint(client, token, monkeypatch):
    """factor-analysis：有效标的≥3 -> 200 + status=ok（含 ic_summary/layered_cum/long_short_cum）；
    有效标的<3 -> status=error（insufficient_data），诚实不编造、不补零。"""
    import pandas as pd
    import modules.page_utils as pu

    def _fake_df(code=None):
        n = 61
        idx = pd.date_range("2026-01-01", periods=n, freq="D")
        # 每只标的斜率不同 -> 截面上有差异（rank_ic 要求截面 nunique≥2，否则为 NaN）。
        slope = 1 + ((int(str(code or "0")[-3:]) % 50) / 100.0)
        close = [100 + slope * (i + (i % 7)) for i in range(n)]
        return pd.DataFrame({"日期": idx, "收盘": close})

    monkeypatch.setattr(pu, "hist_cached", _fake_df)

    # 1) 充分数据：3 只标的 + n_layers=3（≤标的数，可分层）-> ok 信封 + 三层图表数据
    resp = client.get(
        "/api/v2/read/factor-analysis?codes=600519,000001,300750&days=60&factor=momentum&n_layers=3&forward=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ok", body
    d = body["data"]
    assert d["factor"] == "momentum" and d["n_layers"] == 3
    assert isinstance(d["ic_summary"], dict) and (d["ic_summary"].get("n") or 0) >= 1
    assert len(d["layered_cum"]) >= 1
    assert len(d["long_short_cum"]) >= 1
    # 诚实红线：数值缺失应为 null，绝不允许补 0（ic_summary.n 为真实样本数，非 0）
    assert d["ic_summary"]["n"] != 0

    # 2) 不足 3 只标的 -> 诚实 error，不给出因子结论
    resp2 = client.get(
        "/api/v2/read/factor-analysis?codes=600519&days=60",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2["status"] == "error"
    assert body2["code"] == "insufficient_data"


def test_backtest_endpoint(client, token, monkeypatch):
    """backtest：有效取数 -> 200 + status=ok（含 summary/equity_curve/trades）；
    取数为空 -> status=error（insufficient_data），诚实不编造、不补零；
    ticker 非法 -> 400 invalid_param。"""
    import pandas as pd
    from modules.backtest import Backtester
    from modules.backtest_result import BacktestResult

    n = 30
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    # 单调上行 + 轻微波动 -> 有正收益、有回撤，足以撑起 summary 与曲线。
    close = [100 + i * 1.5 + (i % 3) for i in range(n)]
    df = pd.DataFrame({
        "date": idx,
        "close": close,
        "position": [1] * n,
        "cash": [0.0] * n,
        "total_asset": [100000 + i * 150.0 for i in range(n)],
        "cumulative_return": [i * 0.15 for i in range(n)],
        "daily_return": [0.15] * n,
        "drawdown": [-0.5 * (i % 5) for i in range(n)],
    })
    trades = [{
        "entry_date": idx[0], "exit_date": idx[5],
        "entry_price": 100.0, "exit_price": 108.0,
        "profit_pct": 7.5, "exit_reason": "止盈", "bars_held": 5,
    }]

    def _fake_run(ticker, start, end, strategy="multi_factor", **kw):
        return BacktestResult(ticker, strategy, df, 100000, trades)

    monkeypatch.setattr(Backtester, "run", staticmethod(_fake_run))

    # 1) 充分数据 -> ok 信封 + summary/曲线/交易
    resp = client.get(
        "/api/v2/read/backtest?ticker=600519&start=2024-01-01&end=2024-12-31&strategy=multi_factor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ok", body
    d = body["data"]
    assert d["ticker"] == "600519" and d["strategy"] == "multi_factor"
    assert d["total_return_pct"] is not None and d["total_return_pct"] != 0
    assert d["sharpe_ratio"] is not None
    assert len(d["equity_curve"]) == n
    assert d["equity_curve"][-1]["date"] == str(idx[-1])[:10]
    assert len(d["trades"]) == 1
    assert d["trades"][0]["exit_reason"] == "止盈"

    # 2) 取数为空（df.empty）-> 诚实 error
    def _fake_run_empty(ticker, start, end, strategy="multi_factor", **kw):
        return BacktestResult(ticker, strategy, pd.DataFrame(), 100000, [])

    monkeypatch.setattr(Backtester, "run", staticmethod(_fake_run_empty))
    resp2 = client.get(
        "/api/v2/read/backtest?ticker=600519&start=2024-01-01&end=2024-12-31",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2["status"] == "error"
    assert body2["code"] == "insufficient_data"

    # 3) ticker 非法 -> 400 invalid_param
    resp3 = client.get(
        "/api/v2/read/backtest?ticker=abc&start=2024-01-01&end=2024-12-31",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 400
    assert resp3.get_json()["code"] == "invalid_param"


def test_market_panorama_endpoint(client, token, monkeypatch):
    """market-panorama（56 状态机 + 57 全景共享）：regime 可用 -> 200 + status=ok
    （含 regime/slavester_latest/shepherd_series/shepherd_unavailable）；
    regime 不可用 -> status=error（insufficient_data），诚实不编造。"""
    import pandas as pd
    from modules import market_regime as mr
    from modules import shepherd_history as sh

    state_order = ["暴涨", "普涨", "结构牛", "震荡", "恐慌", "暴跌"]
    fake_report = {
        "available": True,
        "data": {"rows": 100, "start": "2020-01-01", "end": "2026-08-21"},
        "latest": {"date": "2026-08-21", "state": "震荡", "confidence": 0.42,
                   "metrics": {"red_ratio": 51.3, "limit_up": 40, "limit_down": 8}},
        "state_distribution": {s: 10 for s in state_order},
        "transition_matrix": {a: {b: 1 / len(state_order) for b in state_order} for a in state_order},
        "analogs": [
            {"date": "2023-05-04", "distance": 1.2, "state": "普涨",
             "metrics": {"red_ratio": 62.0, "limit_up": 55, "limit_down": 3},
             "forward": {"d5": {"avg_red": 55.0, "up_frac": 0.6, "median_delta": 1.1}}},
        ],
    }
    idx = pd.date_range("2026-08-01", periods=5, freq="B")
    fake_df = pd.DataFrame({
        "date": idx, "red_ratio": [50.0, 51.0, 52.0, 49.0, 51.3],
        "limit_up": [30, 35, 40, 28, 40], "limit_down": [10, 8, 9, 12, 8],
        "connect_hl": [5, 6, 7, 4, 6], "zt_fail_ratio": [0.2, 0.18, 0.15, 0.22, 0.19],
    })
    fake_meta = {"available": ["red_ratio", "limit_up"], "unavailable": [("zt_fail_ratio", "该日数据源缺失")]}

    monkeypatch.setattr(mr, "regime_report", lambda k=8: fake_report)
    monkeypatch.setattr(sh, "get_shepherd_indicators", lambda days=60: (fake_df, fake_meta))

    resp = client.get(
        "/api/v2/read/market-panorama?k=8",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ok", body
    d = body["data"]
    assert d["regime"]["latest"]["state"] == "震荡"
    assert d["regime"]["state_distribution"]["震荡"] == 10
    assert len(d["regime"]["analogs"]) == 1
    assert d["shepherd_latest"].get("red_ratio") == 51.3
    assert len(d["shepherd_series"]) == 5
    assert d["shepherd_unavailable"] == [["zt_fail_ratio", "该日数据源缺失"]]
    assert d["date"] == "2026-08-21"

    # 2) regime 不可用 -> 诚实 error
    monkeypatch.setattr(mr, "regime_report", lambda k=8: {"available": False, "reason": "广度历史为空（数据缺失）"})
    resp2 = client.get(
        "/api/v2/read/market-panorama?k=8",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2["status"] == "error"
    assert body2["code"] == "insufficient_data"


def test_portfolio_endpoint(client, token, monkeypatch):
    """portfolio（45 持仓中心）：持仓充分 -> 200 + status=ok（含 summary/positions/
    attribution/weights/curve）；持仓为空 -> status=error（insufficient_data）；
    计算异常 -> compute_error（诚实降级，不 500）。"""
    import pandas as pd
    from modules import portfolio as pf_mod

    pnl_df = pd.DataFrame([
        {"ticker": "600519", "name": "贵州茅台", "buy_date": "2026-01-02", "buy_price": 1700.0,
         "shares": 100, "remaining_shares": 100, "cost": 170000.0, "current_price": 1800.0,
         "market_value": 180000.0, "realized_pnl": 0.0, "pnl": 10000.0, "pnl_pct": 5.88},
        {"ticker": "000001", "name": "平安银行", "buy_date": "2026-01-03", "buy_price": 12.0,
         "shares": 1000, "remaining_shares": 500, "cost": 6000.0, "current_price": 11.0,
         "market_value": 5500.0, "realized_pnl": 0.0, "pnl": -500.0, "pnl_pct": -8.33},
    ])
    attr_df = pd.DataFrame([
        {"ticker": "600519", "name": "贵州茅台", "pnl": 10000.0, "pnl_pct": 5.88, "contribution": 104.17},
        {"ticker": "000001", "name": "平安银行", "pnl": -500.0, "pnl_pct": -8.33, "contribution": -4.17},
    ])
    summary = {"total_cost": 176000.0, "total_market_value": 185500.0, "total_pnl": 9500.0,
               "total_pnl_pct": 5.4, "position_count": 2}

    class _Fetcher:
        @staticmethod
        def get_daily(symbol, start=None, end=None):
            n = 20
            idx = pd.date_range("2026-01-01", periods=n, freq="B")
            return pd.DataFrame({"close": [100.0 + i for i in range(n)]}, index=idx)

    class _FakePM:
        fetcher = _Fetcher()

        def calc_pnl(self):
            return pnl_df

        def summary(self):
            return summary

        def pnl_attribution(self):
            return attr_df

    monkeypatch.setattr(pf_mod, "PortfolioManager", _FakePM)

    # 1) 充分持仓 -> ok 信封 + 全字段
    resp = client.get(
        "/api/v2/read/portfolio",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ok", body
    d = body["data"]
    assert d["summary"]["position_count"] == 2
    assert len(d["positions"]) == 2
    assert d["positions"][0]["current_price"] == 1800.0
    # 市值占比之和应≈100（此处 180000/185500*100）
    assert abs(sum(w["weight_pct"] for w in d["weights"]) - 100.0) < 1e-6
    assert len(d["attribution"]) == 2
    # 净值曲线尽力而为：两标的同序列 -> 公共日期≥2
    assert d["curve_available"] is True
    assert len(d["curve"]) >= 2
    assert d["curve"][0]["portfolio"] is not None

    # 2) 持仓为空 -> 诚实 insufficient_data
    class _FakeEmpty:
        fetcher = _Fetcher()

        def calc_pnl(self):
            return pd.DataFrame()

        def summary(self):
            return {"total_cost": 0, "total_market_value": 0, "total_pnl": 0,
                    "total_pnl_pct": 0, "position_count": 0}

        def pnl_attribution(self):
            return pd.DataFrame()

    monkeypatch.setattr(pf_mod, "PortfolioManager", _FakeEmpty)
    resp2 = client.get(
        "/api/v2/read/portfolio",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2["status"] == "error"
    assert body2["code"] == "insufficient_data"

    # 3) 计算异常 -> compute_error（不 500）
    class _FakeBoom:
        fetcher = _Fetcher()

        def calc_pnl(self):
            raise RuntimeError("boom")

        def summary(self):
            return {}

        def pnl_attribution(self):
            return pd.DataFrame()

    monkeypatch.setattr(pf_mod, "PortfolioManager", _FakeBoom)
    resp3 = client.get(
        "/api/v2/read/portfolio",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200
    body3 = resp3.get_json()
    assert body3["status"] == "error"
    assert body3["code"] == "compute_error"


def test_fund_flow_endpoint(client, token, monkeypatch):
    """fund-flow（35 资金流向）：四块取数充分 -> 200 + status=ok，各块 available=True；
    取数为空 -> 该块 available=False（诚实降级，不 500、不补 0）；异常 -> 仍 200（不 500）。"""
    import pandas as pd
    from modules import fundflow as ff_mod
    from modules import margin_trading as mt_mod

    nb = {
        "boards": [{"板块": "沪股通", "资金方向": "北向", "成交净买额": 1.2e8, "资金净流入": 3.4e8,
                    "上涨数": 300, "下跌数": 150, "指数涨跌幅": 1.2}],
        "trade_date": "2026-11-08", "total_inflow": 5.0e8, "sh_inflow": 3.0e8, "sz_inflow": 2.0e8,
        "northbound_net_available": True, "last_net_buy": 9.9e9, "last_net_buy_date": "2024-08-15",
        "cumulative": 1.8e12, "cumulative_date": "2024-08-15",
    }
    ind = pd.DataFrame([
        {"行业": "半导体", "涨跌幅": 2.5, "流入资金": 5.0e10, "流出资金": 4.0e10, "净额": 1.0e10,
         "领涨股": "中芯国际", "领涨股涨跌幅": 5.1},
        {"行业": "银行", "涨跌幅": -1.1, "流入资金": 2.0e10, "流出资金": 2.5e10, "净额": -5.0e9,
         "领涨股": "招商银行", "领涨股涨跌幅": -0.8},
    ])
    mk = pd.DataFrame([
        {"日期": "2026-11-06", "上证-涨跌幅": 0.5, "主力净流入-净额": 1.2e10, "主力净流入-净占比": 3.1,
         "超大单净流入-净额": 6.0e9, "大单净流入-净额": 6.0e9, "中单净流入-净额": -5.0e9},
        {"日期": "2026-11-07", "上证-涨跌幅": -0.3, "主力净流入-净额": -8.0e9, "主力净流入-净占比": -2.2,
         "超大单净流入-净额": -4.0e9, "大单净流入-净额": -4.0e9, "中单净流入-净额": 3.0e9},
    ])
    mg = pd.DataFrame([
        {"日期": "2026-11-06", "sh_rzmr": 3.0e10, "sz_rzmr": 2.0e10, "total_rzmr": 5.0e10,
         "sh_rzye": 7.0e11, "sz_rzye": 6.0e11, "total_rzye": 1.3e12,
         "sh000001": 3300.0, "sz399001": 11000.0, "sz399006": 2300.0},
    ])
    mg_summary = {
        "date": "2026-11-06", "total_rzmr_yi": 500.0, "total_rzye_yi": 13000.0, "sh_rzmr_yi": 300.0,
        "sz_rzmr_yi": 200.0, "rzmr_change_yi": 12.5, "rzye_change_yi": -8.3,
        "rzmr_change_pct": 2.5, "rzye_change_pct": -0.6,
    }

    monkeypatch.setattr(ff_mod, "get_northbound_fund_flow", lambda: nb)
    monkeypatch.setattr(ff_mod, "get_industry_fund_flow", lambda: ind)
    monkeypatch.setattr(ff_mod, "get_market_fund_flow", lambda days=30: mk)
    monkeypatch.setattr(mt_mod, "get_margin_trading_data", lambda days=180: mg)
    monkeypatch.setattr(mt_mod, "get_latest_margin_summary", lambda: mg_summary)

    # 1) 充分取数 -> ok 信封 + 四块均可用
    resp = client.get("/api/v2/read/fund-flow", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ok", body
    d = body["data"]
    assert d["northbound"]["available"] is True
    assert d["northbound"]["total_inflow"] == 5.0  # 5.0e8 元 -> 5.0 亿
    assert d["northbound"]["boards"][0]["net_inflow"] == 3.4  # 3.4e8 -> 3.4 亿
    assert d["northbound"]["last_net_buy"] == 99.0  # 9.9e9 -> 99.0 亿
    assert d["industry"]["available"] is True
    assert len(d["industry"]["rows"]) == 2
    assert d["industry"]["rows"][0]["net"] == 100.0  # 1.0e10 -> 100.0 亿
    assert d["market"]["available"] is True
    assert len(d["market"]["rows"]) == 2
    assert d["market"]["rows"][0]["main_net"] == 120.0  # 1.2e10 -> 120.0 亿
    assert d["margin"]["available"] is True
    assert d["margin"]["rows"][0]["total_rzmr_yi"] == 500.0  # 5.0e10 -> 500.0 亿
    assert d["margin"]["latest"]["total_rzye_yi"] == 13000.0
    assert d["unavailable"] == []

    # 2) 取数为空 -> 各块 available=False（诚实降级，不 500、不补 0）
    monkeypatch.setattr(ff_mod, "get_northbound_fund_flow", lambda: {})
    monkeypatch.setattr(ff_mod, "get_industry_fund_flow", lambda: pd.DataFrame())
    monkeypatch.setattr(ff_mod, "get_market_fund_flow", lambda days=30: pd.DataFrame())
    monkeypatch.setattr(mt_mod, "get_margin_trading_data", lambda days=180: pd.DataFrame())
    monkeypatch.setattr(mt_mod, "get_latest_margin_summary", lambda: {})
    resp2 = client.get("/api/v2/read/fund-flow", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2["status"] == "ok"  # 仍 200，分块降级而非整页 error
    d2 = body2["data"]
    assert d2["northbound"]["available"] is False
    assert d2["industry"]["available"] is False
    assert d2["market"]["available"] is False
    assert d2["margin"]["available"] is False

    # 3) 取数抛异常 -> 仍 200（不 500），各块降级
    def _boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(ff_mod, "get_northbound_fund_flow", _boom)
    monkeypatch.setattr(ff_mod, "get_industry_fund_flow", _boom)
    monkeypatch.setattr(ff_mod, "get_market_fund_flow", _boom)
    monkeypatch.setattr(mt_mod, "get_margin_trading_data", _boom)
    monkeypatch.setattr(mt_mod, "get_latest_margin_summary", _boom)
    resp3 = client.get("/api/v2/read/fund-flow", headers={"Authorization": f"Bearer {token}"})
    assert resp3.status_code == 200
    body3 = resp3.get_json()
    assert body3["status"] == "ok"
    assert body3["data"]["northbound"]["available"] is False


def test_trading_account_endpoint(client, token, tmp_path, monkeypatch):
    """trading-account（43 实盘交易只读概览）：聚合本地模拟账本；无账本 → 诚实空态。

    只读、不暴露任何写接口；缺账本 available=False + 空数据（不 500、不补 0）。
    """
    # 写一个自洽的本地模拟账本到临时目录，并 monkeypatch _DATA_DIR 指向它
    import backend.api.read_routes as rr
    ledger = {
        "init_cash": 1000000.0, "cash": 870944.0,
        "positions": {"600519": {"name": "贵州茅台", "qty": 100, "avg_cost": 1290.56}},
        "trades": [
            {"time": "2026-09-09 12:10", "code": "600519", "name": "贵州茅台",
             "side": "买", "price": 1290.56, "qty": 100, "amount": 129056.0},
        ],
        "equity": [["2026-09-09 12:10", 1000000.0]],
    }
    ledger_path = tmp_path / "paper_admin.json"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rr, "_DATA_DIR", tmp_path.resolve())

    # 1) 充分账本 -> ok 信封 + account/positions/orders 三块齐备
    resp = client.get("/api/v2/read/trading-account?user=admin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ok", body
    d = body["data"]
    assert d["account"]["available"] is True
    assert d["account"]["broker_type"] == "sim"
    assert d["account"]["mode"] == "模拟"
    assert d["account"]["cash"] == 870944.0
    # 持仓成本 = 100 * 1290.56 = 129056.0；总资产 = cash + 持仓成本
    assert d["positions"][0]["code"] == "600519"
    assert d["positions"][0]["cost_basis"] == pytest.approx(129056.0)
    assert d["account"]["position_cost"] == pytest.approx(129056.0)
    assert d["account"]["total_assets"] == pytest.approx(870944.0 + 129056.0)
    assert d["orders"][0]["side"] == "买"
    assert d["orders"][0]["amount"] == pytest.approx(129056.0)

    # 2) 无账本（目录里没有该 user）-> 仍 200、available=False + 空数据（诚实降级）
    resp2 = client.get("/api/v2/read/trading-account?user=nobody", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2["status"] == "ok"
    assert body2["data"]["account"]["available"] is False
    assert body2["data"]["positions"] == []
    assert body2["data"]["orders"] == []

    # 3) user 非法 -> 400
    resp3 = client.get("/api/v2/read/trading-account?user=../etc", headers={"Authorization": f"Bearer {token}"})
    assert resp3.status_code == 400


def test_macro_data_endpoint(client, token, monkeypatch):
    """macro-data（84 宏观数据）：fetch_all 聚合多指标，逐指标独立降级（None）；
    regime 取不到→None；整体异常→仍 200、unavailable=['macro_fetch_failed']。"""
    from modules import macro_data as md_mod

    sample = {
        "pmi": {"key": "pmi", "name": "制造业 PMI", "unit": "%", "freq": "月",
                "source": "国家统计局", "region": "国内", "desc": "荣枯线 50",
                "value": 51.2, "prev": 50.8, "change": 0.4, "date": "2026-11-01",
                "stale": False, "from_cache": False},
        "cpi": None,  # 取不到，诚实降级（不补 0）
        "dxy": {"key": "dxy", "name": "美元指数 DXY", "unit": "点", "freq": "日",
                "source": "ICE", "region": "全球", "desc": "强美元",
                "value": 102.3, "prev": 101.8, "change": 0.5, "date": "2026-11-08",
                "stale": False, "from_cache": False},
    }
    regime = {"score": 62, "sub": {"dxy": 55.0, "us_treasury_10y": 60.0},
              "parts": {"dxy": 102.3, "us_treasury_10y": 4.1},
              "yield_curve": None, "cn_us_spread": None,
              "dates": {"dxy": "2026-11-08", "us_treasury_10y": "2026-11-08"}}

    # 1) 充分取数 -> ok 信封 + indicators + regime + unavailable 列出缺失 key
    monkeypatch.setattr(md_mod, "fetch_all", lambda: sample)
    monkeypatch.setattr(md_mod, "global_regime_score", lambda: regime)
    resp = client.get("/api/v2/read/macro-data", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ok", body
    d = body["data"]
    assert d["indicators"]["pmi"]["value"] == 51.2
    assert d["indicators"]["cpi"] is None  # 取不到如实 null
    assert d["indicators"]["dxy"]["value"] == 102.3
    assert d["regime"]["score"] == 62
    assert d["regime"]["sub"]["dxy"] == 55.0
    assert d["unavailable"] == ["cpi"]

    # 2) regime 取不到 -> None（不编造评分）
    monkeypatch.setattr(md_mod, "global_regime_score", lambda: None)
    resp2 = client.get("/api/v2/read/macro-data", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    assert resp2.get_json()["data"]["regime"] is None
    # 指标仍正常
    assert resp2.get_json()["data"]["indicators"]["pmi"]["value"] == 51.2

    # 3) 整体异常 -> 仍 200、unavailable=['macro_fetch_failed']（不 500）
    def _boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(md_mod, "fetch_all", _boom)
    resp3 = client.get("/api/v2/read/macro-data", headers={"Authorization": f"Bearer {token}"})
    assert resp3.status_code == 200
    assert resp3.get_json()["data"]["unavailable"] == ["macro_fetch_failed"]
    assert resp3.get_json()["data"]["indicators"] == {}

