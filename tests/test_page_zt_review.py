"""页面 70《涨停复盘 × 龙头识别》渲染回归测试。

为何需要独立测试（而非只靠 test_pages_smoke）：
- test_pages_smoke 在沙箱里把网络打桩成速败，页面 70 在「取不到交易日历」即 st.stop()
  优雅退出，**主体（①KPI ②时间线 ③梯队 ④龙头榜 ⑤分档 ⑥题材/炸板 ⑦交叉验证）根本不执行**。
- 本测试**直接注入假的涨停池/梯队/牧羊人/状态机数据**，逼出主体代码的渲染路径，
  抓「函数内 NameError / KeyError / plotly 调用异常」类真 bug（普通 import 检查抓不到）。

不依赖网络：所有取数入口 monkeypatch 为内存假数据；并叠加离线网络 stub 兜底任何残余调用。
"""
from __future__ import annotations

import os

import pandas as pd
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

# 中和 AppTest 环境伪象
st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PAGE_70 = os.path.join(_PROJECT_ROOT, "pages", "70_涨停复盘.py")

_FAKE_DAYS = [
    "20260915", "20260912", "20260911", "20260910", "20260909", "20260908",
]

# 涨停池假数据：列为东财候选列名（与页面 COL 映射一致）
def _fake_pool_df():
    return pd.DataFrame([
        # 代码, 名称, 连板数, 所属行业, 封板资金, 成交额, 首次封板时间, 炸板次数, 换手率, 流通市值, 涨跌幅
        ["600000", "浦发银行", 1, "银行", 1_000_000, 5_000_000, "093000", 0, 1.2, 3.0e11, 10.0],
        ["600001", "招商银行", 2, "银行", 2_000_000, 8_000_000, "093500", 1, 2.0, 4.0e11, 9.5],
        ["600002", "中信银行", 3, "银行", 3_000_000, 9_000_000, "100000", 0, 1.5, 3.5e11, 9.0],
        ["600003", "兴业银行", 4, "银行", 4_000_000, 12_000_000, "140000", 2, 3.0, 5.0e11, 8.5],
        ["600004", "平安银行", 1, "银行", 1_500_000, 6_000_000, "140500", 0, 1.1, 4.5e11, 9.2],
    ], columns=[
        "代码", "名称", "连板数", "所属行业", "封板资金", "成交额",
        "首次封板时间", "炸板次数", "换手率", "流通市值", "涨跌幅",
    ])


def _fake_ladder():
    return {
        "levels": [], "total_connect": 3, "max_boards": 4,
        "distribution": [(4, 1), (3, 1), (2, 1), (1, 2)], "top": None,
    }


def _fake_ind_df():
    return pd.DataFrame([{
        "date": "20260915", "zt_fail_ratio": 30.0, "limit_up": 5,
        "limit_down": 1, "median_chg": 1.2,
    }])


def _fake_snap():
    return {"cycle": "主升", "temperature": 60.0}


def _fake_regime():
    return {"available": True, "latest": {"state": "主升", "confidence": 0.8}}


def _offline_stub(monkeypatch):
    """兜底：残余网络入口速败，避免任何漏网调用真连网挂起。"""
    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")
    for tgt in (requests, requests.Session):
        for attr in ("get", "post", "request"):
            try:
                monkeypatch.setattr(tgt, attr, _boom, raising=True)
            except AttributeError:
                pass


def _patch_sources(monkeypatch):
    """把所有取数入口替换为内存假数据（含 _trading_days，使页面走到真实主体路径）。"""
    import modules.shepherd as _sh
    import modules.market_regime as _mr

    monkeypatch.setattr(_sh, "_trading_days", lambda n: list(_FAKE_DAYS[:n]), raising=True)
    monkeypatch.setattr(_sh, "_zt_pool_detail_cached", lambda date=None: _fake_pool_df(), raising=True)
    monkeypatch.setattr(_sh, "get_zt_ladder", lambda *a, **k: _fake_ladder(), raising=True)
    monkeypatch.setattr(_sh, "get_shepherd_indicators", lambda *a, **k: (_fake_ind_df(), {}), raising=True)
    monkeypatch.setattr(_sh, "load_latest_snapshot", lambda: _fake_snap(), raising=True)
    monkeypatch.setattr(_mr, "regime_report", lambda *a, **k: _fake_regime(), raising=True)


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
def test_page70_renders_with_fake_data(authed: bool, monkeypatch):
    """注入假数据后，页面 70 在游客/已登录态下均应无未捕获异常地渲染完主体。"""
    _patch_sources(monkeypatch)
    _offline_stub(monkeypatch)

    at = AppTest.from_file(PAGE_70, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    msgs = []
    if len(at.exception):
        msgs.append("EXC:" + "; ".join(str(e) for e in at.exception[:3]))
    assert not msgs, f"页面 70 渲染抛出异常: {msgs}"


@pytest.mark.parametrize("authed", [False, True], ids=["guest", "authed"])
def test_page70_offline_graceful_stop(authed: bool, monkeypatch):
    """不注入任何假数据、仅离线打桩：真实 _trading_days 应抛错被页面 try/except 捕获，
    页面优雅 st.stop()（提示「无法获取交易日历」），不得抛出未捕获异常。
    这覆盖 test_pages_smoke 在沙箱里对页面 70 的唯一执行路径。"""
    _offline_stub(monkeypatch)

    at = AppTest.from_file(PAGE_70, default_timeout=120)
    if authed:
        _auth_session(at)
    at.run()
    msgs = []
    if len(at.exception):
        msgs.append("EXC:" + "; ".join(str(e) for e in at.exception[:3]))
    assert not msgs, f"离线场景下页面 70 应优雅降级而非崩溃: {msgs}"
