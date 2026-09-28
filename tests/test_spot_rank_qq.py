# -*- coding: utf-8 -*-
"""
tests/test_spot_rank_qq.py — T-178 腾讯应急备源守卫。

【契约】东财 clist 风控全封期间（实测 >21h），强势榜第三层兜底：
  ems 直连 → akshare → 腾讯 qt 批量（本地代码库 + 400 只/批）。
守卫：解析索引与单位换算 / 前缀规则 / 三层链次序 / 诚实阈值（覆盖不足不装全市场）/
  数据源标注。纯 mock，不触网。
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
def _fresh_states():
    ems._reset_state_for_test()
    sr._reset_qq_state_for_test()
    sr._spot_cached_with_source.clear()   # st.cache_data 跨测试串味防线
    yield
    ems._reset_state_for_test()
    sr._reset_qq_state_for_test()
    sr._spot_cached_with_source.clear()


# ── 1. 前缀规则 ──
def test_qq_prefix_rules():
    assert sr._qq_prefix("600000") == "sh600000"
    assert sr._qq_prefix("688512") == "sh688512"
    assert sr._qq_prefix("000001") == "sz000001"
    assert sr._qq_prefix("300750") == "sz300750"
    assert sr._qq_prefix("920992") == "bj920992"
    assert sr._qq_prefix("830799") == "bj830799"
    assert sr._qq_prefix("430047") == "bj430047"


# ── 2. 解析与单位换算 ──
def _qq_line(code="600000", name="浦发银行", price="9.14", pct="1.56",
             amt_wan="79979", turnover="0.26", vol_ratio="3.16"):
    """按实测索引造一行腾讯响应（v_sh600000="..."）。"""
    f = [""] * 52
    f[1], f[2], f[3] = name, code, price
    f[32], f[37], f[38], f[49] = pct, amt_wan, turnover, vol_ratio
    return f'v_sh{code}="{"~".join(f)}";'


def test_parse_qq_batch_columns_and_units():
    text = _qq_line() + _qq_line(code="300750", name="宁德时代", price="188.0",
                                 pct="2.10", amt_wan="500000", turnover="1.2",
                                 vol_ratio="1.05")
    df = sr._parse_qq_batch(text)
    assert len(df) == 2
    for col in ("代码", "名称", "最新价", "涨跌幅", "成交额", "换手率", "量比"):
        assert col in df.columns, f"缺列 {col}"
    r0 = df.iloc[0]
    assert r0["代码"] == "600000" and r0["名称"] == "浦发银行"
    assert abs(r0["成交额"] - 79979 * 1e4) < 1e-6, "腾讯成交额单位为万，必须换算成元与东财列对齐"
    assert abs(r0["量比"] - 3.16) < 1e-9


def test_parse_qq_batch_skips_garbage():
    """坏行/无效前缀行跳过，不炸不编造。"""
    text = "pv_none=\"1\";" + _qq_line()
    df = sr._parse_qq_batch(text)
    assert len(df) == 1


def test_parse_qq_batch_numeric_dtypes():
    df = sr._parse_qq_batch(_qq_line())
    for col in ("最新价", "涨跌幅", "成交额", "换手率", "量比"):
        assert pd.api.types.is_numeric_dtype(df[col]), f"{col} 应为数值列"


# ── 3. 应急层：分批 + 诚实阈值 ──
class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200
        self.content = text.encode("gbk", errors="replace")  # 实现走 content.decode("gbk")

    def raise_for_status(self):
        return None


def test_spot_from_qq_batches_and_threshold(monkeypatch):
    """分批拉取合并；覆盖不足（<阈值）按诚实口径返回 None。"""
    monkeypatch.setattr(sr, "_qq_codes", lambda: [f"{600000 + i}" for i in range(120)])
    calls = {"urls": []}

    def _fake_get(url, **k):
        calls["urls"].append(url)
        # 按批内真实代码回包（1 行/批 → 共 120 行 < 100 阈值）
        return _FakeResp(_qq_line(code=url.split("q=")[1].split(",")[0][2:]))

    monkeypatch.setattr(sr, "_qq_get_raw", _fake_get)
    monkeypatch.setattr(sr, "_QQ_MIN_ROWS", 100)
    monkeypatch.setattr(sr, "_QQ_BATCH", 100)   # 缩批验证分批逻辑（默认 400）
    out = sr._spot_from_qq()
    assert out is None, "覆盖不足必须 None（不装全市场）"
    assert len(calls["urls"]) == 2, "120 只/批 100 → 2 批"


def test_spot_from_qq_success(monkeypatch):
    codes = [f"{600000 + i}" for i in range(1200)]
    monkeypatch.setattr(sr, "_qq_codes", lambda: codes)
    monkeypatch.setattr(sr, "_QQ_MIN_ROWS", 1000)

    def _fake_get(url, **k):
        # 按批内真实代码逐只回包（模拟腾讯行为：所查即所回）
        qcodes = url.split("q=")[1].split(",")
        return _FakeResp("".join(_qq_line(code=c) for c in qcodes))

    monkeypatch.setattr(sr, "_qq_get_raw", _fake_get)
    out = sr._spot_from_qq()
    assert out is not None and len(out) == 1200


def test_spot_from_qq_cooling(monkeypatch):
    """冷却期内零请求（与 em_snapshot 同防风控语义）。"""
    sr._qq_state["cool_until"] = 9e18
    calls = {"n": 0}

    def _fake_get(url, **k):
        calls["n"] += 1
        return _FakeResp(_qq_line())

    monkeypatch.setattr(sr, "_qq_get_raw", _fake_get)
    monkeypatch.setattr(sr, "_qq_codes", lambda: ["sh600000"])
    assert sr._spot_from_qq() is None
    assert calls["n"] == 0, "冷却期内不得打请求"


# ── 4. 三层链次序 ──
def test_impl_third_layer_when_both_em_fail(monkeypatch):
    """ems None + akshare 抛异常 → 腾讯应急层接住。"""
    monkeypatch.setattr(ems, "fetch_a_spot_em", lambda **k: None)

    def _boom():
        raise ConnectionError("82.push2 dead")

    monkeypatch.setattr(sr, "_spot_cached_akshare", _boom)
    sentinel = pd.DataFrame({"代码": ["600000"], "名称": ["浦发银行"], "最新价": [9.14],
                             "涨跌幅": [1.56], "成交额": [79979 * 1e4],
                             "换手率": [0.26], "量比": [3.16]})
    monkeypatch.setattr(sr, "_spot_from_qq", lambda: sentinel)
    out, source = sr.load_spot_with_source()
    assert out is sentinel
    assert "腾讯" in source


def test_impl_prefers_em_snapshot(monkeypatch):
    """直连层成功 → 不走 akshare/腾讯。"""
    fake = pd.DataFrame({"代码": ["600000"]})
    monkeypatch.setattr(ems, "fetch_a_spot_em", lambda **k: fake)

    def _must_not():
        raise AssertionError("直连成功不应走兜底")

    monkeypatch.setattr(sr, "_spot_cached_akshare", _must_not)
    monkeypatch.setattr(sr, "_spot_from_qq", _must_not)
    out, source = sr.load_spot_with_source()
    assert out is fake
    assert "东财" in source


def test_impl_all_fail_returns_none_unavailable(monkeypatch):
    """三源全失败 → (None, "不可用")，页面按未就绪降级（不抛、不编造）。"""
    monkeypatch.setattr(ems, "fetch_a_spot_em", lambda **k: None)

    def _boom():
        raise ConnectionError("dead")

    monkeypatch.setattr(sr, "_spot_cached_akshare", _boom)
    monkeypatch.setattr(sr, "_spot_from_qq", lambda: None)
    out, source = sr.load_spot_with_source()
    assert out is None
    assert "不可用" in source
