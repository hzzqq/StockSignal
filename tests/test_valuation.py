# -*- coding: utf-8 -*-
"""tests/test_valuation.py — H2 估值分位深钻测试（纯计算，离线）。"""
import pytest

from modules import valuation as va


# ─────────────────────────── band_stats ───────────────────────────
def test_band_too_few_samples_is_unavailable():
    r = va.band_stats([10, 12, 11], 12)
    assert r["status"] == "unavailable"
    assert "样本不足" in r["reason"]


def test_band_ignores_non_positive_and_garbage():
    """负 PE（亏损）不得参与分位——否则会得出「越亏越便宜」。"""
    vals = [-8.0, 0.0, None, "abc"] + list(range(10, 40))
    r = va.band_stats(vals, 25)
    assert r["status"] == "ok"
    assert r["n"] == 30
    assert r["min"] == 10.0          # 不是 -8
    assert r["percentile"] is not None


def test_band_zone_boundaries():
    vals = list(range(1, 101))       # 1..100
    assert va.band_stats(vals, 5)["zone"] == "低估"
    assert va.band_stats(vals, 30)["zone"] == "偏低"
    assert va.band_stats(vals, 50)["zone"] == "合理"
    assert va.band_stats(vals, 70)["zone"] == "偏高"
    assert va.band_stats(vals, 95)["zone"] == "高估"


def test_band_percentiles_ordered():
    r = va.band_stats(list(range(1, 101)), 50)
    assert r["p20"] < r["p50"] < r["p80"]
    assert r["p20"] == pytest.approx(20.8, abs=1.0)
    assert r["p50"] == pytest.approx(50.5, abs=1.0)


def test_band_current_missing_still_returns_percentiles():
    r = va.band_stats(list(range(1, 101)), None)
    assert r["status"] == "ok"
    assert r["percentile"] is None and r["zone"] == "不可用"


def test_pe_pb_band_combines():
    r = va.pe_pb_band(list(range(1, 101)), list(range(1, 51)), 30, 25)
    assert r["pe"]["status"] == "ok" and r["pb"]["status"] == "ok"
    assert r["pe"]["zone"] == "偏低"


# ─────────────────────────── industry_relative ───────────────────────────
def test_industry_relative_basic():
    peers = [10, 20, 30, 40, 50]
    r = va.industry_relative(15, peers)
    assert r["status"] == "ok"
    assert r["rank"] == 2                    # 只有 10 比自己低
    assert r["median"] == 30.0
    assert r["ratio_to_median"] == pytest.approx(0.5)
    assert r["zone"] == "低估"


def test_industry_relative_needs_enough_peers():
    r = va.industry_relative(15, [10, 20])
    assert r["status"] == "unavailable"


def test_industry_relative_rejects_negative_current():
    r = va.industry_relative(-5, [10, 20, 30])
    assert r["status"] == "unavailable"
    assert "非正" in r["reason"]


# ─────────────────────────── dupont ───────────────────────────
def test_dupont_consistent():
    r = va.dupont(roe=20.0, net_margin=25.0, asset_turnover=0.8, equity_multiplier=1.0)
    assert r["status"] == "ok"
    assert r["implied_roe"] == pytest.approx(20.0)
    assert r["consistent"] is True


def test_dupont_missing_factor_unavailable():
    r = va.dupont(roe=20.0, net_margin=None, asset_turnover=0.8, equity_multiplier=1.0)
    assert r["status"] == "unavailable"
    assert "净利率" in r["missing"]


def test_dupont_leverage_flag():
    r = va.dupont(roe=18.0, net_margin=6.0, asset_turnover=1.2, equity_multiplier=2.5)
    assert any("高杠杆" in f for f in r["flags"])


def test_dupont_inconsistent_is_flagged_not_hidden():
    r = va.dupont(roe=30.0, net_margin=5.0, asset_turnover=1.0, equity_multiplier=1.0)
    assert r["status"] == "ok"          # 仍返回，但必须标注
    assert r["consistent"] is False
    assert "口径" in r["note"]


# ─────────────────────────── peer_matrix ───────────────────────────
def test_peer_matrix_medians_and_ranks():
    peers = [{"code": "A", "name": "甲", "pe": 10, "pb": 1.0, "roe": 20},
             {"code": "B", "name": "乙", "pe": 20, "pb": 2.0, "roe": 15},
             {"code": "C", "name": "丙", "pe": 30, "pb": 3.0, "roe": 10}]
    r = va.peer_matrix(peers)
    assert r["status"] == "ok"
    assert r["medians"]["pe"] == 20
    rows = {x["code"]: x for x in r["rows"]}
    assert rows["A"]["rank_pe"] == 1     # PE 最低
    assert rows["C"]["rank_pe"] == 3
    assert rows["A"]["rank_roe"] == 1    # ROE 最高


def test_peer_matrix_missing_value_not_filled_with_zero():
    peers = [{"code": "A", "pe": 10}, {"code": "B", "pe": None}, {"code": "C", "pe": 30}]
    r = va.peer_matrix(peers)
    rows = {x["code"]: x for x in r["rows"]}
    assert rows["B"]["pe"] is None        # 绝不补 0
    assert rows["B"]["rank_pe"] is None
    assert rows["B"]["n_valid"] == 0
    assert r["medians"]["pe"] == 20       # 只用有效值算中位


def test_peer_matrix_too_few():
    assert va.peer_matrix([{"code": "A", "pe": 10}])["status"] == "unavailable"
    assert va.peer_matrix(None)["status"] == "unavailable"


# ─────────────────────────── 纯度红线 ───────────────────────────
def test_pure_functions_work_without_akshare(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "akshare", None)
    assert va.band_stats(list(range(1, 101)), 50)["status"] == "ok"
    assert va.industry_relative(15, [10, 20, 30])["status"] == "ok"
    assert va.dupont(10, 10, 1, 1)["status"] == "ok"
    assert va.peer_matrix([{"code": "A", "pe": 1}, {"code": "B", "pe": 2},
                           {"code": "C", "pe": 3}])["status"] == "ok"


def test_fetch_returns_none_without_akshare(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "akshare", None)
    assert va.fetch_valuation_series("600519", "市盈率(TTM)") is None
    assert va.fetch_pe_pb_series("600519") is None
    assert va.fetch_dupont_inputs("600519") is None


# ─────────────────────────── 杜邦取数（假 akshare） ───────────────────────────
def _fake_ak_dupont(monkeypatch, row):
    import sys
    import types
    import pandas as pd
    mod = types.ModuleType("akshare")
    mod.stock_financial_analysis_indicator = lambda symbol, start_year: pd.DataFrame([row])
    monkeypatch.setitem(sys.modules, "akshare", mod)
    return mod


def test_fetch_dupont_inputs_uses_official_ratios(monkeypatch):
    _fake_ak_dupont(monkeypatch, {
        "日期": "2026-06-30", "净资产收益率(%)": "24.53", "销售净利率(%)": "52.08",
        "总资产周转率(次)": "0.2985", "股东权益比率(%)": "84.81",
    })
    got = va.fetch_dupont_inputs("600519")
    assert got["roe"] == 24.53
    assert got["net_margin"] == 52.08
    assert got["asset_turnover"] == 0.2985
    assert got["equity_multiplier"] == pytest.approx(1.1791, abs=0.001)
    # 三因子能直接喂给 dupont()
    rep = va.dupont(**got)
    assert rep["status"] == "ok"


def test_fetch_dupont_inputs_falls_back_to_debt_ratio(monkeypatch):
    _fake_ak_dupont(monkeypatch, {
        "日期": "2026-06-30", "净资产收益率(%)": "24.53", "销售净利率(%)": "52.08",
        "总资产周转率(次)": "0.2985", "资产负债率(%)": "15.19",
    })
    got = va.fetch_dupont_inputs("600519")
    assert got["equity_multiplier"] == pytest.approx(1.1791, abs=0.001)


def test_fetch_dupont_inputs_missing_factor_returns_none(monkeypatch):
    """缺「总资产周转率」→ 整体返回 None（不省略、不默认 1.0），页面据此标「不可用」。"""
    _fake_ak_dupont(monkeypatch, {
        "日期": "2026-06-30", "净资产收益率(%)": "24.53", "销售净利率(%)": "52.08",
        "股东权益比率(%)": "84.81",
    })
    assert va.fetch_dupont_inputs("600519") is None


def test_fetch_dupont_inputs_picks_latest_period(monkeypatch):
    import sys
    import types
    import pandas as pd
    mod = types.ModuleType("akshare")
    mod.stock_financial_analysis_indicator = lambda symbol, start_year: pd.DataFrame([
        {"日期": "2025-12-31", "净资产收益率(%)": "10.0", "销售净利率(%)": "10.0",
         "总资产周转率(次)": "1.0", "股东权益比率(%)": "50.0"},
        {"日期": "2026-06-30", "净资产收益率(%)": "24.0", "销售净利率(%)": "52.0",
         "总资产周转率(次)": "0.3", "股东权益比率(%)": "80.0"},
    ])
    monkeypatch.setitem(sys.modules, "akshare", mod)
    got = va.fetch_dupont_inputs("600519")
    assert got["roe"] == 24.0      # 取最新报告期
