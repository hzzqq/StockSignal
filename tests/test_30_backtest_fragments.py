"""
30_策略回测 两个 fragment 的状态依赖崩溃回归测试。

背景（R11 修复 IndexError/AttributeError 后暴露的新错误类型）：
- fragment_daily_picker：每日选股回测跑出结果后（picker_result 进入 session_state），
  累计收益曲线分支会引用 _is_dark / UP_COLOR / SF_* —— 这些名字**只在该 fragment 之外**
  （fragment_manual_backtest / fragment_strong_bull）导入/定义，本 fragment 内未导入
  → 渲染期 NameError，被 safe_fragment 隔离成「🧯 ⚠️ 每日选股回测 加载失败（NameError）」。
- fragment_strong_bull：点「运行强势上涨股批量回测」后，按钮回调里
  st.session_state["sb_with_market"] = sb_with_market 重写了复选框自身的 session key
  → StreamlitAPIException（widget key 实例化后不可改），表现同上为
  「🧯 ⚠️ 强势上涨股批量回测 加载失败（StreamlitAPIException）」。

本测试预置 session_state（让分支真正跑起来），断言不再出现对应错误卡片。
冒烟测试 test_pages_smoke 只覆盖「无结果」的干净加载路径，抓不到这类状态依赖崩溃。
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
_PAGE = os.path.join(_PROJECT_ROOT, "pages", "30_策略回测.py")

from modules.site_config import TEST_SMOKE_SECRET

_FAKE_TOKEN = jwt.encode(
    {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
    TEST_SMOKE_SECRET, algorithm="HS256",
)


def _offline(monkeypatch):
    import requests as _r
    import urllib.request as _u
    import urllib.error as _ue

    def _boom(*a, **k):
        raise _r.exceptions.ConnectionError("offline stub")

    for _t in (_r, _r.Session):
        for _a in ("get", "post", "request"):
            try:
                monkeypatch.setattr(_t, _a, _boom, raising=True)
            except AttributeError:
                pass
    monkeypatch.setattr(_u, "urlopen", lambda *a, **k: (_ue.URLError("offline stub")), raising=True)


class _FakePicker:
    """构造一个「能跑通汇总/推荐/曲线渲染」的 picker_result 替身，专门逼出图表分支。"""

    def summary(self):
        return {
            "total_days": 10, "win_pick_pct": 55.0, "win_day_pct": 50.0,
            "total_return_pct": 3.2, "avg_daily_return_pct": 0.3, "total_picks": 50,
        }

    @property
    def returns_df(self):
        return pd.DataFrame({"date": pd.date_range("2026-01-01", periods=5),
                             "cumulative_return_pct": [0.0, 1.0, 2.0, 1.5, 3.2]})

    @property
    def picks_df(self):
        return pd.DataFrame([
            {"date": "2026-01-01", "code": "600519", "name": "贵州茅台", "score": 80,
             "buy_price": 100.0, "sell_price": 102.0, "hold_return_pct": 2.0,
             "rsi2": 5.0, "rsi14": 50.0, "reasons": "强趋势"},
        ])

    def prev_picks(self, n=5):
        return self.picks_df.copy()

    def latest_picks(self, n=5):
        return self.picks_df.copy()


def _authed(at):
    at.session_state["auth_token"] = _FAKE_TOKEN
    at.session_state["auth_user"] = {"id": 1, "username": "demo", "role": "admin"}


class _FakeRunResult:
    """替身：让 Backtester.run 走通 summary() 而不真连网（BaoStock 走 socket，离线桩只挡了 requests/urllib）。"""

    def summary(self):
        return {
            "win_rate_pct": 60.0, "total_return_pct": 5.0, "max_drawdown_pct": 8.0,
            "trade_count": 12, "sharpe_ratio": 1.2,
        }


def _stub_backtester_run(monkeypatch):
    from modules.backtest import Backtester

    def _fake_run(self, *a, **k):
        return _FakeRunResult()

    monkeypatch.setattr(Backtester, "run", _fake_run, raising=True)


def _err_texts(at) -> list[str]:
    out = []
    try:
        for w in at.error:
            out.append(getattr(w, "value", str(w)))
    except Exception:
        pass
    return out


def test_daily_picker_renders_with_result_no_nameerror(monkeypatch):
    """每日选股回测有结果时，累计收益曲线分支不再 NameError。"""
    _offline(monkeypatch)
    at = AppTest.from_file(_PAGE, default_timeout=120)
    _authed(at)
    at.session_state["picker_result"] = _FakePicker()
    at.run()

    errs = _err_texts(at)
    bad = [e for e in errs if "每日选股回测" in e and "NameError" in e]
    assert not bad, f"每日选股回测仍渲染 NameError 隔离卡片: {errs}"
    assert not at.exception, f"每日选股回测抛未捕获异常: {[str(e) for e in at.exception]}"
    # 正向确认：图表/汇总分支确实跑通（「累计收益」标题出现）
    joined = " ".join(getattr(w, "value", "") for w in at.markdown)
    assert "累计收益" in joined, "每日选股回测汇总/曲线分支未正常渲染"


def test_strong_bull_run_button_no_streamlit_api_exception(monkeypatch):
    """点「运行强势上涨股批量回测」后，按钮回调不再因重写复选框 session key 而 StreamlitAPIException。"""
    _offline(monkeypatch)
    _stub_backtester_run(monkeypatch)
    at = AppTest.from_file(_PAGE, default_timeout=120)
    _authed(at)
    at.run()  # 先加载页面，建立 widget 与 session 上下文
    # 不勾选「全市场基准」（默认 False），直接点运行按钮
    at.button("sb_run").click()
    at.run()

    errs = _err_texts(at)
    bad = [e for e in errs if "强势上涨股批量回测" in e and "StreamlitAPIException" in e]
    assert not bad, f"强势上涨股批量回测仍渲染 StreamlitAPIException 隔离卡片: {errs}"
    assert not at.exception, f"强势上涨股批量回测抛未捕获异常: {[str(e) for e in at.exception]}"
