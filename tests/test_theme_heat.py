"""G7 题材热点守卫：生命周期/换手分位纯逻辑 + 页面渲染/离线降级。"""
from __future__ import annotations

import os

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

from modules.theme_heat import lifecycle_label, turnover_pct

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(_PROJECT_ROOT, "pages", "75_题材热点.py")


def test_lifecycle_label_rules():
    assert lifecycle_label(5.0, 90.0) == "高潮"
    assert lifecycle_label(2.0, 50.0) == "发酵"
    assert lifecycle_label(-2.0, 70.0) == "退潮"
    assert lifecycle_label(0.5, 20.0) == "平淡"
    assert lifecycle_label(None, 50.0) == "未知"
    assert lifecycle_label(float("nan"), 50.0) == "未知"


def test_turnover_pct_range():
    df = pd.DataFrame({"换手率": [1.0, 2.0, 3.0, 4.0]})
    p = turnover_pct(df)
    assert p.min() > 0 and p.max() == 100.0


def _fake_loaded():
    d = pd.DataFrame([
        ["AI算力", 5.2, 1e11, 4.0, "龙头A"],
        ["白酒", -1.5, 5e11, 1.2, "龙头B"],
        ["光伏", 2.0, 8e10, 3.5, "龙头C"],
    ], columns=["板块名称", "涨跌幅", "总市值", "换手率", "领涨股票"])
    d["_chg"] = d["涨跌幅"]
    d["_turnover_p"] = [90.0, 20.0, 60.0]
    d["_life"] = ["高潮", "平淡", "退潮"]
    return d


def _offline_stub(monkeypatch):
    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")
    for tgt in (requests, requests.Session):
        for attr in ("get", "post", "request"):
            try:
                monkeypatch.setattr(tgt, attr, _boom, raising=True)
            except AttributeError:
                pass


def _auth_session(at):
    from modules.site_config import TEST_SMOKE_SECRET
    import jwt, time
    tok = jwt.encode(
        {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
        TEST_SMOKE_SECRET, algorithm="HS256",
    )
    at.session_state["auth_token"] = tok
    at.session_state["auth_user"] = {"id": 1, "username": "demo", "role": "admin"}


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_theme_heat_renders_with_fake_data(authed, monkeypatch):
    import modules.theme_heat as th
    monkeypatch.setattr(th, "load_concepts", lambda: _fake_loaded(), raising=True)
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"题材热点页渲染异常: {[str(e) for e in at.exception]}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_theme_heat_offline_graceful(authed, monkeypatch):
    _offline_stub(monkeypatch)
    at = AppTest.from_file(PAGE, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    assert not at.exception, f"离线应优雅降级而非崩溃: {[str(e) for e in at.exception]}"


def test_concepts_fallback_to_ths_when_eastmoney_fails(monkeypatch):
    """东财代理/限流失败时切同花顺真实概念资金流，不静默吞、不冒充市值/换手率。"""
    import akshare as ak
    import modules.theme_heat as th

    def _boom(*args, **kwargs):
        raise RuntimeError("eastmoney proxy blocked")

    ths = pd.DataFrame({
        "行业": ["AI", "光伏"],
        "行业-涨跌幅": [3.5, -2.0],
        "净额": [12.5, "-3.2亿"],
        "公司家数": [120, 60],
        "领涨股": ["寒武纪", "通威股份"],
    })
    monkeypatch.setattr(ak, "stock_board_concept_name_em", _boom, raising=True)
    monkeypatch.setattr(ak, "stock_fund_flow_concept", lambda symbol="即时": ths, raising=True)

    th._concepts_cached.clear()
    try:
        got = th.load_concepts()
        assert got is not None and not got.empty
        assert list(got["板块名称"]) == ["AI", "光伏"]
        assert set(got["_source"]) == {th.SOURCE_THS}
        assert got["_heat_basis"].eq("资金净额绝对值分位").all()
        assert got["_net_yi"].tolist() == [12.5, -3.2]
        assert got["_life"].notna().all()
        # 同花顺源没有总市值/换手率，派生列不得凭空补出东财字段
        assert "总市值" not in got.columns
        assert "换手率" not in got.columns
    finally:
        th._concepts_cached.clear()


def test_concepts_all_sources_fail_returns_none(monkeypatch):
    """三级全失败→返回 None 由上层诚实空态，不编题材。"""
    import akshare as ak
    import modules.theme_heat as th

    def _boom(*args, **kwargs):
        raise RuntimeError("all sources blocked")

    monkeypatch.setattr(ak, "stock_board_concept_name_em", _boom, raising=True)
    monkeypatch.setattr(ak, "stock_fund_flow_concept", _boom, raising=True)
    monkeypatch.setattr(ak, "stock_sector_spot", _boom, raising=True)
    # 直连东财也一并封死（requests.get）
    import requests as _requests
    monkeypatch.setattr(_requests, "get", _boom, raising=True)

    th._concepts_cached.clear()
    try:
        assert th.load_concepts() is None
    finally:
        th._concepts_cached.clear()


def test_concepts_third_level_sina_fallback(monkeypatch):
    """东财/同花顺都失败→新浪概念第三级兜底，热度=公司家数分位，不冒充换手率/市值/净额。"""
    import akshare as ak
    import modules.theme_heat as th

    def _boom(*args, **kwargs):
        raise RuntimeError("blocked")

    sina = pd.DataFrame({
        "label": ["gn_a", "gn_b", "gn_c"],
        "板块": ["人工智能", "光伏", "白酒"],
        "公司家数": [200, 80, 40],
        "涨跌幅": [4.2, -1.0, 0.5],
        "股票名称": ["寒武纪", "通威股份", "贵州茅台"],
    })
    monkeypatch.setattr(ak, "stock_board_concept_name_em", _boom, raising=True)
    monkeypatch.setattr(ak, "stock_fund_flow_concept", _boom, raising=True)
    monkeypatch.setattr(ak, "stock_sector_spot", lambda indicator="概念": sina, raising=True)

    th._concepts_cached.clear()
    try:
        got = th.load_concepts()
        assert got is not None and not got.empty
        assert list(got["板块名称"]) == ["人工智能", "光伏", "白酒"]
        assert set(got["_source"]) == {th.SOURCE_SINA}
        assert got["_heat_basis"].eq("公司家数分位").all()
        assert got["_life"].notna().all()
        # 新浪源没有总市值/换手率/净额，派生列不得凭空补出
        assert "总市值" not in got.columns
        assert "换手率" not in got.columns
        assert got["_net_yi"].isna().all()
    finally:
        th._concepts_cached.clear()


def test_concepts_eastmoney_direct_fallback_when_akshare_blocked(monkeypatch):
    """akshare 东财入口被代理拦 → 直连 push2 主域恢复东财原口径（总市值/换手率真实带出）。"""
    import akshare as ak
    import modules.theme_heat as th

    def _boom(*args, **kwargs):
        raise RuntimeError("79.push2 proxy blocked")

    monkeypatch.setattr(ak, "stock_board_concept_name_em", _boom, raising=True)

    class _Resp:
        def __init__(self, payload):
            self._p = payload
        def raise_for_status(self):
            pass
        def json(self):
            return self._p

    def _fake_get(url, **kwargs):
        assert "push2.eastmoney.com" in url, f"直连域名错误: {url}"
        assert url.startswith("https://push2.eastmoney.com/"), f"必须是主域，非子域: {url}"
        pn = int(kwargs["params"]["pn"])
        if pn == 1:
            diff = [
                {"f3": 3.5, "f8": 8.0, "f12": "BK001", "f14": "AI", "f20": 1e12, "f104": 10, "f105": 2, "f128": "寒武纪"},
                {"f3": -2.0, "f8": 9.0, "f12": "BK002", "f14": "光伏", "f20": 5e11, "f104": 3, "f105": 9, "f128": "通威股份"},
            ]
            return _Resp({"data": {"diff": diff}})
        return _Resp({"data": {"diff": []}})

    import requests as _requests
    monkeypatch.setattr(_requests, "get", _fake_get, raising=True)

    th._concepts_cached.clear()
    try:
        got = th.load_concepts()
        assert got is not None and not got.empty
        assert list(got["板块名称"]) == ["AI", "光伏"]
        assert set(got["_source"]) == {th.SOURCE_EM}
        assert got["_heat_basis"].eq("换手率分位").all()
        # 东财原口径字段必须真实带出（不再被 fallback 清空）
        assert "总市值" in got.columns
        assert "换手率" in got.columns
        assert got["总市值"].tolist() == [1e12, 5e11]
        assert got["_net_yi"].isna().all()
    finally:
        th._concepts_cached.clear()

