"""
analysis_engine._sector_analysis 边界健壮性测试。

覆盖：
1) 回归：板块/概念列表缺失「涨跌幅」列时，函数应优雅返回占位 dict，而非抛 KeyError
   （修复前概念分支 L154 重算 chg_col 后无 None 守卫，会触发 sec.iloc[0][None] 崩溃）。
2) 正向：行业匹配成功返回排名信息；概念命中且无 change 列时安全降级。
3) 网络/数据为空时返回占位，不抛异常（既有契约）。
"""

from __future__ import annotations

import pandas as pd

from modules.analysis_engine import _sector_analysis


class _FakeFetcher:
    """可编排返回值的假 fetcher，仅实现 _sector_analysis 实际调用的方法。"""

    def __init__(self, sector_df=None, concept_df=None, peer_df=None):
        self._sector = sector_df
        self._concept = concept_df
        self._peer = peer_df

    def get_sector_list(self):
        return self._sector

    def get_concept_list(self):
        return self._concept

    def get_concept_stocks(self, name):
        return self._peer

    def get_sector_stocks(self, name):
        return self._peer


def _sector_with_change(rows):
    return pd.DataFrame(rows, columns=["sector", "change_pct"])


def _concept_no_change(rows):
    # 故意不含任何 change 列，触发 chg_col=None 守卫路径
    return pd.DataFrame(rows, columns=["sector"])


def test_concept_match_but_no_change_column_returns_placeholder():
    """概念列表命中行业但无涨跌幅列：修复前 KeyError，修复后应安全返回占位。"""
    sector = _sector_with_change([{"sector": "银行", "change_pct": 0.5}])  # 不匹配"半导体"
    concept = _concept_no_change([{"sector": "半导体"}])  # 命中但无 change 列
    fetcher = _FakeFetcher(sector_df=sector, concept_df=concept)
    out = _sector_analysis("半导体", fetcher, ticker="600000")
    assert isinstance(out, dict)
    # 回归核心：不应抛 KeyError；因概念列表无涨跌幅列无法排名，change_pct/rank 仍为占位
    assert out["change_pct"] is None
    assert out["rank"] is None


def test_sector_match_returns_ranking():
    """行业命中且有涨跌幅列：正常返回排名信息。"""
    sector = _sector_with_change([
        {"sector": "半导体", "change_pct": 2.3},
        {"sector": "银行", "change_pct": 0.5},
    ])
    fetcher = _FakeFetcher(sector_df=sector)
    out = _sector_analysis("半导体", fetcher)
    assert out["board_type"] == "行业"
    assert out["change_pct"] == 2.3
    assert out["rank"] == 1
    assert out["total"] == 2


def test_empty_inputs_return_placeholder():
    """行业关键词为空 / 列表为空：安全返回占位。"""
    fetcher = _FakeFetcher(sector_df=pd.DataFrame(columns=["sector", "change_pct"]))
    out = _sector_analysis("", fetcher)
    assert out["change_pct"] is None
    out2 = _sector_analysis("半导体", fetcher)
    assert out2["board_type"] in ("行业", "概念")
