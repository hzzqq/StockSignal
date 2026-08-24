"""P0-1 回归测试：验证 fetcher/session/market_drivers 的裸吞 except Exception 已接 logger.warning。

注意：modules/_feed_io.py 中的 logger 设置 propagate=False 并自带 StreamHandler，
因此 pytest 的 caplog 无法捕获；改用 monkeypatch 拦截 logger.warning 方法本身。
"""
import pytest


def test_fetcher_data_source_health_logs_importlib_failure(monkeypatch):
    """data_source_health() 中 _spec() 捕获 importlib 异常时应打 warning。"""
    from modules.fetcher import StockFetcher
    import importlib.util

    warnings = []
    monkeypatch.setattr(
        "modules.fetcher.logger.warning", lambda msg, *a, **k: warnings.append(msg)
    )

    def _boom(*args, **kwargs):
        raise ValueError("spec boom")

    monkeypatch.setattr(importlib.util, "find_spec", _boom)

    result = StockFetcher().data_source_health()
    assert isinstance(result, dict)
    assert "sources" in result
    assert any("spec boom" in w for w in warnings)


def test_session_api_request_logs_network_error(monkeypatch):
    """_api_request 在 requests 网络错误兜底时应打 logger.warning。"""
    import requests
    from modules.session import _api_request

    class _DummyExc(requests.exceptions.RequestException):
        pass

    warnings = []
    monkeypatch.setattr(
        "modules.session.logger.warning", lambda msg, *a, **k: warnings.append(msg)
    )
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: (_ for _ in ()).throw(_DummyExc("network down"))
    )
    monkeypatch.setattr("time.sleep", lambda x: None)

    status, body = _api_request("GET", "/test")
    assert status == -1
    assert "network down" in body["message"]
    assert any("network down" in w for w in warnings)


def test_market_drivers_read_last_cached_logs_db_error(monkeypatch):
    """_read_last_cached_value 在 SQLite 读取异常时应打 warning 并返回 None。"""
    import sqlite3
    from modules.market_drivers import _read_last_cached_value

    warnings = []
    monkeypatch.setattr(
        "modules.market_drivers.logger.warning", lambda msg, *a, **k: warnings.append(msg)
    )
    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db locked"))
    )

    assert _read_last_cached_value("test_key") is None
    assert any("db locked" in w for w in warnings)
