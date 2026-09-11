# -*- coding: utf-8 -*-
"""锐评 R9 守卫：板块涨幅排名索引错位。

_cleaned 保留原 sectors 索引，ranked 是 reset_index 后的新索引；旧代码用
ranked[cleaned == X] 按标签对齐会选到「原始位置」匹配行而非「排序位置」匹配行，
导致排名错乱。修复后在 ranked 上重算清理名，索引与 ranked 一致。
"""
import sys
import pandas as pd

sys.path.insert(0, r"E:/project/ks/StockSignal")

from modules.analysis_engine import _sector_analysis  # noqa: E402


class FakeFetcher:
    def get_sector_list(self):
        # 白酒涨跌幅最高(3.0)应排第1名，但它在原始顺序里位于 index 1
        return pd.DataFrame({"sector": ["银行", "白酒", "医药"], "change": [1.0, 3.0, 2.0]})

    def get_concept_list(self):
        return None

    def get_concept_stocks(self, *a, **k):
        return None

    def get_sector_stocks(self, *a, **k):
        return None


def test_sector_rank_top_is_one():
    out = _sector_analysis("白酒", FakeFetcher())
    assert out["change_pct"] == 3.0, out
    assert out["rank"] == 1, out  # 白酒涨幅最高，必须排第 1
    assert out["total"] == 3, out


def test_sector_rank_mid_is_two():
    out = _sector_analysis("医药", FakeFetcher())
    assert out["change_pct"] == 2.0, out
    assert out["rank"] == 2, out  # 医药涨幅中间，必须排第 2


def test_sector_rank_bottom_is_three():
    out = _sector_analysis("银行", FakeFetcher())
    assert out["change_pct"] == 1.0, out
    assert out["rank"] == 3, out  # 银行涨幅最低，必须排第 3
