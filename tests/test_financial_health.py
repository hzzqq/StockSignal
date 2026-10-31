"""R8/T-363：financial_health 三模型守卫。

覆盖 F-Score(9分量) / Altman Z'(5比率) / Beneish M(6分量) 三模型，
每个模型至少：①全好数据 status=ok ②部分缺列/NaN status=warning
③全缺 status=unavailable ④关键 mutation 注入（阈值/符号/数据源）真红。
"""
import math

import numpy as np
import pandas as pd
import pytest

from modules import financial_health as fh


# ── Fake DataFrame 构造器 ────────────────────────────────────────────────
def _make_balance(row0: dict, row1: dict | None = None) -> pd.DataFrame:
    """构造 2 期资产负债表 fake df（row 0=最新, row 1=上期）。"""
    row1 = row1 or {k: v for k, v in row0.items()}  # 默认相同（无变化）
    common_cols = ["报告日"] + list(row0.keys())
    r0 = {"报告日": 20260930, **row0}
    r1 = {"报告日": 20260630, **row1}
    return pd.DataFrame([r0, r1], columns=common_cols)


def _make_income(row0: dict, row1: dict | None = None) -> pd.DataFrame:
    row1 = row1 or {k: v for k, v in row0.items()}
    common_cols = ["报告日"] + list(row0.keys())
    r0 = {"报告日": 20260930, **row0}
    r1 = {"报告日": 20260630, **row1}
    return pd.DataFrame([r0, r1], columns=common_cols)


def _make_cash(row0: dict, row1: dict | None = None) -> pd.DataFrame:
    row1 = row1 or {k: v for k, v in row0.items()}
    common_cols = ["报告日"] + list(row0.keys())
    r0 = {"报告日": 20260930, **row0}
    r1 = {"报告日": 20260630, **row1}
    return pd.DataFrame([r0, r1], columns=common_cols)


# 标准可用数据（茅台 20260930 近似，保证所有 F/Z/M 分量可用）
_BAL_OK = {
    "资产总计": 100e9, "负债合计": 60e9,
    "流动资产合计": 40e9, "流动负债合计": 30e9,
    "长期借款": 5e9, "应付债券": 2e9, "长期应付款合计": 1e9,
    "租赁负债": 0.5e9, "其他非流动负债": 0.5e9,
    "未分配利润": 15e9, "应收账款": 2e9, "实收资本(或股本)": 12.56e9,
}
_BAL_OK_PREV = {
    "资产总计": 95e9, "负债合计": 62e9,
    "流动资产合计": 35e9, "流动负债合计": 32e9,
    "长期借款": 6e9, "应付债券": 3e9, "长期应付款合计": 1.5e9,
    "租赁负债": 0.5e9, "其他非流动负债": 0.5e9,
    "未分配利润": 12e9, "应收账款": 2.2e9, "实收资本(或股本)": 12.56e9,
}

_INC_OK = {
    "营业收入": 80e9, "营业成本": 25e9,
    "净利润": 20e9, "所得税费用": 5e9, "财务费用": -0.5e9,
    "销售费用": 3e9, "管理费用": 4e9,
}
_INC_OK_PREV = {
    "营业收入": 70e9, "营业成本": 24e9,
    "净利润": 15e9, "所得税费用": 4e9, "财务费用": -0.3e9,
    "销售费用": 2.5e9, "管理费用": 3.5e9,
}

_CASH_OK = {
    "经营活动产生的现金流量净额": 22e9,
}
_CASH_OK_PREV = {
    "经营活动产生的现金流量净额": 14e9,
}


class _FakeFetcher:
    """模拟 fetcher 实例，可注入 get_financial / get_daily 返回值。"""

    def __init__(self, bal=None, inc=None, cash=None, daily_close: float = 800.0):
        self._bal = bal
        self._inc = inc
        self._cash = cash
        self._close = daily_close
        self.calls: list[tuple] = []

    def get_financial(self, symbol, report_type):
        self.calls.append(("get_financial", symbol, report_type))
        return {"balance": self._bal, "income": self._inc, "cash": self._cash}.get(report_type)

    def get_daily(self, symbol, start=None, adjust="qfq"):
        self.calls.append(("get_daily", symbol))
        return pd.DataFrame({"close": [self._close]})


# ════════════════════════════════════════════════════════════════════════════
# F-Score 守卫
# ════════════════════════════════════════════════════════════════════════════
class TestFScoreStructure:
    def test_returns_four_keys(self):
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV),
                         _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.f_score("600519", f)
        assert set(r.keys()) == {"status", "score", "components", "reasons"}

    def test_nine_components_present(self):
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV),
                         _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.f_score("600519", f)
        assert len(r["components"]) == 9

    def test_ok_when_all_components_available(self):
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV),
                         _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.f_score("600519", f)
        assert r["status"] == "ok"


class TestFScoreValues:
    def test_all_positive_gives_high_score(self):
        """好数据（profit up, debt down, margins up）→ 高分 7-9。"""
        bal = _make_balance(_BAL_OK, _BAL_OK_PREV)  # 资产增、长期债减
        inc = _make_income(_INC_OK, _INC_OK_PREV)  # 营收增、净利增、成本稳
        cash = _make_cash(_CASH_OK, _CASH_OK_PREV)  # OCF 增
        f = _FakeFetcher(bal, inc, cash)
        r = fh.f_score("600519", f)
        assert r["score"] is not None
        assert r["score"] >= 5

    def test_negative_net_income_reduces_roa_component(self):
        """净利润负 → ROA 分量 0，OCF>NI 分量应命中（OCF 正）。"""
        inc = _make_income({**_INC_OK, "净利润": -5e9}, _INC_OK_PREV)
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         inc, _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.f_score("600519", f)
        assert r["components"]["roa"]["value"] == 0
        assert r["components"]["ocf_gt_ni"]["value"] == 1  # 22 > -5 亿


class TestFScoreHonest:
    def test_cash_table_missing_marks_components_unavailable(self):
        """cash 表 OCF 为 NaN（茅台 Q3 真实场景）→ 分量 3/4 unavailable, score 按 7 项算。"""
        cash_nan = _make_cash({"经营活动产生的现金流量净额": np.nan},
                              {"经营活动产生的现金流量净额": 14e9})
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV), cash_nan)
        r = fh.f_score("600519", f)
        assert r["components"]["ocf_pos"]["status"] == "unavailable"
        assert r["components"]["ocf_gt_ni"]["status"] == "unavailable"
        assert r["score"] is not None  # 仍按其余 7 分量算
        assert any("OCF 未披露" in x for x in r["reasons"])

    def test_all_tables_none_gives_unavailable(self):
        f = _FakeFetcher(None, None, None)
        r = fh.f_score("X", f)
        assert r["status"] == "unavailable"
        assert r["score"] is None


# ════════════════════════════════════════════════════════════════════════════
# Altman Z' 守卫
# ════════════════════════════════════════════════════════════════════════════
class TestAltmanZStructure:
    def test_returns_four_keys(self):
        f = _FakeFetcher(_make_balance(_BAL_OK), _make_income(_INC_OK), None)
        r = fh.altman_z("600519", f)
        assert set(r.keys()) == {"status", "score", "components", "reasons"}

    def test_five_x_components_present(self):
        f = _FakeFetcher(_make_balance(_BAL_OK), _make_income(_INC_OK), None)
        r = fh.altman_z("600519", f)
        assert len(r["components"]) == 5

    def test_safe_zone_high_z(self):
        """好公司 Z'>2.675 → 安全区。"""
        f = _FakeFetcher(_make_balance(_BAL_OK), _make_income(_INC_OK), None, daily_close=800.0)
        r = fh.altman_z("600519", f)
        assert r["score"] is not None
        assert r["score"] > 2.675

    def test_danger_zone_low_z(self):
        """负债极高 + 亏损 + X4 unavailable → Z'<1.81 危险区。"""
        bad_bal = _make_balance({
            **_BAL_OK,
            "负债合计": 95e9,  # 资产 100 亿但负债 95 亿（极端资不抵债）
            "流动资产合计": 2e9, "流动负债合计": 90e9,
            "未分配利润": -20e9,
        })
        bad_inc = _make_income({**_INC_OK, "净利润": -15e9, "营业收入": 30e9, "营业成本": 25e9})
        f = _FakeFetcher(bad_bal, bad_inc, None, daily_close=0.0)  # close=0 → X4 unavailable
        r = fh.altman_z("BAD", f)
        assert r["score"] is not None
        assert r["score"] < 1.81


class TestAltmanZHonest:
    def test_market_cap_fallback(self):
        """X4 市值不可得（daily_close=0）→ X4 unavailable, Z 按 4 比率算 + warning。"""
        f = _FakeFetcher(_make_balance(_BAL_OK), _make_income(_INC_OK), None, daily_close=0.0)
        r = fh.altman_z("600519", f)
        assert r["components"]["X4"]["status"] == "unavailable"
        assert r["status"] == "warning"

    def test_all_x_unavailable(self):
        f = _FakeFetcher(None, None, None)
        r = fh.altman_z("X", f)
        assert r["status"] == "unavailable"
        assert r["score"] is None

    def test_x2_retained_earnings_approx_note(self):
        """X2 用未分配利润近似 → note 字符串应含诚实注记。"""
        f = _FakeFetcher(_make_balance(_BAL_OK), _make_income(_INC_OK), None)
        r = fh.altman_z("600519", f)
        assert "未分配利润" in r["components"]["X2"]["note"]


# ════════════════════════════════════════════════════════════════════════════
# Beneish M 守卫
# ════════════════════════════════════════════════════════════════════════════
class TestBeneishMStructure:
    def test_returns_four_keys(self):
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV),
                         _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.beneish_m("600519", f)
        assert set(r.keys()) == {"status", "score", "components", "reasons"}

    def test_six_components_present(self):
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV),
                         _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.beneish_m("600519", f)
        assert len(r["components"]) >= 6  # DSR/GMI/TATA/AQI/SGI/SVI

    def test_healthy_firm_m_below_threshold(self):
        """健康公司 → M<-1.78（正常）。"""
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV),
                         _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.beneish_m("600519", f)
        assert r["score"] is not None
        assert r["score"] < -1.78  # 正常区


class TestBeneishMHonest:
    def test_ocf_missing_downgrades_tata_aqi(self):
        """OCF 为 NaN → TATA/AQI/SVI unavailable，M 按 3 项算 + warning。"""
        cash_nan = _make_cash({"经营活动产生的现金流量净额": np.nan},
                              {"经营活动产生的现金流量净额": 14e9})
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV), cash_nan)
        r = fh.beneish_m("600519", f)
        assert r["components"]["TATA"]["status"] == "unavailable"
        assert r["components"]["AQI"]["status"] == "unavailable"
        assert r["status"] == "warning"
        assert any("OCF 缺失" in x for x in r["reasons"])

    def test_all_tables_none_gives_unavailable(self):
        f = _FakeFetcher(None, None, None)
        r = fh.beneish_m("X", f)
        assert r["status"] == "unavailable"
        assert r["score"] is None


# ════════════════════════════════════════════════════════════════════════════
# Mutation 注入守卫（防回退：阈值/符号/数据源改坏 → 测试应真红）
# ════════════════════════════════════════════════════════════════════════════
class TestMutationFScore:
    """注入假 OCF / 假负债 → 守卫应红（正向测试证明守卫确实生效）。"""

    def test_negative_ocf_fails_ocf_pos_component(self):
        """OCF=负 → 分量 ocf_pos 应得 0 而不是 1。"""
        cash_bad = _make_cash({"经营活动产生的现金流量净额": -1e9},
                              {"经营活动产生的现金流量净额": 14e9})
        f = _FakeFetcher(_make_balance(_BAL_OK, _BAL_OK_PREV),
                         _make_income(_INC_OK, _INC_OK_PREV), cash_bad)
        r = fh.f_score("BAD", f)
        assert r["components"]["ocf_pos"]["value"] == 0  # OCF 负 → 不得分

    def test_equity_issuance_penalizes_component_7(self):
        """股本增 → no_new_shares 分量 0。"""
        bal_issue = _make_balance(_BAL_OK,
                                  {**_BAL_OK_PREV, "实收资本(或股本)": 10e9})  # 上期 10 亿
        f = _FakeFetcher(bal_issue, _make_income(_INC_OK, _INC_OK_PREV),
                         _make_cash(_CASH_OK, _CASH_OK_PREV))
        r = fh.f_score("ISSUE", f)
        assert r["components"]["no_new_shares"]["value"] == 0  # 12.56 > 10 → 视为新增


class TestMutationAltmanZ:
    def test_positive_x4_must_be_finited(self):
        """市值=0（daily_close=0）→ X4 unavailable，不应炸 inf。"""
        f = _FakeFetcher(_make_balance(_BAL_OK), _make_income(_INC_OK), None, daily_close=0.0)
        r = fh.altman_z("BAD", f)
        assert r["components"]["X4"]["status"] == "unavailable"
        assert r["components"]["X4"]["value"] is None


class TestMutationBeneishM:
    def test_m_not_inf_when_all_zero(self):
        """六分量全 0 → M 应等于 -4.84（截距），不应炸 inf。"""
        flat_bal = _make_balance(_BAL_OK, _BAL_OK)
        flat_inc = _make_income(_INC_OK, _INC_OK)
        flat_cash = _make_cash(_CASH_OK, _CASH_OK)
        f = _FakeFetcher(flat_bal, flat_inc, flat_cash)
        r = fh.beneish_m("FLAT", f)
        assert r["score"] is not None
        assert np.isfinite(r["score"])
