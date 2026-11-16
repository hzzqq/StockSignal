"""财报猎手（业绩预告信号扫描）v2 读端点验收测试。

承接 v1 ``pages/77_财报猎手.py`` → ``GET /api/v2/read/earnings-hunter``。

测试夹具说明：
  * 业绩预告 DataFrame 为**合成确定性夹具，非真实接口数据**，
    monkeypatch ``backend.api.earnings_routes.get_earnings_forecast`` 注入，绝不真联网；
  * 端点层用真 Flask test_client + 独立 SQLite（E:/tmp/ss_probe_d/app.db）+ 真 JWT；
  * 覆盖：正常扫描（过滤+降序+n_total）/ 空数据降级 / 取数异常降级 /
    period 白名单 422 / signals 非法 422 / min_pct 非法 422 / 无 token 401 / NaN→None。
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

PROBE_DIR = "E:/tmp/ss_probe_d"

# ── 合成确定性业绩预告夹具（非真实数据）──
# 信号映射：预增→利好 / 略增→偏多 / 预减→利空 / 略减→偏空 / 续盈→偏多
_COLS = ["股票代码", "股票简称", "预告类型", "业绩变动幅度",
         "业绩变动原因", "公告日期", "预测指标"]


def _forecast_df() -> pd.DataFrame:
    return pd.DataFrame({
        "股票代码": ["600519", "000001", "300750", "600000", "688111"],
        "股票简称": ["贵州茅台", "平安银行", "宁德时代", "浦发银行", "金山办公"],
        "预告类型": ["预增", "略增", "预减", "略减", "续盈"],
        "业绩变动幅度": [20.0, 10.0, -30.0, float("nan"), 5.0],
        "业绩变动原因": ["产销两旺", "规模增长", "行业竞争加剧", "息差收窄", "订单增长"],
        "公告日期": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"],
        "预测指标": ["净利润"] * 5,
    })


def _forecast_df_many(n: int) -> pd.DataFrame:
    """n 行夹具，用于验证 rows 截断 100 + n_total 语义。"""
    rows = []
    for i in range(n):
        rows.append({
            "股票代码": f"{600000 + i}", "股票简称": f"标的{i}",
            "预告类型": "预增", "业绩变动幅度": float(n - i),
            "业绩变动原因": "合成夹具", "公告日期": "2026-07-01", "预测指标": "净利润",
        })
    return pd.DataFrame(rows)


def _install_fetch(monkeypatch, df="default", error=None):
    """把 fake 注入到 earnings_routes 模块内引用处（patch 目标即端点实际调用处）。

    df="default" → 正常夹具；df=None → 空 DataFrame；error 非 None → 抛异常。
    返回 calls 列表记录每次调用收到的 period。
    """
    import backend.api.earnings_routes as er

    calls: list = []
    data = _forecast_df() if isinstance(df, str) and df == "default" else df

    def fake(period="20260630"):
        calls.append(period)
        if error is not None:
            raise error
        return data if data is not None else pd.DataFrame()

    monkeypatch.setattr(er, "get_earnings_forecast", fake)
    return calls


# ───────────── 0. 纯函数层（分级语义回归）─────────────
def test_signal_mapping_semantics():
    from modules.financial_hunter import SIGNAL_ORDER, signal_of

    assert SIGNAL_ORDER == ["利好", "偏多", "中性", "偏空", "利空"]
    assert signal_of("预增") == "利好" and signal_of("扭亏") == "利好"
    assert signal_of("略增") == "偏多" and signal_of("续盈") == "偏多"
    assert signal_of("首亏") == "利空" and signal_of("预减") == "利空"
    assert signal_of("略减") == "偏空" and signal_of("续亏") == "偏空"
    assert signal_of("不确定") == "中性"


# ───────────── 1. 端点（真 Flask test_client + 独立 SQLite + JWT）─────────────
@pytest.fixture
def app(monkeypatch):
    os.makedirs(PROBE_DIR, exist_ok=True)
    db_url = f"sqlite:///{PROBE_DIR}/app.db"
    monkeypatch.setenv("DATABASE_URL", db_url)

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = db_url
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    # team-lead 会在 backend/app.py 统一注册本 blueprint；此处条件注册保证测试在当前
    # worktree（app.py 尚未改）也能跑，且未来 app.py 注册后不会重复注册。
    from backend.api.earnings_routes import bp as earnings_bp

    if "earnings_hunter" not in application.blueprints:
        application.register_blueprint(earnings_bp)

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


def _assert_validation_422(r):
    assert r.status_code == 422, f"期望 422，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert j["status"] == "error" and j["code"] == "validation_error", j
    assert j["data"] is None, j


def test_earnings_hunter_happy_path(client, auth, monkeypatch):
    calls = _install_fetch(monkeypatch)
    r = client.get("/api/v2/read/earnings-hunter", headers=auth)
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok" and j["code"] == "ok", j
    d = j["data"]
    assert d["available"] is True and d["reason"] is None, d
    assert d["n_scanned"] == 5 and d["n_total"] == 5, d
    assert d["signal_counts"] == {"利好": 1, "偏多": 2, "中性": 0, "偏空": 1, "利空": 1}, d
    # 全部信号档位都在（0 也给）
    assert set(d["signal_counts"]) == {"利好", "偏多", "中性", "偏空", "利空"}, d
    # 缺省不过滤 → 5 行，按业绩变动幅度降序（NaN 排最后）
    pcts = [row["_pct"] for row in d["rows"]]
    assert pcts == [20.0, 10.0, 5.0, -30.0, None], d
    assert calls == ["20260630"], calls  # 缺省报告期


def test_earnings_hunter_filter_and_desc_order(client, auth, monkeypatch):
    _install_fetch(monkeypatch)
    r = client.get(
        "/api/v2/read/earnings-hunter",
        query_string={"min_pct": "0", "signals": "利好,偏多"},
        headers=auth,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    # 过滤：信号 ∈ {利好,偏多} 且 幅度 ≥ 0 → 600519(20) / 000001(10) / 688111(5)
    assert d["n_total"] == 3 and len(d["rows"]) == 3, d
    assert [row["股票代码"] for row in d["rows"]] == ["600519", "000001", "688111"], d
    assert d["n_scanned"] == 5, d  # 统计仍是全量
    # signal_counts 仍按 annotate 后全量统计（不受筛选影响）
    assert d["signal_counts"]["利好"] == 1 and d["signal_counts"]["偏空"] == 1, d


def test_earnings_hunter_empty_data_degrades(client, auth, monkeypatch):
    _install_fetch(monkeypatch, df=None)
    r = client.get("/api/v2/read/earnings-hunter?period=20260331", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is False, d
    assert "暂无业绩预告数据" in d["reason"], d
    assert d["rows"] == [], d


def test_earnings_hunter_fetch_error_degrades(client, auth, monkeypatch):
    _install_fetch(monkeypatch, error=RuntimeError("akshare 接口超时"))
    r = client.get("/api/v2/read/earnings-hunter", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is False, d
    assert d["rows"] == [], d
    # reason 带真实异常文本
    assert "RuntimeError" in d["reason"] and "akshare 接口超时" in d["reason"], d
    assert len(d["reason"]) <= 180, d


@pytest.mark.parametrize("period", ["20240630", "20260631", "2026", "abc", ""])
def test_earnings_hunter_period_not_whitelisted_422(client, auth, monkeypatch, period):
    calls = _install_fetch(monkeypatch)
    r = client.get("/api/v2/read/earnings-hunter",
                   query_string={"period": period}, headers=auth)
    _assert_validation_422(r)
    assert calls == [], calls  # 白名单拦截在取数之前


@pytest.mark.parametrize("signals", ["利好,涨停", "利空,", "中性 中性", "优选"])
def test_earnings_hunter_invalid_signals_422(client, auth, monkeypatch, signals):
    _install_fetch(monkeypatch)
    r = client.get("/api/v2/read/earnings-hunter",
                   query_string={"signals": signals}, headers=auth)
    _assert_validation_422(r)


@pytest.mark.parametrize("min_pct", ["abc", "300", "-500", "nan", "inf"])
def test_earnings_hunter_invalid_min_pct_422(client, auth, monkeypatch, min_pct):
    _install_fetch(monkeypatch)
    r = client.get("/api/v2/read/earnings-hunter",
                   query_string={"min_pct": min_pct}, headers=auth)
    _assert_validation_422(r)


def test_earnings_hunter_no_token_401(client, monkeypatch):
    _install_fetch(monkeypatch)
    r = client.get("/api/v2/read/earnings-hunter")
    assert r.status_code == 401, f"期望 401，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert j["status"] == "error" and j["code"] == "missing_token", j


def test_earnings_hunter_nan_to_none(client, auth, monkeypatch):
    _install_fetch(monkeypatch)
    r = client.get("/api/v2/read/earnings-hunter", headers=auth)
    assert r.status_code == 200, r.text[:300]
    # 原始响应文本中不允许出现 NaN 字面量
    assert "NaN" not in r.text, r.text[:600]
    d = r.get_json()["data"]
    row = next(x for x in d["rows"] if x["股票代码"] == "600000")
    assert row["_pct"] is None and row["业绩变动幅度"] is None, row
    # 非缺失字段不受影响
    assert row["预告类型"] == "略减" and row["_signal"] == "偏空", row


def test_earnings_hunter_rows_truncated_to_100(client, auth, monkeypatch):
    _install_fetch(monkeypatch, df=_forecast_df_many(103))
    r = client.get("/api/v2/read/earnings-hunter", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["n_total"] == 103 and len(d["rows"]) == 100, d
    # 截断保留的是降序后的前 100 行
    assert d["rows"][0]["业绩变动幅度"] == 103.0, d
    assert d["rows"][-1]["业绩变动幅度"] == 4.0, d
