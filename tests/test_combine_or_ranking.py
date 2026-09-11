# -*- coding: utf-8 -*-
"""锐评 R10 守卫：OR 模式综合评分排序的单调性（超集股票不应排到子集之后）。

旧实现按各命中策略分项分的平均(score)排序：命中 a(95)+b(20) 平均 57.5，
会排在仅命中 a(95) 的股票(95) 之后——尽管前者是后者的超集且多一条确认信号，
单调性被破坏（静默错排）。修复后主排序键取分项分最大值、次键取加和 total_score，
既消除错排，也保留「单策略强信号不被双策略弱信号反超」的既有语义。
"""
import sys

sys.path.insert(0, r"E:/project/ks/StockSignal")

from modules.stock_screener import StockScreener  # noqa: E402


def _rmap():
    # C 命中 a(95)+b(20) → 是 D(仅 a=95) 的超集；D 只命中 a(95)
    return {
        "a": {
            "results": [
                {"code": "C", "name": "C", "score": 95},
                {"code": "D", "name": "D", "score": 95},
            ],
            "count": 2,
        },
        "b": {"results": [{"code": "C", "name": "C", "score": 20}], "count": 1},
    }


def test_or_superset_ranks_above_subset():
    out = StockScreener._combine_or(_rmap())
    codes = [r["code"] for r in out]
    # C 是 D 的超集（多一条确认信号 b(20)），必须排在 D 之前；旧实现会反排。
    assert codes.index("C") < codes.index("D"), codes
    c = next(r for r in out if r["code"] == "C")
    d = next(r for r in out if r["code"] == "D")
    assert c["best_score"] == 95 and d["best_score"] == 95
    assert c["total_score"] > d["total_score"]


def test_or_single_strong_beats_double_weak():
    # 既有语义：单策略强信号(95) 不被双策略弱信号(各60)反超
    rm = {
        "a": {"results": [{"code": "S", "name": "S", "score": 95}], "count": 1},
        "b": {"results": [{"code": "T", "name": "T", "score": 60}], "count": 1},
        "c": {"results": [{"code": "T", "name": "T", "score": 60}], "count": 1},
    }
    out = StockScreener._combine_or(rm)
    assert out[0]["code"] == "S"
    assert out[0]["best_score"] == 95
    assert out[1]["best_score"] == 60
