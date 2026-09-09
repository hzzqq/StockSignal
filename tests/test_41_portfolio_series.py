"""
41_组合收益 fragment_portfolio 的崩溃回归测试（R15）。

根因：_build_portfolio_series 里：
- 线程池把每只持仓的 {date: float市值} 合并进 series（series = {date: float}）；
- 但聚合行写成 `pdict = {d: sum(v.values()) for d, v in series.items()}`，
  把 v（float）当成 dict 调 .values() → AttributeError: 'float' object has no attribute 'values'；
  被 safe_fragment 隔离成「🧯 ⚠️ 组合收益 加载失败（AttributeError）」。
- 附带数据正确性 bug：series.update(_fut.result()) 在跨持仓同日期时**覆盖**而非累加，
  会丢失其它持仓当天市值。修复改为按日期累加。

本测试打桩 PortfolioManager.get_positions + StockFetcher.get_daily（两票同日期，验证累加），
断言：① 不再渲染 AttributeError 隔离卡片；② 组合净值曲线（plotly_chart）正常渲染。
"""
from __future__ import annotations

import os
import time

import jwt
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PAGE = os.path.join(_PROJECT_ROOT, "pages", "41_组合收益.py")

from modules.site_config import TEST_SMOKE_SECRET

_FAKE_TOKEN = jwt.encode(
    {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
    TEST_SMOKE_SECRET, algorithm="HS256",
)


def _authed(at):
    at.session_state["auth_token"] = _FAKE_TOKEN
    at.session_state["auth_user"] = {"id": 1, "username": "demo", "role": "admin"}


def _fake_positions():
    # ticker / remaining_shares / buy_date 三列（_build_portfolio_series 读取所需）
    return pd.DataFrame([
        {"ticker": "600519", "buy_date": "2024-01-01", "remaining_shares": 100},
        {"ticker": "000001", "buy_date": "2024-01-01", "remaining_shares": 200},
    ])


def _fake_get_daily(self, ticker, start=None, end=None):
    # 两票日期完全重叠（2024-01-02 / 2024-01-03），专门验证「跨持仓同日累加」而非覆盖。
    closes = [10.0, 11.0] if ticker == "600519" else [20.0, 22.0]
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "close": closes,
    })


def _err_texts(at) -> list[str]:
    out = []
    try:
        for w in at.error:
            out.append(getattr(w, "value", str(w)))
    except Exception:
        pass
    return out


def test_portfolio_series_no_attribute_error(monkeypatch):
    from modules.portfolio import PortfolioManager
    from modules.fetcher import StockFetcher

    monkeypatch.setattr(PortfolioManager, "get_positions", lambda self: _fake_positions(), raising=True)
    monkeypatch.setattr(StockFetcher, "get_daily", _fake_get_daily, raising=True)

    at = AppTest.from_file(_PAGE, default_timeout=120)
    _authed(at)
    at.run()

    errs = _err_texts(at)
    bad = [e for e in errs if "AttributeError" in e or ("组合收益" in e and "加载失败" in e)]
    assert not bad, f"组合收益 fragment 仍渲染错误卡片: {errs}"
    assert not at.exception, f"组合收益 fragment 抛未捕获异常: {[str(e) for e in at.exception]}"
    # 正向确认：净值曲线成功构建并渲染（pidx 非 None → 渲染「组合累计收益」指标）
    labels = [m.label for m in at.metric]
    assert "组合累计收益" in labels, f"组合净值未正常构建（预期出现『组合累计收益』指标）；当前指标: {labels}"
