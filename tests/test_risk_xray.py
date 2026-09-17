"""tests/test_risk_xray.py — H4 组合风险透视（离线纯计算）。"""

from modules.risk_xray import (
    brinson,
    concentration,
    correlation_matrix,
    scenario_pnl,
    sector_exposure,
)


# ───────── concentration ─────────
def test_concentration_levels_and_metrics():
    c = concentration({"a": 60, "b": 30, "c": 10})
    assert c["status"] == "ok"
    assert c["n"] == 3
    assert c["hhi"] == round(0.36 + 0.09 + 0.01, 4)      # 0.46
    assert c["level"] == "集中"
    assert c["max_weight_pct"] == 60.0
    assert c["effective_n"] == round(1 / 0.46, 2)
    assert c["top"][0] == ("a", 60.0)


def test_concentration_is_scale_invariant_and_guards():
    a = concentration({"a": 6, "b": 3, "c": 1})           # 不要求和=100
    b = concentration({"a": 60, "b": 30, "c": 10})
    assert a["hhi"] == b["hhi"]
    assert concentration({})["status"] == "unavailable"
    assert concentration(None)["status"] == "unavailable"
    assert concentration({"a": -1, "b": 0, "c": None})["status"] == "unavailable"


def test_concentration_dispersed():
    c = concentration({f"s{i}": 1 for i in range(20)})     # 等权 20 只
    assert c["level"] == "分散"
    assert c["hhi"] == round(1 / 20, 4)


# ───────── sector_exposure ─────────
def test_sector_exposure_aggregates():
    e = sector_exposure({"a": 50, "b": 30, "c": 20},
                        {"a": "银行", "b": "银行", "c": "白酒"})
    assert e["status"] == "ok"
    assert e["exposure"]["银行"] == 80.0
    assert e["exposure"]["白酒"] == 20.0
    assert e["n_sectors"] == 2
    assert e["unknown_pct"] == 0.0
    assert e["warning"] is None


def test_sector_exposure_unknown_flagged():
    e = sector_exposure({"a": 50, "b": 50}, {})            # 全无行业映射
    assert e["exposure"]["未知"] == 100.0
    assert e["unknown_pct"] == 100.0
    assert e["warning"] is not None                        # 缺失率过高 → 如实告警


# ───────── correlation_matrix ─────────
def test_correlation_matrix_values():
    cm = correlation_matrix({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "c": [4, 3, 2, 1]})
    assert cm["status"] == "ok"
    assert cm["codes"] == ["a", "b", "c"]
    assert cm["matrix"][0][0] == 1.0
    assert cm["matrix"][0][1] == 1.0                       # a,b 完全正相关
    assert cm["matrix"][0][2] == -1.0                      # a,c 完全负相关
    assert abs(cm["avg_corr"] - (-1 / 3)) < 0.01


def test_correlation_matrix_zero_variance_is_not_fabricated():
    cm = correlation_matrix({"a": [1, 2, 3, 4], "d": [5, 5, 5, 5]})
    assert cm["status"] == "ok"
    assert cm["matrix"][0][1] == 0.0                       # 方差 0 → None → 0.0，不编造


def test_correlation_matrix_insufficient():
    assert correlation_matrix({"a": [1, 2, 3]})["status"] == "unavailable"
    assert correlation_matrix({})["status"] == "unavailable"
    assert correlation_matrix(None)["status"] == "unavailable"


# ───────── scenario_pnl ─────────
def test_scenario_pnl_full_and_partial_coverage():
    full = scenario_pnl({"a": 50, "b": 50}, {"a": -0.3, "b": 0.1})
    assert full["status"] == "ok"
    assert full["pnl_pct"] == -10.0                        # 0.5*-0.3 + 0.5*0.1
    assert full["coverage_pct"] == 100.0
    assert full["n_missing"] == 0

    part = scenario_pnl({"a": 50, "b": 50}, {"a": -0.3})
    assert part["pnl_pct"] == -15.0                        # 仅 a 参与：0.5*-0.3
    assert part["coverage_pct"] == 50.0
    assert part["n_missing"] == 1 and "b" in part["missing"]


def test_scenario_pnl_unavailable():
    assert scenario_pnl(None, {"a": -0.1})["status"] == "unavailable"
    assert scenario_pnl({"a": 1}, None)["status"] == "unavailable"


# ───────── brinson ─────────
def test_brinson_equal_portfolio_has_no_effects():
    b = brinson({"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5},
                {"a": 0.10, "b": 0.02}, {"a": 0.10, "b": 0.02},
                {"a": "X", "b": "Y"})
    assert b["status"] == "ok"
    assert abs(b["total_alloc_pct"]) < 1e-9
    assert abs(b["total_select_pct"]) < 1e-9
    assert abs(b["total_inter_pct"]) < 1e-9


def test_brinson_allocation_effect_on_overweight_winner():
    # 超配跑赢行业 X（组内收益 10% > 基准整体 5%）→ 配置效应为正
    b = brinson({"a": 0.7, "b": 0.3}, {"a": 0.5, "b": 0.5},
                {"a": 0.10, "b": 0.00}, {"a": 0.10, "b": 0.00},
                {"a": "X", "b": "Y"})
    assert b["status"] == "ok"
    assert abs(b["total_alloc_pct"] - 2.0) < 1e-9          # (0.2*0.05) + (-0.2*-0.05) = 0.02
    assert abs(b["total_select_pct"]) < 1e-9
    assert b["rows"][0]["sector"] in ("X", "Y")


def test_brinson_unavailable():
    assert brinson(None, {"a": 1}, {}, {}, {})["status"] == "unavailable"
    assert brinson({"a": 1}, None, {}, {}, {})["status"] == "unavailable"
