"""锁定 _feed_io 的 symbol 转换 / 交易日判断 / 板块校验 / 取数重试（防回归）。

这些是数据源降级链与 K 线抓取正确性的底层契约，纯逻辑、可离线验证，此前无单测。
"""
import datetime as _dt
import urllib.error
import urllib.request

import pandas as pd

import modules._feed_io as fio


def test_symbol_to_secid():
    assert fio._symbol_to_secid("600000") == "1.600000"   # 沪市
    assert fio._symbol_to_secid("000001") == "0.000001"   # 深市
    assert fio._symbol_to_secid("300750") == "0.300750"   # 创业板


def test_index_to_secid():
    assert fio._index_to_secid("000001") == "1.000001"
    assert fio._index_to_secid("399006") == "0.399006"
    assert fio._index_to_secid("999999") == "1.999999"  # 未知 -> 默认沪市


def test_symbol_to_bs():
    assert fio._symbol_to_bs("600000") == "sh.600000"
    assert fio._symbol_to_bs("000001") == "sz.000001"


def test_symbol_to_sina():
    assert fio._symbol_to_sina("600000") == "sh600000"
    assert fio._symbol_to_sina("000001") == "sz000001"


class _FakeDT:
    """整体替换 _feed_io.datetime（builtin datetime 不可 setattr now）。"""

    _fixed = None

    @classmethod
    def now(cls):
        return cls._fixed

    @classmethod
    def strptime(cls, s, fmt):
        return _dt.datetime.strptime(s, fmt)


def _freeze(monkeypatch, y, mo, d, h, mi):
    _FakeDT._fixed = _dt.datetime(y, mo, d, h, mi)
    monkeypatch.setattr(fio, "datetime", _FakeDT)


def test_is_market_open(monkeypatch):
    _freeze(monkeypatch, 2026, 8, 10, 10, 0)   # 周一 10:00 开市
    assert fio._is_market_open() is True
    _freeze(monkeypatch, 2026, 8, 10, 12, 0)   # 周一 12:00 午休
    assert fio._is_market_open() is False
    _freeze(monkeypatch, 2026, 8, 8, 10, 0)    # 周六休市
    assert fio._is_market_open() is False


def test_is_midday_break(monkeypatch):
    _freeze(monkeypatch, 2026, 8, 10, 12, 0)
    assert fio._is_midday_break() is True
    _freeze(monkeypatch, 2026, 8, 10, 10, 0)
    assert fio._is_midday_break() is False


def test_validate_sector_data():
    assert fio._validate_sector_data(None) is False
    assert fio._validate_sector_data(pd.DataFrame()) is False
    assert fio._validate_sector_data(pd.DataFrame({"name": ["a"]})) is False  # 缺 change_pct
    assert fio._validate_sector_data(pd.DataFrame({"change_pct": [1, 2, 3, 4, 5]})) is False  # 全涨
    assert fio._validate_sector_data(pd.DataFrame({"change_pct": [-1, -2, -3, -4, -5]})) is False  # 全跌
    assert fio._validate_sector_data(pd.DataFrame({"change_pct": [1, -2, 3, -4, 5, -1]})) is True  # 混合


def test_safe_urlopen_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        pass

    def _fake(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("connection refused")
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    resp = fio._safe_urlopen("req", timeout=5, retries=3, backoff=0)
    assert isinstance(resp, _Resp)
    assert calls["n"] == 3


def test_safe_urlopen_persistent_failure_raises(monkeypatch):
    def _fake(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    try:
        import pytest
        with pytest.raises(urllib.error.URLError):
            fio._safe_urlopen("req", timeout=5, retries=2, backoff=0)
    except ImportError:
        raise


def test_ensure_login_serialized_under_concurrency(monkeypatch):
    """R77 回归：多线程并发首次 _ensure_login 时，bs.login() 只执行一次。

    背景：_fetch_level 并行竞速会从多个子线程调用 _ensure_login，
    check-then-act 非原子时多线程同时首次 login（BaoStock 会话互踩）。
    """
    import concurrent.futures
    import types
    from types import SimpleNamespace

    import modules._feed_io as fio

    login_calls = {"n": 0}

    class _FakeBs(types.ModuleType):
        def login(self):
            login_calls["n"] += 1
            import time
            time.sleep(0.05)  # 放大竞态窗口
            return SimpleNamespace(error_code="0", error_msg="")

        def logout(self):
            return None

    fake = _FakeBs("baostock")
    # 直接替换 _feed_io 模块级 bs 引用（模块导入时已绑定真实 baostock，
    # 仅 monkeypatch sys.modules 不影响已绑定引用）
    monkeypatch.setattr(fio, "bs", fake)

    # 重置类状态，确保是"首次登录"场景
    monkeypatch.setattr(fio._BaoStockFetcher, "_login_done", False)

    def _call():
        return fio._BaoStockFetcher._ensure_login()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda _: _call(), range(16)))

    assert all(results), "所有线程都应判定登录成功"
    assert login_calls["n"] == 1, f"bs.login() 应只执行 1 次，实际 {login_calls['n']} 次"
    # 清理：恢复类状态，避免影响其他测试
    monkeypatch.undo()
    fio._BaoStockFetcher._login_done = False
