# -*- coding: utf-8 -*-
"""tests/test_health_realtime_probe.py — T-384 数据源真实网络探测守卫。

背景：``data_source_health()`` 一直明确「只做静态/本地探测，不发任何网络请求」
（既有 ``test_health_no_network_calls`` 锁死该契约）。本轮**additive** 扩展：
显式传 ``realtime_probe=True`` 时额外真实探网，结果放独立 ``probe`` 字段。

必须钉住的不变量：
1. 默认（不传参）**零网络、零行为变化**，报告里不得出现 ``probe`` 键；
2. 探针结果如实反映——通就是 True、不通就是 False，**绝不编造**；
3. 单源抛异常 → 该项 ``ok=False`` 且 detail 带异常类型（不静默吞成"无数据"）；
4. 实例未装配 ``_fetch_level`` → 整体诚实降级 ``unavailable``，不伪造四源结论；
5. 顶层 ``ok``/``summary``/``sources`` 契约不受 probe 影响（probe 只加不改）。

mutation 基线：
  - 把 ``realtime_probe`` 默认改成 True → test_default_has_no_probe_key 变红；
  - 探针把异常吞成 ok=True → test_probe_marks_failed_source 变红；
  - 缺 ``_fetch_level`` 时仍返回四源结果 → test_probe_unavailable_without_fetch_level 变红。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import modules.fetcher as fetcher_mod  # noqa: E402
from modules import _feed_io  # noqa: E402
from modules import fetcher_health  # noqa: E402
from modules.fetcher import StockFetcher  # noqa: E402


def _df():
    dates = pd.date_range("2026-10-01", periods=10).strftime("%Y-%m-%d")
    n = len(dates)
    return pd.DataFrame({"date": pd.to_datetime(dates),
                         "open": [10.0] * n, "high": [11.0] * n,
                         "low": [9.0] * n, "close": [10.0] * n,
                         "volume": [1e6] * n})


def _fetcher(tmp_path):
    """最小实例：只装配 data_source_health 需要的 _get_conn。"""
    db = str(tmp_path / "cache.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS rt_quote_cache (cache_key TEXT PRIMARY KEY, "
                 "data_json TEXT, updated_at TEXT)")
    conn.commit()
    conn.close()
    f = StockFetcher.__new__(StockFetcher)
    f._get_conn = lambda: sqlite3.connect(db)  # type: ignore[method-assign]
    return f


def _block_network(monkeypatch):
    """任何真实网络请求都抛 AssertionError（用于证明「没触网」）。"""
    import socket
    import urllib.request

    def _block(*a, **k):
        raise AssertionError("该路径不应触网")

    monkeypatch.setattr(urllib.request, "urlopen", _block)
    monkeypatch.setattr(socket, "create_connection", _block)


# ───────────────────── 1. 默认零网络、零行为变化 ─────────────────────

def test_default_has_no_probe_key(tmp_path, monkeypatch):
    """默认调用不得包含 probe 字段（additive 字段只在显式要求时出现）。"""
    _block_network(monkeypatch)
    f = _fetcher(tmp_path)
    report = f.data_source_health()
    assert set(report.keys()) == {"timestamp", "summary", "sources"}, \
        f"默认报告键集被改动: {sorted(report.keys())}"
    assert "probe" not in report, "默认路径不得探网（probe 字段应仅显式触发时出现）"


# ───────────────────── 2. 探针如实反映各源可用性 ─────────────────────

def test_probe_marks_failed_source(tmp_path, monkeypatch):
    """L3 通、其余不通 → probe 必须如实区分（通的 True、不通的 False）。"""
    f = _fetcher(tmp_path)

    def _level(self, level, symbol, start, end, adjust):
        if level == "L3":
            return _df(), None
        return None, f"{level}: 连接失败"

    f._fetch_level = _level.__get__(f, StockFetcher)  # type: ignore[method-assign]
    report = f.data_source_health(realtime_probe=True)

    probe = report["probe"]
    assert set(probe.keys()) == {"L1", "L2", "L3", "L4"}, f"探针必须覆盖四源: {sorted(probe)}"
    assert probe["L3"]["ok"] is True, "通了却报不通"
    for lv in ("L1", "L2", "L4"):
        assert probe[lv]["ok"] is False, f"{lv} 不通却谎报可用"
        assert "连接失败" in probe[lv]["detail"]
    assert all(probe[lv]["latency_ms"] >= 0 for lv in probe), "耗时必须为非负整数"


def test_probe_exception_is_reported_not_swallowed(tmp_path, monkeypatch):
    """单源抛异常 → 该项 ok=False 且 detail 含异常类型（不得静默成「无数据」）。"""
    f = _fetcher(tmp_path)

    def _level(self, level, symbol, start, end, adjust):
        if level == "L2":
            raise RuntimeError("boom")
        return _df(), None

    f._fetch_level = _level.__get__(f, StockFetcher)  # type: ignore[method-assign]
    probe = f.data_source_health(realtime_probe=True)["probe"]
    assert probe["L2"]["ok"] is False
    assert "RuntimeError" in probe["L2"]["detail"], probe["L2"]["detail"]
    assert probe["L1"]["ok"] is True and probe["L3"]["ok"] is True


# ───────────────────── 3. 能力缺失时诚实降级 ─────────────────────

def test_probe_unavailable_without_fetch_level(tmp_path, monkeypatch):
    """实例未装配 _fetch_level → 整体 unavailable，绝不伪造四源结论。

    注意：真实 StockFetcher 经 MRO 永远带 _fetch_level，所以这里必须用只含
    HealthMixin 的桩类型，才能覆盖「能力缺失」这条诚实降级分支。
    """
    from modules.fetcher_health import HealthMixin

    class _FakeHealth(HealthMixin):
        pass

    fake = _FakeHealth.__new__(_FakeHealth)
    probe = fake._probe_sources_network()
    assert probe.get("status") == "unavailable", f"缺能力却给出结论: {probe}"
    assert "reason" in probe and probe["reason"], "降级必须说明原因"
    assert "L1" not in probe, "不可用状态下不得编造四源结果"


# ───────────────────── 4. 顶层契约不受 probe 影响 ─────────────────────

def test_probe_does_not_change_top_level_contract(tmp_path, monkeypatch):
    """加了 probe 之后，sources / summary / timestamp 结构与计数完全不变。"""
    monkeypatch.setattr(_feed_io, "_AK_OK", False)
    monkeypatch.setattr(_feed_io, "_BS_OK", False)
    f = _fetcher(tmp_path)

    def _level(self, level, symbol, start, end, adjust):
        return None, f"{level}: offline"

    f._fetch_level = _level.__get__(f, StockFetcher)  # type: ignore[method-assign]

    base = f.data_source_health()
    probed = f.data_source_health(realtime_probe=True)

    assert probed["summary"] == base["summary"], "probe 不得改动 summary 计数"
    assert set(probed["sources"]) == set(base["sources"]), "probe 不得增删数据源维度"
    for name in base["sources"]:
        assert probed["sources"][name]["ok"] == base["sources"][name]["ok"], \
            f"{name} 的静态可用性判定被探网结果污染"
        assert probed["sources"][name]["detail"] == base["sources"][name]["detail"]
    assert probed["timestamp"] and base["timestamp"]


# ───────────────────── 5. 方法签名守卫（防默认值被改开） ─────────────────────

def test_realtime_probe_defaults_false():
    """AST 守卫：data_source_health 的 realtime_probe 默认值必须是 False。"""
    import ast

    src = Path(fetcher_health.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "data_source_health")
    arg = next(a for a in fn.args.args if a.arg == "realtime_probe")
    default = fn.args.defaults[fn.args.args.index(arg) - (len(fn.args.args) - len(fn.args.defaults))]
    assert isinstance(default, ast.Constant) and default.value is False, \
        "realtime_probe 默认值必须为 False（否则全站健康探测都会触网）"


# ───────────────────── 6. 异常保真（截图缺陷：大字「不通」+ 小字「无数据」）─────────────────────
# 现状：observe_source 把 ProxyError 记进 SOURCE_METRICS 后返回 None（不抛给调用方），
# _fetch_level 再把 None 一律写成「<源>: 无数据」→ 真实网络故障原因彻底丢失，
# 前端于是出现「不通 / 无数据」自相矛盾，运维无从判断该修什么。
# 已有 test_probe_exception_is_reported_not_swallowed 只覆盖「异常穿透到 _one」，
# 覆盖不到「异常被 observe_source 内部吞掉」这条真实路径，故补以下守卫。


def _mock_swallowed_observe(monkeypatch, detail="ProxyError: Unable to connect to proxy"):
    """精确复现 observe_source 真实行为：内部记异常、返回 None，不向上抛。"""
    import modules.fetcher_kline as fk

    def _observe(source, level, func, validate=None, error_out=None):
        if error_out is not None:
            error_out.append(detail)
        return None

    monkeypatch.setattr(fk, "observe_source", _observe)
    monkeypatch.setattr(fetcher_mod, "_AK_OK", True)


def test_swallowed_akshare_exception_is_not_washed_to_no_data(tmp_path, monkeypatch):
    """L1：真实网络异常必须带出异常类型，不得洗成「无数据」。"""
    f = _fetcher(tmp_path)
    _mock_swallowed_observe(monkeypatch)
    df, err = f._fetch_level("L1", "600519", "2026-10-17", "2026-11-16", "qfq")
    assert df is None
    assert "ProxyError" in (err or ""), f"真实网络异常被洗成「无数据」：{err}"
    assert "无数据" not in (err or ""), f"异常与「无数据」语义矛盾：{err}"


def test_swallowed_eastmoney_exception_is_not_washed_to_no_data(tmp_path, monkeypatch):
    """L4：东方财富同理（实证 L1/L4 共用 push2his.eastmoney.com 上游）。"""
    f = _fetcher(tmp_path)
    _mock_swallowed_observe(monkeypatch, "ProxyError: push2his.eastmoney.com 不可达")
    df, err = f._fetch_level("L4", "600519", "2026-10-17", "2026-11-16", "qfq")
    assert df is None
    assert "ProxyError" in (err or ""), f"真实网络异常被洗成「无数据」：{err}"


def test_truly_empty_response_still_reports_no_data(tmp_path, monkeypatch):
    """真·空响应（无异常）仍诚实写「无数据」，不得反向虚报成故障（防过度告警）。"""
    import modules.fetcher_kline as fk

    f = _fetcher(tmp_path)
    monkeypatch.setattr(
        fk, "observe_source",
        lambda source, level, func, validate=None, error_out=None: None,
    )
    monkeypatch.setattr(fetcher_mod, "_AK_OK", True)
    df, err = f._fetch_level("L1", "600519", "2026-10-17", "2026-11-16", "qfq")
    assert df is None
    assert err == "akshare: 无数据", f"空响应被误报成故障：{err}"


# ───────────────────── 7. 第二层吞噬（各 fetcher 内部 except 也吞异常）─────────────────────


def _fake_urllib(error=None):
    """桩：模拟 _UrllibFetcher.fetch_kline 内部 except 后返回 None 的真实行为。"""
    class _Fake:
        @staticmethod
        def fetch_kline(symbol, start_date, end_date, adjust="qfq",
                        is_index=False, error_out=None):
            if error is not None and error_out is not None:
                error_out.append(error)
            return None

    return _Fake


def test_nested_fetcher_exception_is_not_swallowed(tmp_path, monkeypatch):
    """L4 内层异常（实测 RemoteDisconnected）必须带出，不能只修到 observe_source 这一层。"""
    import modules.fetcher_kline as fk

    f = _fetcher(tmp_path)
    monkeypatch.setattr(
        fk, "_UrllibFetcher",
        _fake_urllib("RemoteDisconnected: Remote end closed connection without response"),
    )
    df, err = f._fetch_level("L4", "600519", "2026-10-17", "2026-11-16", "qfq")
    assert df is None
    assert "RemoteDisconnected" in (err or ""), f"内层异常仍被洗成「无数据」：{err}"


def test_eastmoney_empty_klines_still_reports_no_data(tmp_path, monkeypatch):
    """东方财富真·空 klines（无异常）仍诚实写「无数据」，不反向虚报成故障。"""
    import modules.fetcher_kline as fk

    f = _fetcher(tmp_path)
    monkeypatch.setattr(fk, "_UrllibFetcher", _fake_urllib())
    df, err = f._fetch_level("L4", "600519", "2026-10-17", "2026-11-16", "qfq")
    assert df is None
    assert err == "东方财富: 无数据", f"空响应被误报成故障：{err}"
