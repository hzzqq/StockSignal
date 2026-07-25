"""page_widgets 纯助手函数 / 交易时段边界回归测试（无网依赖）。

覆盖：
- is_trading_now / current_trading_session（含周末、午休、开收盘边界；新能力 current_trading_session）
- 隐式 bug 修复：交易时段判定改用北京时间(_now_cst)，服务器非 CST 时不再错位
- 数值格式化 _fmt_yi / _fmt_num / _fmt_pct / _delta_color / _delta_html（NaN / None 兜底）
"""
from datetime import datetime

import modules.page_widgets as PW


# ── 交易时段 ──────────────────────────────────────────────
def test_is_trading_now_weekend():
    # 2026-07-25 是周六
    assert PW.is_trading_now(datetime(2026, 7, 25, 10, 0)) is False


def test_is_trading_now_morning():
    # 2026-07-27 周一 10:00
    assert PW.is_trading_now(datetime(2026, 7, 27, 10, 0)) is True


def test_is_trading_now_lunch():
    # 周一 11:45 午休
    assert PW.is_trading_now(datetime(2026, 7, 27, 11, 45)) is False


def test_is_trading_now_afternoon():
    # 周一 14:00 午盘
    assert PW.is_trading_now(datetime(2026, 7, 27, 14, 0)) is True


def test_is_trading_now_pre_open():
    # 周一 08:00 盘前
    assert PW.is_trading_now(datetime(2026, 7, 27, 8, 0)) is False


def test_is_trading_now_after_close():
    # 周一 15:30 收盘后
    assert PW.is_trading_now(datetime(2026, 7, 27, 15, 30)) is False


def test_is_trading_now_boundary_inclusive():
    # 11:30 收上午盘、13:00 开下午盘（边界包含）
    assert PW.is_trading_now(datetime(2026, 7, 27, 11, 30)) is True
    assert PW.is_trading_now(datetime(2026, 7, 27, 13, 0)) is True


def test_current_trading_session_labels():
    assert PW.current_trading_session(datetime(2026, 7, 25, 10, 0)) == "weekend"
    assert PW.current_trading_session(datetime(2026, 7, 27, 8, 0)) == "pre_open"
    assert PW.current_trading_session(datetime(2026, 7, 27, 10, 0)) == "morning"
    assert PW.current_trading_session(datetime(2026, 7, 27, 11, 45)) == "lunch"
    assert PW.current_trading_session(datetime(2026, 7, 27, 14, 0)) == "afternoon"
    assert PW.current_trading_session(datetime(2026, 7, 27, 15, 30)) == "after_close"


def test_is_trading_now_default_no_arg():
    # 不带参数必须返回 bool（不抛异常，依赖 _now_cst）
    assert isinstance(PW.is_trading_now(), bool)


# ── 数值格式化兜底 ────────────────────────────────────────
def test_fmt_yi():
    assert PW._fmt_yi(None) == "—"
    assert PW._fmt_yi(float("nan")) == "—"
    assert PW._fmt_yi(1e8) == "1.00亿"
    assert PW._fmt_yi(1e4) == "1.0万"
    assert PW._fmt_yi(999) == "999"


def test_fmt_num():
    assert PW._fmt_num(None) == "—"
    assert PW._fmt_num("abc") == "—"
    assert PW._fmt_num(3.14159) == "3.14"
    assert PW._fmt_num(3.1, sign=True) == "+3.10"
    assert PW._fmt_num(3.1, nd=0) == "3"


def test_fmt_pct():
    assert PW._fmt_pct(None) == "—"
    assert PW._fmt_pct(0.1234) == "+12.34%"
    assert PW._fmt_pct(0.5, sign=False) == "50.00%"
    assert PW._fmt_pct(float("nan")) == "—"


def test_delta_color():
    assert PW._delta_color(0) == ""
    assert PW._delta_color(None) == ""
    assert PW._delta_color(1.0) == PW.UP
    assert PW._delta_color(-1.0) == PW.DOWN
    # inverse：跌幅越小越好 → 下跌变为 UP
    assert PW._delta_color(-1.0, inverse=True) == PW.UP


def test_delta_html():
    assert "—" in PW._delta_html(None)
    assert "0.00%" in PW._delta_html(0.0)
    assert PW.UP in PW._delta_html(0.01)
    assert PW.DOWN in PW._delta_html(-0.01)
