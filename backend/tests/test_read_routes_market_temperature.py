# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_read_routes_market_temperature.py — /api/v2/read/market-temperature 回归守卫。

验证：
  1. 无 token -> 401（鉴权闸门）；
  2. 正常路径：三个 modules 函数 monkeypatch 已知结构 -> 响应字段逐字透传
     （含 hits / forward 嵌套），hist_days 白名单 {60, 250, 2000} 全可用；
  3. hist_days 非法（非白名单 / 非 int）-> 422 validation_error；
  4. get_shepherd_today 不可用（抛异常 / available 空）-> 三块全部 available=False
     + 中文 reason + temp=None + contributions=[]，无任何 0 补值、无 data_as_of；
  5. analogs / extreme_signal 内部异常 -> 仍 200 + 对应块 available=False + reason。

monkeypatch 目标为 modules.shepherd / modules.market_temperature 的模块属性：
端点在函数内 `from modules import ...` 后按属性调用（call-time 查找），
monkeypatch.setattr(module, name, fake) 即生效，无需触达真实数据源。
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
import modules.shepherd as shepherd_mod  # noqa: E402
import modules.market_temperature as mt_mod  # noqa: E402

URL = "/api/v2/read/market-temperature"


# ───────────────────── 已知结构的假数据 / 假函数 ─────────────────────
TODAY_WITH_DATE = {
    "date": "2026-11-20",
    "red_ratio": 57.0,
    "limit_up": 50,
    "limit_down": 10,
    "zt_prev_ret": 1.0,
}
TODAY_NO_DATE = {k: v for k, v in TODAY_WITH_DATE.items() if k != "date"}
META_OK = {
    "available": ["red_ratio", "limit_up", "limit_down"],
    "unavailable": [("zt_pool", "涨停池暂不可用")],
}
META_EMPTY = {"available": [], "unavailable": [("legu", "乐股快照暂不可用")]}

TEMP_DETAIL = {
    "temp": 63.5,
    "contributions": [
        {"key": "red_ratio", "name": "红盘占比", "unit": "%", "dir": 1,
         "value": 57.0, "hot": 70.0, "warm": 45.0, "heat": 12.3},
        {"key": "limit_up", "name": "涨停数", "unit": "家", "dir": 1,
         "value": 50, "hot": 90.0, "warm": 30.0, "heat": 8.1},
    ],
}
EXTREME_OK = {
    "available": True, "evaluated": True, "triggered": True,
    "hits": [{"key": "zt_prev_ret", "name": "昨日涨停表现", "value": 1.0,
              "threshold": -2.0, "prob": 0.62, "n": 296, "z": 4.36,
              "why": "极端恐慌出清后次日红盘概率显著抬升"}],
    "prob": 0.62, "base_rate": 0.47, "edge_pp": 15.0,
    "strength_hint": "strong",
    "statement": "恐慌出清，历史统计次日红盘概率偏高",
    "abstain": False, "reason": None,
}
ANALOGS_OK = {
    "available": True,
    "today_metrics": {"red_ratio": 57.0, "limit_up": 50.0, "limit_down": 10.0},
    "analogs": [
        {"date": "2025-03-04", "distance": 0.12,
         "metrics": {"red_ratio": 56.0, "limit_up": 48.0, "limit_down": 9.0},
         "state": "修复试探",
         "forward": {
             "d5": {"avg_red": 55.0, "up_frac": 0.6, "median_delta": 0.4},
             "d10": {"avg_red": 54.0, "up_frac": 0.55, "median_delta": 0.2},
             "d20": {"avg_red": 53.0, "up_frac": 0.5, "median_delta": -0.1},
         }},
    ],
    "reason": "",
}


def _mk_fakes(captured=None, temp_detail=TEMP_DETAIL, extreme=EXTREME_OK,
              analogs=ANALOGS_OK, today=TODAY_WITH_DATE, meta=META_OK):
    """构造三个 fake：可选把调用入参记录进 captured dict 供断言。"""
    def fake_get_shepherd_today():
        if captured is not None:
            captured["shepherd_called"] = True
        return today, meta

    def fake_temp_contrib(t, hist_days=2000):
        if captured is not None:
            captured["temp_today"] = t
            captured["temp_hist_days"] = hist_days
        return temp_detail

    def fake_extreme(t):
        if captured is not None:
            captured["extreme_today"] = t
        return extreme

    def fake_analogs(t, k=8):
        if captured is not None:
            captured["analogs_today"] = t
            captured["analogs_k"] = k
        return analogs

    return fake_get_shepherd_today, fake_temp_contrib, fake_extreme, fake_analogs


def _patch_fakes(monkeypatch, **kwargs):
    captured = {}
    f_today, f_temp, f_extreme, f_analogs = _mk_fakes(captured, **kwargs)
    monkeypatch.setattr(shepherd_mod, "get_shepherd_today", f_today)
    monkeypatch.setattr(mt_mod, "temperature_contributions", f_temp)
    monkeypatch.setattr(mt_mod, "extreme_zone_signal", f_extreme)
    monkeypatch.setattr(mt_mod, "historical_analogs", f_analogs)
    return captured


# ───────────────────── fixture（与 test_read_routes.py 同款）─────────────────────
@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'mt.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="mtuser", role="user")
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
        u = User.query.filter_by(username="mtuser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ───────────────────── 用例 ─────────────────────
def test_auth_gate_requires_token(client):
    """无 token 必须 401。"""
    assert client.get(URL).status_code == 401


def test_full_passthrough_default(client, token, monkeypatch):
    """正常路径：三块已知结构逐字透传（含 hits/forward 嵌套）+ data_as_of。"""
    captured = _patch_fakes(monkeypatch)
    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj

    data = obj["data"]
    assert data["hist_days"] == 2000
    assert data["data_as_of"] == "2026-11-20"  # 快照自带 date 才透出，非 now() 生成
    assert data["temperature"] == {
        "available": True,
        "temp": 63.5,
        "contributions": TEMP_DETAIL["contributions"],
        "reason": None,
        "indicators_available": ["red_ratio", "limit_up", "limit_down"],
        "indicators_unavailable": [["zt_pool", "涨停池暂不可用"]],
    }
    assert data["extreme_signal"] == EXTREME_OK
    assert data["extreme_signal"]["hits"][0]["z"] == 4.36
    assert data["analogs"] == ANALOGS_OK
    assert data["analogs"]["analogs"][0]["forward"]["d5"]["up_frac"] == 0.6

    # 入参透传：today 原样、hist_days 透传给温度合成、k=8 给类比
    assert captured["temp_today"] == TODAY_WITH_DATE
    assert captured["temp_hist_days"] == 2000
    assert captured["extreme_today"] == TODAY_WITH_DATE
    assert captured["analogs_today"] == TODAY_WITH_DATE
    assert captured["analogs_k"] == 8


@pytest.mark.parametrize("hd", [60, 250, 2000])
def test_hist_days_whitelist(client, token, monkeypatch, hd):
    """白名单三档全可用，hist_days 透传给温度合成并回显。"""
    captured = _patch_fakes(monkeypatch)
    resp = client.get(f"{URL}?hist_days={hd}", headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok", obj
    assert obj["data"]["hist_days"] == hd
    assert captured["temp_hist_days"] == hd


@pytest.mark.parametrize("raw", ["100", "abc", "60.5", "-1"])
def test_hist_days_invalid_422(client, token, raw):
    """非白名单 / 非 int -> 422 validation_error + 中文文案。"""
    resp = client.get(f"{URL}?hist_days={raw}", headers=_auth(token))
    assert resp.status_code == 422
    obj = resp.get_json()
    assert obj["status"] == "error" and obj["code"] == "validation_error", obj
    assert "hist_days" in obj["message"]


def test_today_unavailable_shepherd_exception(client, token, monkeypatch):
    """get_shepherd_today 抛异常 -> 三块全部 available=False，无 0 补值、无 data_as_of。"""
    def _boom():
        raise RuntimeError("legu 网络超时")

    monkeypatch.setattr(shepherd_mod, "get_shepherd_today", _boom)
    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok", obj  # 诚实降级，不 500

    data = obj["data"]
    assert "data_as_of" not in data  # 绝不用 now() 兜底日期
    t = data["temperature"]
    assert t["available"] is False
    assert t["temp"] is None  # 绝不补 0
    assert t["contributions"] == []
    assert isinstance(t["reason"], str) and t["reason"].strip()
    e = data["extreme_signal"]
    assert e["available"] is False and e["hits"] == [] and e["abstain"] is True
    assert isinstance(e["reason"], str) and e["reason"].strip()
    a = data["analogs"]
    assert a["available"] is False and a["analogs"] == [] and a["today_metrics"] is None
    assert isinstance(a["reason"], str) and a["reason"].strip()


def test_today_unavailable_empty_meta(client, token, monkeypatch):
    """meta.available 为空 -> today 必须被弃用，三块降级；unavailable 清单仍诚实透出。"""
    captured = _patch_fakes(monkeypatch, today=TODAY_WITH_DATE, meta=META_EMPTY)
    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "data_as_of" not in data
    t = data["temperature"]
    assert t["available"] is False and t["temp"] is None and t["contributions"] == []
    assert t["indicators_available"] == []
    assert t["indicators_unavailable"] == [["legu", "乐股快照暂不可用"]]
    assert data["extreme_signal"]["available"] is False
    assert data["analogs"]["available"] is False
    # 三块 fake 均不应被调用
    assert "temp_today" not in captured and "extreme_today" not in captured


def test_no_data_as_of_when_today_missing_date(client, token, monkeypatch):
    """快照无 date 键 -> 省略 data_as_of（绝不 now() 兜底），三块照常可用。"""
    _patch_fakes(monkeypatch, today=TODAY_NO_DATE)
    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "data_as_of" not in data
    assert data["temperature"]["available"] is True
    assert data["extreme_signal"]["available"] is True
    assert data["analogs"]["available"] is True


def test_analogs_exception_degrades(client, token, monkeypatch):
    """historical_analogs 内部抛异常 -> 200 + analogs 块降级，其余两块不受影响。"""
    def _boom(t, k=8):
        raise ValueError("广度历史加载失败")

    _patch_fakes(monkeypatch)
    monkeypatch.setattr(mt_mod, "historical_analogs", _boom)
    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok", obj
    data = obj["data"]
    a = data["analogs"]
    assert a["available"] is False and a["analogs"] == []
    assert a["today_metrics"] is None
    assert "ValueError" in a["reason"]
    assert data["temperature"]["available"] is True
    assert data["extreme_signal"]["available"] is True


def test_extreme_exception_degrades(client, token, monkeypatch):
    """extreme_zone_signal 内部抛异常 -> 200 + extreme 块降级（键集完整），其余两块不受影响。"""
    def _boom(t):
        raise RuntimeError("校准件读取失败")

    _patch_fakes(monkeypatch)
    monkeypatch.setattr(mt_mod, "extreme_zone_signal", _boom)
    resp = client.get(URL, headers=_auth(token))
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj["status"] == "ok", obj
    data = obj["data"]
    e = data["extreme_signal"]
    assert set(e.keys()) == {
        "available", "evaluated", "triggered", "hits", "prob", "base_rate",
        "edge_pp", "strength_hint", "statement", "abstain", "reason",
    }
    assert e["available"] is False and e["evaluated"] is False
    assert e["triggered"] is False and e["hits"] == [] and e["abstain"] is True
    assert e["prob"] is None and e["base_rate"] is None and e["edge_pp"] is None
    assert isinstance(e["reason"], str) and "RuntimeError" in e["reason"]
    assert data["temperature"]["available"] is True
    assert data["analogs"]["available"] is True
