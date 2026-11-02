"""tests/test_event_factor_lhb_source.py — 龙虎榜第三真实源守卫（离线、零网络）。

akshare ``stock_lhb_detail_em`` 的函数签名与返回列名已核实 1.18.64 源码
（「代码/上榜日/龙虎榜净买额/上榜原因」等中文列）。本套注入 fake akshare 隔离
网络，锁死：
  - 方向映射（净买额 >0 看多 62 / <0 看空 38 / 缺失中性 50）
  - 未上榜 = 正常状态 available=False（非错误）
  - 接口异常/缺列 → 诚实降级带原因，绝不造数
  - 代码归一化（600077 / 600077.SH / sh600077 均可命中）
  - get_event_factor 兜底序：P1 miss → 新闻 unavailable → 龙虎榜命中
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from modules import event_factor as ef

_ROOT = Path(__file__).resolve().parents[1]


def _lhb_df():
    return pd.DataFrame({
        "代码": ["600077", "600077", "000001"],
        "名称": ["宋都股份", "宋都股份", "平安银行"],
        "上榜日": pd.to_datetime(["2026-11-01", "2026-11-02", "2026-11-02"]).date,
        "龙虎榜净买额": [-1000000.0, 25000000.0, 5000000.0],
        "上榜原因": ["日振幅值达15%的证券",
                    "连续三个交易日内收盘价格涨幅偏离值累计达到20%的证券",
                    "日涨幅偏离值达7%的证券"],
    })


def _install_ak(monkeypatch, df=None, raise_on=False):
    """把 sys.modules 的 akshare 换成 fake（仅 stock_lhb_detail_em）。"""

    def _fn(start_date=None, end_date=None):
        if raise_on:
            raise RuntimeError("上游不可用")
        return df

    monkeypatch.setitem(sys.modules, "akshare",
                        types.SimpleNamespace(stock_lhb_detail_em=_fn))


def test_lhb_hit_net_buy_bullish(monkeypatch):
    _install_ak(monkeypatch, _lhb_df())
    r = ef.lhb_event_signal("600077")
    assert r["available"] is True
    assert r["signal"] == "看多"
    assert r["score"] == 62.0
    assert r["source"] == "eastmoney-lhb"
    assert r["lhb"]["count"] == 2, "窗口内两次上榜应如实计数"
    assert r["lhb"]["last_date"].startswith("2026-11-02"), "取最近一次上榜"
    assert r["lhb"]["net_amt"] == 25000000.0
    assert r["hard_logic"]["status"] in ("ok", "unavailable"), "上榜原因必须尝试标注"


def test_lhb_code_normalized(monkeypatch):
    """600077.SH / sh600077 / 600077 三种写法都能命中同一上榜记录。"""
    _install_ak(monkeypatch, _lhb_df())
    for sym in ("600077.SH", "sh600077", "600077"):
        r = ef.lhb_event_signal(sym)
        assert r["available"] is True, f"{sym} 应命中"
        assert r["signal"] == "看多"


def test_lhb_net_sell_bearish(monkeypatch):
    df = _lhb_df()
    df = df[df["代码"] == "000001"].copy()  # 只留净买额为正的另一只 → 换成负值
    df["龙虎榜净买额"] = [-8000000.0]
    _install_ak(monkeypatch, df)
    r = ef.lhb_event_signal("000001")
    assert r["available"] is True
    assert r["signal"] == "看空"
    assert r["score"] == 38.0


def test_lhb_missing_net_amt_neutral(monkeypatch):
    df = _lhb_df()
    df = df[df["代码"] == "000001"].copy()
    df["龙虎榜净买额"] = [None]
    _install_ak(monkeypatch, df)
    r = ef.lhb_event_signal("000001")
    assert r["available"] is True
    assert r["signal"] == "中性"
    assert r["score"] == 50.0
    assert r["lhb"]["net_amt"] is None


def test_lhb_absent_is_normal_state(monkeypatch):
    """未上榜 = 正常状态 available=False（非错误），reason 如实说明。"""
    _install_ak(monkeypatch, _lhb_df())
    r = ef.lhb_event_signal("300999")
    assert r["available"] is False
    assert "未上龙虎榜" in r["reason"]


def test_lhb_upstream_error_honest(monkeypatch):
    _install_ak(monkeypatch, raise_on=True)
    r = ef.lhb_event_signal("600077")
    assert r["available"] is False
    assert "抓取失败" in r["reason"]


def test_lhb_missing_code_column_honest(monkeypatch):
    _install_ak(monkeypatch, pd.DataFrame({"名称": ["x"]}))
    r = ef.lhb_event_signal("600077")
    assert r["available"] is False
    assert "代码" in r["reason"]


# ── get_event_factor 兜底序接线：P1 miss → 新闻 unavailable → 龙虎榜命中 ──
class _P1LoaderMiss:
    """有 ev 模型，但目标 symbol 不在任何榜 / daily 为空 → 走后续兜底。"""

    def available_models(self):
        return ["ev"]

    def top_long(self, model, top_n=None):
        return []

    def top_short(self, model, top_n=None):
        return []

    def daily_df(self, model):
        return pd.DataFrame(columns=["symbol", "date", "score", "signal"])

    def load(self, model):
        return {"horizon": 10, "latest_date": "2026-08-14"}


def test_get_event_factor_falls_through_to_lhb(monkeypatch, tmp_path):
    monkeypatch.setattr(ef, "news_event_signal",
                        lambda s, limit=15: {"available": False, "symbol": s,
                                             "reason": "无相关新闻"})
    _install_ak(monkeypatch, _lhb_df())
    out = ef.get_event_factor("600077", loader=_P1LoaderMiss())
    assert out["available"] is True
    assert out["source"] == "eastmoney-lhb"
    assert out["signal"] == "看多"


def test_get_event_factor_all_sources_miss_honest(monkeypatch):
    """三源全 miss → available=False，reason 覆盖三源语义，绝不造数。"""
    monkeypatch.setattr(ef, "news_event_signal",
                        lambda s, limit=15: {"available": False, "symbol": s,
                                             "reason": "无相关新闻"})
    monkeypatch.setattr(ef, "lhb_event_signal",
                        lambda s, lookback_days=10: {"available": False, "symbol": s,
                                                     "reason": "近 10 日未上龙虎榜"})
    out = ef.get_event_factor("600077", loader=_P1LoaderMiss())
    assert out["available"] is False
    assert "无 P1 事件因子信号" in out["reason"]
