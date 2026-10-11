"""T-256 信念×风险二维配仓单测（全离线）。

规格（benchmark stock-evaluator 采纳清单 R3 落地遗留 + T-256 spec 冻结）：
  - 信念维：picks 内 composite min-max 归一 → 倍数 [0.6, 1.5]（全相同=1.0）；
  - 风险维：risk_scan.overall_level=medium → ×0.8；reliable=False → ×0.85；
    value_trap.total ≥50 → ×0.85（乘积叠加；not_scanned/缺失 = 1.0，不惩罚也不奖）；
  - 预算守恒：Σhint = pos_base（总敞口不放大），单票 clamp [1, 20]，clamp 超预算则等比缩回；
  - pos_base 不可得/非正 → None（引擎走原「自行确定仓位」降级，不编造）。

mutation 基线：
  - 去掉风险维 → test_risk_level_downweights 变红；
  - 去掉预算守恒 → test_budget_conservation / test_clamp_renormalizes 变红；
  - 信念维改成等权 → test_conviction_orders_hints 变红。
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.recommend_engine import (  # noqa: E402
    generate_daily_recommendation, size_positions,
)


def _pick(code, composite, risk="scanned", level="low", reliable=True, vt=None):
    p = {"code": code, "name": code, "composite": composite}
    if risk is not None:
        p["risk_scan"] = {"status": risk, "overall_level": level, "reliable": reliable}
    if vt is not None:
        p["value_trap"] = {"total": vt}
    return p


def _hints(res):
    return res["hints"]


# ── 基础 ──
def test_budget_conservation():
    """Σhint = pos_base：总敞口不超市场建议仓位（不加杠杆）。"""
    picks = [_pick("600001", 80.0), _pick("600002", 60.0), _pick("600003", 40.0)]
    res = size_positions(picks, pos_base=30.0)
    assert res is not None
    assert sum(_hints(res).values()) == pytest.approx(30.0, abs=1e-6)
    assert all(1.0 <= v <= 20.0 for v in _hints(res).values())


def test_conviction_orders_hints():
    """信念维：composite 越高仓位越高（风险同档）。"""
    picks = [_pick("600001", 90.0), _pick("600002", 50.0), _pick("600003", 10.0)]
    res = size_positions(picks, pos_base=30.0)
    h = _hints(res)
    assert h["600001"] > h["600002"] > h["600003"]


def test_all_equal_composite_equal_split():
    """信念全相同 → 倍数全 1.0 → 等权 pos_base/n。"""
    picks = [_pick("600001", 55.0), _pick("600002", 55.0)]
    res = size_positions(picks, pos_base=20.0)
    h = _hints(res)
    assert h["600001"] == pytest.approx(h["600002"])
    assert sum(h.values()) == pytest.approx(20.0)


# ── 风险维 ──
def test_risk_level_downweights():
    """medium 风险 → ×0.8：同信念下拿得更少。"""
    picks = [_pick("600001", 70.0, level="low"),
             _pick("600002", 70.0, level="medium")]
    res = size_positions(picks, pos_base=20.0)
    h = _hints(res)
    assert h["600001"] > h["600002"]
    assert h["600002"] / h["600001"] == pytest.approx(0.8, rel=0.02)


def test_unreliable_scan_downweights():
    """扫描覆盖不足（reliable=False）→ ×0.85 保守。"""
    picks = [_pick("600001", 70.0, reliable=True),
             _pick("600002", 70.0, reliable=False)]
    res = size_positions(picks, pos_base=20.0)
    h = _hints(res)
    assert h["600001"] > h["600002"]
    assert h["600002"] / h["600001"] == pytest.approx(0.85, rel=0.02)


def test_value_trap_downweights():
    """价值陷阱分 ≥50 → ×0.85。"""
    picks = [_pick("600001", 70.0, vt=10.0),
             _pick("600002", 70.0, vt=60.0)]
    res = size_positions(picks, pos_base=20.0)
    h = _hints(res)
    assert h["600001"] > h["600002"]
    assert h["600002"] / h["600001"] == pytest.approx(0.85, rel=0.02)


def test_not_scanned_neutral():
    """未过闸（not_scanned）= 风险中性 1.0（不惩罚也不奖，不装扫过）。"""
    a = _pick("600001", 70.0, risk=None)
    b = _pick("600002", 70.0, risk="not_scanned")
    res = size_positions([a, b], pos_base=20.0)
    h = _hints(res)
    assert h["600001"] == pytest.approx(h["600002"])


def test_risk_factors_multiply():
    """medium(0.8) × trap(0.85) = 0.68 复合折减。"""
    picks = [_pick("600001", 70.0, level="low"),
             _pick("600002", 70.0, level="medium", vt=60.0)]
    res = size_positions(picks, pos_base=20.0)
    h = _hints(res)
    assert h["600002"] / h["600001"] == pytest.approx(0.8 * 0.85, rel=0.02)


# ── 边界 ──
def test_clamp_renormalizes():
    """cap 顶格后超预算 → 其余等比压缩，总量仍守恒。"""
    picks = [_pick("600001", 100.0), _pick("600002", 1.0)]
    res = size_positions(picks, pos_base=30.0)  # 无约束时 600001 想要 >20
    h = _hints(res)
    assert h["600001"] <= 20.0
    assert sum(h.values()) <= 30.0 + 1e-6


def test_floor_respected():
    """floor 1%：再弱也有最低试探仓（否则被 clamp 掉后守恒由其余承担）。"""
    picks = [_pick("600001", 100.0), _pick("600002", 100.0), _pick("600003", 0.0)]
    res = size_positions(picks, pos_base=3.0)
    h = _hints(res)
    assert h["600003"] >= 1.0


def test_pos_base_none_returns_none():
    """市场仓位快照不可得 → None（引擎走「自行确定仓位」降级，不编造）。"""
    picks = [_pick("600001", 80.0)]
    assert size_positions(picks, pos_base=None) is None
    assert size_positions(picks, pos_base=0.0) is None
    assert size_positions([], pos_base=30.0) is None


def test_basis_reported():
    """逐票 basis 如实落盘（信念倍数/风险因子），供页面解释。"""
    picks = [_pick("600001", 90.0, level="medium", vt=60.0)]
    res = size_positions(picks, pos_base=10.0)
    b = res["basis"]["600001"]
    assert b["conviction_mult"] == 1.0  # 单票 min-max → 全相同=1.0
    assert b["risk_factor"] == pytest.approx(0.8 * 0.85)
    assert res["pos_base"] == 10.0


# ── 接线（wired，含顺带修复的 levels 串票缺陷验证）──
def _wired(monkeypatch, per_code_df):
    codes = list(per_code_df)
    import pandas as pd

    class FakeFetcher:
        def __init__(self, config_path="config.yaml"):
            pass

        def get_all_codes(self, limit=None):
            return codes

        def get_stock_basic(self, code):
            return None, f"股{code}"

        def get_daily(self, code, start=None, end=None):
            return per_code_df[code].copy()

    monkeypatch.setattr("modules.fetcher.StockFetcher", FakeFetcher)
    monkeypatch.setattr(
        "modules.fetch_parallel.fetch_many",
        lambda tasks, max_workers=8, timeout=None:
        {name: (per_code_df[name[3:]].copy() if name.startswith("df_") else None)
         for name, _ in tasks})
    monkeypatch.setattr("modules.backtest.Backtester._score_for_picker",
                        lambda self, df, strategy="multi_factor":
                        {"score": 55.0, "reasons": ["fake"]})
    monkeypatch.setattr("modules.recommend_engine._safe_fund_flow", lambda c: None)
    monkeypatch.setattr("modules.recommend_engine._safe_event_long_list", lambda: {})
    monkeypatch.setattr("modules.recommend_engine._safe_market_context",
                        lambda: {"position": {"pct": 20.0}})
    monkeypatch.setattr("modules.recommend_engine._safe_risk_scan", lambda cw: {})
    monkeypatch.setattr("modules.recommend_engine._safe_pe_pb_series", lambda c: None)
    monkeypatch.setattr("modules.recommend_engine.save_recommendation",
                        lambda rec, data_dir=None: None)


def _mk_df(base):
    rows = [{"date": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
             "open": base, "high": base + 1, "low": base - 1, "close": base,
             "volume": 1000.0, "amount": 5e8} for i in range(100)]
    return pd.DataFrame(rows)


def test_wired_sizing_and_per_pick_levels(monkeypatch):
    """接线验证：①budget 守恒（pos_base=20 → Σhint=20）；②levels 逐票独立
    （600001 收盘 10 → entry≈10；600002 收盘 50 → entry≈50，不再串票）。"""
    _wired(monkeypatch, {"600001": _mk_df(10.0), "600002": _mk_df(50.0)})
    rec = generate_daily_recommendation(universe_limit=10, enrich_top=2, top_k=2,
                                        data_dir="unused")
    assert rec["status"] == "ok"
    hints = {p["code"]: p["plan"]["position_pct_hint"] for p in rec["picks"]}
    assert sum(hints.values()) == pytest.approx(20.0, abs=0.2), f"预算守恒: {hints}"
    entries = {p["code"]: p["plan"]["entry"] for p in rec["picks"]}
    assert entries["600001"] == pytest.approx(10.0, abs=0.5)
    assert entries["600002"] == pytest.approx(50.0, abs=0.5), "levels 必须逐票独立"


def test_wired_sizing_source_guard():
    """防脱落：引擎必须引用 size_positions。"""
    import inspect

    from modules import recommend_engine as re_mod

    assert "size_positions" in inspect.getsource(re_mod.generate_daily_recommendation)
