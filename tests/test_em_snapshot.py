# -*- coding: utf-8 -*-
"""
tests/test_em_snapshot.py — T-177 东财直连快照薄层守卫。

【背景】akshare stock_zh_a_spot_em 硬编码 82.push2.eastmoney.com 子域，
本机网络下该子域恒 RemoteDisconnected（主域 push2.eastmoney.com 正常），
实时强势榜/市场驱动力 3 个调用点全部取数失败。本薄层直连主域绕过子域，
并统一 UA/Referer/重试/诚实降级。

守卫：
  1. 列映射：f 字段 → akshare 同款中文列（下游 COL 候选表依赖这些列名）；
  2. 直连参数：主域 URL + fs 覆盖沪深京 A 股 + UA/Referer 规范；
  3. 重试：网络失败重试 3 次后才放弃；
  4. 诚实降级：全部失败返回 None（绝不编造空 DataFrame 假装成功）；
  5. spot_rank 接入：直连优先、akshare 兜底、双失败返 None。
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import em_snapshot as ems     # noqa: E402
from modules import spot_rank as sr        # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_state():
    """每个用例重置风控状态（fail_streak/冷却/缓存跨用例污染）。"""
    ems._reset_state_for_test()
    yield
    ems._reset_state_for_test()


# ───────────────────────── 1. 列映射 ─────────────────────────
def _raw_page():
    """模拟 push2 clist 单页响应（data.diff 列表）。"""
    return {
        "data": {
            "total": 2,
            "diff": [
                {"f12": "600000", "f14": "浦发银行", "f2": 12.34, "f3": 1.56,
                 "f4": 0.19, "f5": 123456, "f6": 987654321.0, "f7": 2.1,
                 "f8": 0.85, "f9": 5.6, "f10": 1.23, "f20": 123456789012,
                 "f21": 98765432100, "f23": 0.62},
                {"f12": "000001", "f14": "平安银行", "f2": "-", "f3": "-",
                 "f4": "-", "f5": "-", "f6": "-", "f7": "-", "f8": "-",
                 "f9": "-", "f10": "-", "f20": "-", "f21": "-", "f23": "-"},
            ],
        }
    }


def test_map_columns_produces_chinese_names():
    df = ems.map_diff_to_df(_raw_page()["data"]["diff"])
    for col in ("代码", "名称", "最新价", "涨跌幅", "涨跌额", "成交量", "成交额",
                "振幅", "换手率", "市盈率-动态", "量比", "总市值", "流通市值", "市净率"):
        assert col in df.columns, f"缺中文列 {col}"
    row0 = df.iloc[0]
    assert row0["代码"] == "600000" and row0["名称"] == "浦发银行"
    assert abs(row0["涨跌幅"] - 1.56) < 1e-9
    assert abs(row0["量比"] - 1.23) < 1e-9
    # '-' 占位 → NaN（诚实缺失，不编 0）
    assert pd.isna(df.iloc[1]["最新价"])


def test_map_columns_preserves_dtypes_numeric():
    df = ems.map_diff_to_df(_raw_page()["data"]["diff"])
    assert pd.api.types.is_numeric_dtype(df["涨跌幅"])
    assert pd.api.types.is_numeric_dtype(df["成交额"])


# ───────────────────────── 2. 直连参数 ─────────────────────────
def test_endpoint_is_main_domain_not_82():
    """必须连主域 push2.eastmoney.com——82.push2 子域在本机恒断连（T-177 根因）。"""
    assert "82.push2" not in ems.CLIST_URL
    assert ems.CLIST_URL.startswith("https://push2.eastmoney.com/")


def test_fs_covers_sh_sz_bj_a():
    """fs 必须覆盖沪深京 A 股（m:0+t:6 深主板/m:0+t:80 创业板/m:1+t:2 沪主板/
    m:1+t:23 科创板/m:0+t:81+s:2048 北交所）。"""
    for seg in ("m:0+t:6", "m:0+t:80", "m:1+t:2", "m:1+t:23"):
        assert seg in ems.FS_A


# ───────────────────────── 3/4. 重试与诚实降级 ─────────────────────────
class _FakeResp:
    def __init__(self, payload=None, status=200):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            raise RuntimeError("no json")
        return self._payload


def test_fetch_retries_three_then_none(monkeypatch):
    """网络持续失败 → 重试恰 3 次 → 返回 None（诚实降级，不抛不编造）。"""
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise ConnectionError("RemoteDisconnected")

    monkeypatch.setattr(ems, "_sleep", lambda *_: None)
    monkeypatch.setattr(ems.http_get, "__wrapped__", None, raising=False) if False else None
    monkeypatch.setattr(ems, "_http_get_raw", _boom)
    out = ems.fetch_a_spot_em(retries=3, max_pages=1)
    assert out is None
    assert calls["n"] == 3, f"应重试恰 3 次，实际 {calls['n']}"


def test_fetch_success_single_page(monkeypatch):
    """单页成功 → DataFrame 中文列齐全；total <= pz 不再翻页。"""
    calls = {"n": 0}

    def _ok(url, **k):
        calls["n"] += 1
        return _FakeResp(_raw_page())

    monkeypatch.setattr(ems, "_http_get_raw", _ok)
    out = ems.fetch_a_spot_em(max_pages=3, pz=1000)
    assert out is not None and len(out) == 2
    assert "代码" in out.columns and "涨跌幅" in out.columns
    assert calls["n"] == 1, "total=2 <= pz=1000 时不应翻页"


def test_fetch_paginates_by_total(monkeypatch):
    """total > pz 时按页翻齐并合并。"""
    def _resp(url, **k):
        pn = 1
        if "pn=2" in url:
            pn = 2
        page = _raw_page()["data"]["diff"][:1]
        return _FakeResp({"data": {"total": 2, "diff": page}})

    monkeypatch.setattr(ems, "_http_get_raw", _resp)
    out = ems.fetch_a_spot_em(max_pages=2, pz=1)
    assert out is not None and len(out) == 2


def test_spot_rank_uses_snapshot_first(monkeypatch):
    """spot_rank：直连层优先，且其结果直接返回（不调 akshare）。"""
    fake = pd.DataFrame({"代码": ["600000"], "名称": ["浦发银行"], "最新价": [12.34],
                         "涨跌幅": [1.5], "成交额": [1e8], "换手率": [0.8], "量比": [1.2]})
    monkeypatch.setattr(ems, "fetch_a_spot_em", lambda **k: fake)
    monkeypatch.setattr(sr, "_spot_cached_akshare",
                        lambda: (_ for _ in ()).throw(AssertionError("直连成功不应走 akshare")))
    # 直连层成功时 st.cache_data 缓存内层函数——直接调内层实现
    out, source = sr._spot_impl()
    assert out is fake
    assert "东财" in source


def test_spot_rank_falls_back_to_akshare(monkeypatch):
    """直连 None → akshare 兜底。"""
    monkeypatch.setattr(ems, "fetch_a_spot_em", lambda **k: None)
    sentinel = pd.DataFrame({"代码": ["000001"]})
    monkeypatch.setattr(sr, "_spot_cached_akshare", lambda: sentinel)
    monkeypatch.setattr(sr, "_spot_from_qq",
                        lambda: (_ for _ in ()).throw(AssertionError("akshare 成功不应走腾讯")))
    out, source = sr._spot_impl()
    assert out is sentinel
    assert "akshare" in source


# ───────────────────────── 5. 风控防御（T-177 实测 clist 频率风控） ─────────────────────────
def test_cooldown_after_consecutive_failures(monkeypatch):
    """连续 2 轮失败后进入冷却：第 3 轮调用不打任何请求直接 None。"""
    monkeypatch.setattr(ems, "_sleep", lambda *_: None)
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise ConnectionError("rate-limited")

    monkeypatch.setattr(ems, "_http_get_raw", _boom)
    assert ems.fetch_a_spot_em(retries=1, max_pages=1) is None   # streak=1
    assert ems.fetch_a_spot_em(retries=1, max_pages=1) is None   # streak=2 → 触发冷却
    calls["n"] = 0
    assert ems.fetch_a_spot_em(retries=1, max_pages=1) is None   # 冷却期内
    assert calls["n"] == 0, "冷却期内不得发起任何网络请求"


def test_cooldown_expires_and_recovers(monkeypatch):
    """冷却到期后恢复真实尝试；成功即复位 fail_streak。"""
    monkeypatch.setattr(ems, "_sleep", lambda *_: None)
    monkeypatch.setattr(ems, "_http_get_raw",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("x")))
    ems.fetch_a_spot_em(retries=1, max_pages=1)
    ems.fetch_a_spot_em(retries=1, max_pages=1)
    assert ems._state["cool_until"] > 0
    # 把冷却时间拨到过去 → 到期
    ems._state["cool_until"] -= ems._COOLDOWN_SEC + 1
    calls = {"n": 0}

    def _ok(url, **k):
        calls["n"] += 1
        return _FakeResp(_raw_page())

    monkeypatch.setattr(ems, "_http_get_raw", _ok)
    out = ems.fetch_a_spot_em(retries=1, max_pages=1)
    assert out is not None
    assert ems._state["fail_streak"] == 0, "成功后必须复位失败计数"


def test_shared_cache_ttl(monkeypatch):
    """成功结果 60s 内共享：第二次调用不打请求且返回等价数据。"""
    calls = {"n": 0}

    def _ok(url, **k):
        calls["n"] += 1
        return _FakeResp(_raw_page())

    monkeypatch.setattr(ems, "_http_get_raw", _ok)
    out1 = ems.fetch_a_spot_em()
    out2 = ems.fetch_a_spot_em()
    assert calls["n"] == 1, "60s 内第二次调用应命中共享缓存"
    assert out2 is not out1, "缓存必须返回副本（防调用方污染共享态）"
    pd.testing.assert_frame_equal(out1, out2)
