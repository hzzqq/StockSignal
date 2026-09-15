"""tests/test_lhb.py — 龙虎榜模块守卫。

重点锁两条红线：
  ① 净买额列匹配不到 → summarize 返回 None（**不用错列编出资金方向**）
  ② 取数失败/非交易日 → fetch_lhb 返回 None（不臆造明细）

以及一条正向：列名按子串匹配能正确挑中净买额列，并给出正确的多空排名。
测试注入假的 akshare，不触网。
"""
import sys

import pandas as pd
import pytest

from modules import lhb


class _FakeAk:
    def __init__(self, df=None, raise_exc=False):
        self.df = df
        self.raise_exc = raise_exc
        self.calls = []

    def stock_lhb_detail_em(self, start_date=None, end_date=None):
        self.calls.append((start_date, end_date))
        if self.raise_exc:
            raise RuntimeError("上游不可用")
        return self.df


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "代码": ["000001", "000002", "600000"],
        "名称": ["A", "B", "C"],
        "上榜原因": ["日涨幅偏离值达7%", "连续三个交易日", "换手率达20%"],
        "涨跌幅": [10.0, -5.0, 3.2],
        "龙虎榜成交额": [1e8, 2e8, 3e8],
        "龙虎榜净买额": [5e7, -8e7, 1e7],
    })


def test_find_col_by_substring():
    df = _sample_df()
    assert lhb.find_col(df, lhb.NET_BUY_CANDS) == "龙虎榜净买额"
    assert lhb.find_col(df, lhb.CODE_CANDS) == "代码"
    assert lhb.find_col(df, ("不存在的列",)) is None


def test_fetch_lhb_returns_dataframe(monkeypatch):
    fake = _FakeAk(df=_sample_df())
    monkeypatch.setitem(sys.modules, "akshare", fake)
    df = lhb.fetch_lhb("20260915")
    assert df is not None and len(df) == 3
    assert fake.calls == [("20260915", "20260915")], "起止日期都应是传入的交易日"


def test_fetch_lhb_returns_none_on_exception(monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare", _FakeAk(raise_exc=True))
    assert lhb.fetch_lhb("20260915") is None


def test_fetch_lhb_returns_none_when_empty(monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare",
                        _FakeAk(df=pd.DataFrame()))
    assert lhb.fetch_lhb("20260915") is None


def test_summarize_ranks_buy_and_sell_correctly():
    """净买额最大的排 buy_top 第一，最小的（净卖最多）排 sell_top 第一。"""
    s = lhb.summarize(_sample_df())
    assert s is not None
    assert s["count"] == 3
    assert s["net_col"] == "龙虎榜净买额"
    assert list(s["buy_top"]["代码"]) == ["000001", "600000", "000002"]
    assert list(s["sell_top"]["代码"]) == ["000002", "600000", "000001"]
    assert abs(s["net_sum"] - (5e7 - 8e7 + 1e7)) < 1


def test_summarize_returns_none_without_net_buy_column():
    """红线：匹配不到净买额列就返回 None，绝不猜列、绝不编排名。"""
    df = _sample_df().drop(columns=["龙虎榜净买额"])
    assert lhb.summarize(df) is None


def test_summarize_returns_none_on_empty():
    assert lhb.summarize(pd.DataFrame()) is None
    assert lhb.summarize(None) is None
