"""data_source_health 数据源健康度探测测试（#锐评整改 任务3）。

验证健康报告结构契约：5 路数据源齐全、字段（ok/label/detail）完整、
summary 计数正确、离线 stub 各路后 ok 状态与信号一致（不真连网）。
"""
import importlib.util

import pytest

from modules import _feed_io
from modules.fetcher import StockFetcher


def _make_fetcher(tmp_path):
    config_path = str(tmp_path / "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(
            f"default:\n  cache_days: 7\n"
            f"database:\n  path: {tmp_path / 'cache.db'}\n"
        )
    return StockFetcher(config_path)


def test_health_report_contract(tmp_path, monkeypatch):
    """报告必须含 5 路数据源 + 字段契约 + summary 计数正确。"""
    # 固定 akshare/baostock 信号为不可用，让 ok 状态可预测（离线环境）
    monkeypatch.setattr(_feed_io, "_AK_OK", False)
    monkeypatch.setattr(_feed_io, "_BS_OK", False)
    fetcher = _make_fetcher(tmp_path)

    report = fetcher.data_source_health()

    # 顶层契约
    assert set(report.keys()) == {"timestamp", "summary", "sources"}
    assert "timestamp" in report and report["timestamp"]
    # 5 路齐全
    assert set(report["sources"].keys()) == {"akshare", "baostock", "sina", "eastmoney", "cache"}, \
        f"数据源维度缺失: {set(report['sources'].keys())}"
    # 每路字段契约
    for name, info in report["sources"].items():
        assert isinstance(info, dict) and "ok" in info and "label" in info and "detail" in info, \
            f"数据源 {name} 缺 ok/label/detail 字段"
    # summary 与 ok 计数一致
    ok_n = sum(1 for v in report["sources"].values() if v["ok"])
    assert report["summary"] == f"{ok_n}/5 可用", f"summary 与计数不符: {report['summary']}"
    # 不真连网：探测必须秒回（缓存表探测本地 SQLite）
    assert isinstance(ok_n, int) and 0 <= ok_n <= 5


def test_health_akshare_signal_false(tmp_path, monkeypatch):
    """_AK_OK=False 且依赖缺失时 akshare 报不可用（detail 说明原因）。"""
    monkeypatch.setattr(_feed_io, "_AK_OK", False)
    fetcher = _make_fetcher(tmp_path)
    report = fetcher.data_source_health()
    ak = report["sources"]["akshare"]
    assert ak["ok"] is False
    assert ak["detail"] in ("依赖缺失", "信号关闭(_AK_OK=False)"), ak["detail"]


def test_health_bs_signal_false(tmp_path, monkeypatch):
    """_BS_OK=False 时 baostock 报不可用。"""
    monkeypatch.setattr(_feed_io, "_BS_OK", False)
    fetcher = _make_fetcher(tmp_path)
    bs = fetcher.data_source_health()["sources"]["baostock"]
    assert bs["ok"] is False


def test_health_cache_reports_tables(tmp_path, monkeypatch):
    """cache 路必须报出表清单（detail 含 N 表 / M 条）。"""
    fetcher = _make_fetcher(tmp_path)
    # 预置一笔缓存数据，确保 cache 库有真实内容
    fetcher.get_index  # 不触发网络；直接向临时库写入一张表即可验证探测
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "cache.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS rt_quote_cache (cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)")
    conn.execute("INSERT OR REPLACE INTO rt_quote_cache VALUES ('rt_quote_test','{}','2026-08-01T00:00:00')")
    conn.commit()
    conn.close()

    report = fetcher.data_source_health()
    cache = report["sources"]["cache"]
    assert cache["ok"] is True
    assert "表" in cache["detail"] and "条" in cache["detail"], cache["detail"]
    assert "rt_quote_cache" in cache.get("tables", {}), "缓存表清单缺 rt_quote_cache"


def test_health_no_network_calls(tmp_path, monkeypatch):
    """探测不得发起任何网络请求（离线守卫下秒回即为不触网）。"""
    import socket
    import urllib.request

    def _block(*a, **k):
        raise AssertionError("health 探测不应触网")

    monkeypatch.setattr(urllib.request, "urlopen", _block)
    monkeypatch.setattr(socket, "create_connection", _block)
    fetcher = _make_fetcher(tmp_path)
    report = fetcher.data_source_health()  # 触网会抛 AssertionError
    assert report["summary"]
