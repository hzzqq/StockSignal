# -*- coding: utf-8 -*-  # noqa: UP009
"""backend/tests/test_read_routes_dragon_tiger_date.py

**诚实红线守卫：龙虎榜响应里的 date 必须是真实数据日。**

背景（真实缺陷）：
``backend/api/read_routes.py`` 的 ``dragon_tiger`` 端点把 **请求日**
（``?date=`` 入参，未传时为 ``None``）直接当作响应 ``date`` 回给前端，于是：

- 调用方不传 date 时，后端实际取的是"今天"的龙虎榜，响应却是 ``date: null``
  —— 前端无法知道数据是哪一天的；
- 请求日与数据日本来就是两个概念（modules/lhb.py 里 fetch 的 date 只是
  "向数据源要哪一天"的技术参数，缺省会退到 today()）。

修复后的契约：
- ``date`` = 从**明细自带的日期列**解析出的真实数据日（modules.lhb.data_date）；
- 解析不出 → ``date: null`` + ``data_date_available: false``，
  绝不用 now()/today() 冒充数据日；
- 取数失败 → 仍 200 + ``unavailable: ["lhb_fetch_failed"]``，date 也是 null。

本文件同时钉住 modules.lhb.data_date 的解析行为（零网络：akshare 被替换成桩）。
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
from backend.auth.service import issue_token  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from modules import lhb as lhb_mod  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'lhb_date.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="lhbdate", role="user")
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
        u = User.query.filter_by(username="lhbdate").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _df_with_date(date_str: str = "2026-09-15") -> pd.DataFrame:
    """带真实日期列（东财口径：上榜日）的明细。"""
    return pd.DataFrame({
        "代码": ["600519", "000001"],
        "名称": ["贵州茅台", "平安银行"],
        "上榜日": [date_str, date_str],
        "龙虎榜净买额": [5e7, -8e7],
    })


def _df_without_date() -> pd.DataFrame:
    """明细里没有日期列 → 数据日不可得（不得用 today() 冒充）。"""
    return pd.DataFrame({
        "代码": ["600519", "000001"],
        "名称": ["贵州茅台", "平安银行"],
        "龙虎榜净买额": [5e7, -8e7],
    })


# ─────────────────── modules.lhb.data_date：解析真实数据日 ───────────────────
def test_data_date_parses_real_date_from_detail():
    assert lhb_mod.data_date(_df_with_date("2026-09-15")) == "20260915"


def test_data_date_returns_none_without_date_column():
    assert lhb_mod.data_date(_df_without_date()) is None


def test_data_date_returns_none_for_empty_df():
    assert lhb_mod.data_date(pd.DataFrame()) is None
    assert lhb_mod.data_date(None) is None


def test_data_date_returns_none_for_unparseable_date():
    df = pd.DataFrame({"上榜日": ["不是日期", None]})
    assert lhb_mod.data_date(df) is None


# ─────────────────── 端点：date 必须是真实数据日 ───────────────────
def test_endpoint_date_comes_from_detail_not_request_param(client, token, monkeypatch):
    """请求日与数据日不同时，响应 date 必须是**明细里的真实数据日**。"""
    monkeypatch.setattr(lhb_mod, "fetch_lhb", lambda date=None: _df_with_date("2026-09-15"))
    monkeypatch.setattr(lhb_mod, "summarize", lambda df: {
        "count": 2, "net_col": "龙虎榜净买额", "net_sum": -3e7,
        "buy_top": pd.DataFrame({"代码": ["600519"], "龙虎榜净买额": [5e7]}),
        "sell_top": pd.DataFrame({"代码": ["000001"], "龙虎榜净买额": [-8e7]}),
    })

    resp = client.get("/api/v2/read/dragon-tiger", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["date"] == "20260915", "date 必须是明细里的真实数据日"
    assert d["data_date_available"] is True


def test_endpoint_date_null_when_detail_has_no_date(client, token, monkeypatch):
    """明细无日期列 → date=null + data_date_available=false（绝不用 today() 冒充）。"""
    monkeypatch.setattr(lhb_mod, "fetch_lhb", lambda date=None: _df_without_date())
    monkeypatch.setattr(lhb_mod, "summarize", lambda df: {
        "count": 2, "net_col": "龙虎榜净买额", "net_sum": -3e7,
        "buy_top": pd.DataFrame({"代码": ["600519"], "龙虎榜净买额": [5e7]}),
        "sell_top": pd.DataFrame({"代码": ["000001"], "龙虎榜净买额": [-8e7]}),
    })

    resp = client.get("/api/v2/read/dragon-tiger", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["date"] is None, "解析不出数据日时不得填 today()"
    assert d["data_date_available"] is False
    assert d["count"] == 2, "明细本身可用，count 照常给出"


def test_endpoint_date_is_not_today_when_request_omits_date(client, token, monkeypatch):
    """不传 date 时：响应 date 来自明细（数据日），不是请求参数（null），也不是隐式 today()。"""
    monkeypatch.setattr(lhb_mod, "fetch_lhb", lambda date=None: _df_with_date("2026-09-15"))
    monkeypatch.setattr(lhb_mod, "summarize", lambda df: {
        "count": 2, "net_col": "龙虎榜净买额", "net_sum": -3e7,
        "buy_top": pd.DataFrame({"代码": ["600519"], "龙虎榜净买额": [5e7]}),
        "sell_top": pd.DataFrame({"代码": ["000001"], "龙虎榜净买额": [-8e7]}),
    })

    resp = client.get("/api/v2/read/dragon-tiger", headers=_auth(token))
    d = resp.get_json()["data"]
    assert d["date"] == "20260915"
    assert d["date"] is not None, "不传 date 时响应 date 不得为 null（数据日可从明细解析）"


def test_endpoint_fetch_failure_returns_null_date(client, token, monkeypatch):
    """取数失败 → 200 + unavailable，且 date 仍为 null（不拿请求日冒充数据日）。"""
    monkeypatch.setattr(lhb_mod, "fetch_lhb", lambda date=None: None)

    resp = client.get("/api/v2/read/dragon-tiger?date=20260915", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["unavailable"] == ["lhb_fetch_failed"]
    assert d["date"] is None
    assert d["data_date_available"] is False


def test_endpoint_net_col_missing_keeps_real_data_date(client, token, monkeypatch):
    """净买列识别不到时，明细仍有真实日期 → date 照常给出。"""
    monkeypatch.setattr(lhb_mod, "fetch_lhb", lambda date=None: _df_with_date("2026-09-15"))
    monkeypatch.setattr(lhb_mod, "summarize", lambda df: None)

    resp = client.get("/api/v2/read/dragon-tiger", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert d["unavailable"] == ["net_col_missing"]
    assert d["date"] == "20260915"
    assert d["data_date_available"] is True
    assert d["detail"] is not None, "明细仍要诚实保留"


# ─────────────── 缺省日期自动回退最近交易日（2026-11-22 老板需求）───────────────
def _stub_summarize(monkeypatch):
    monkeypatch.setattr(lhb_mod, "summarize", lambda df: {
        "count": 2, "net_col": "龙虎榜净买额", "net_sum": -3e7,
        "buy_top": pd.DataFrame({"代码": ["600519"], "龙虎榜净买额": [5e7]}),
        "sell_top": pd.DataFrame({"代码": ["000001"], "龙虎榜净买额": [-8e7]}),
    })


def test_endpoint_default_falls_back_to_prev_trading_day(client, token, monkeypatch):
    """周末（今天非交易日）：今天不进候选，直接取上一交易日明细，页面不再永远空。"""
    import modules.trading_calendar as tc
    from datetime import date as _d

    monkeypatch.setattr(tc, "is_trading_day", lambda d: False)
    monkeypatch.setattr(tc, "prev_trading_day", lambda d: _d(2026, 11, 20))
    calls = []

    def fake_fetch(date=None):
        calls.append(date)
        return _df_with_date("2026-11-20") if date == "20261120" else None

    monkeypatch.setattr(lhb_mod, "fetch_lhb", fake_fetch)
    _stub_summarize(monkeypatch)

    resp = client.get("/api/v2/read/dragon-tiger", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert calls == ["20261120"], f"非交易日应只探上一交易日，实际 {calls}"
    assert d["date"] == "20261120"
    assert d["data_date_available"] is True
    assert d["count"] == 2


def test_endpoint_default_probes_today_then_falls_back(client, token, monkeypatch):
    """交易日盘中当天未披露：先探今天（空）→ 回退上一交易日。"""
    import modules.trading_calendar as tc
    from datetime import date as _d

    monkeypatch.setattr(tc, "is_trading_day", lambda d: True)
    monkeypatch.setattr(tc, "prev_trading_day", lambda d: _d(2026, 11, 20))
    today_str = _d.today().strftime("%Y%m%d")
    calls = []

    def fake_fetch(date=None):
        calls.append(date)
        return _df_with_date("2026-11-20") if date == "20261120" else None

    monkeypatch.setattr(lhb_mod, "fetch_lhb", fake_fetch)
    _stub_summarize(monkeypatch)

    resp = client.get("/api/v2/read/dragon-tiger", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert calls == [today_str, "20261120"], f"应先探今天再回退，实际 {calls}"
    assert d["date"] == "20261120"


def test_endpoint_explicit_date_never_silently_replaced(client, token, monkeypatch):
    """用户显式传 date（查不到）：诚实降级，绝不悄悄换日期冒充。"""
    calls = []
    monkeypatch.setattr(lhb_mod, "fetch_lhb",
                        lambda date=None: calls.append(date) or None)
    resp = client.get("/api/v2/read/dragon-tiger?date=20260101", headers=_auth(token))
    assert resp.status_code == 200
    d = resp.get_json()["data"]
    assert calls == ["20260101"], "显式日期只查用户给的这一天"
    assert d["unavailable"] == ["lhb_fetch_failed"]
    assert d["date"] is None
