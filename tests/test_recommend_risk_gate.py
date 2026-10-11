"""R1 六维排雷二道闸单测（T-245，全离线）。

规格（docs/algorithm_benchmark.md 采纳清单 R1 + T-245 spec 冻结）：
  - 闸门段 = max(enrich_top, top_k)，逐股 stock_risk 六维扫描；
  - report.overall_level == "high"（ST/商誉/质押/解禁/减持/诉讼任一高危）→ 硬红旗踢出；
  - unknown ≠ guilty：扫描失败/维度未知不踢（绝不把没查到当安全或当有罪）；
  - 排雷整体不可得 → 全部标 not_scanned，主流程不阻塞（诚实降级）；
  - 被踢后从闸门段之外顺位补足 top_k，补入者如实标 not_scanned；
  - rec["risk_gate"] 汇总始终存在；pick 带 risk_scan 字段。

mutation 基线：
  - 踢出逻辑改成「high 也保留」→ test_gate_kicks_high_risk / test_gate_wired_* 变红；
  - 不可得时谎报 scanned → test_gate_unavailable_* 变红；
  - 补入者不标 not_scanned → test_gate_backfill_from_tail 变红。
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.recommend_engine import apply_risk_gate, generate_daily_recommendation  # noqa: E402


# ── 造数 ──
def _report(level="low", n_high=0, risk_score=10.0, reliable=True):
    return {"overall_level": level, "n_high": n_high,
            "risk_score": risk_score, "reliable": reliable}


def _scan(code, level="low", n_high=0, components=None):
    return {"code": str(code).zfill(6), "name": str(code),
            "components": components or {}, "report": _report(level, n_high),
            "errors": []}


def _rows(n):
    return [{"code": f"60000{i}", "name": f"股{i}", "composite": 100.0 - i,
             "risk_scan": None} for i in range(n)]


# ── 纯逻辑：apply_risk_gate ──
def test_gate_kicks_high_risk():
    rows = _rows(3)
    scan_map = {"600000": _scan("600000", "high", 2), "600001": _scan("600001", "low")}
    gated, summary = apply_risk_gate(rows, scan_map, top_k=2, gate_n=3)
    codes = [r["code"] for r in gated]
    assert "600000" not in codes and "600001" in codes
    assert summary["status"] == "ok"
    assert [k["code"] for k in summary["kicked"]] == ["600000"]
    assert summary["kicked"][0]["overall_level"] == "high" and summary["kicked"][0]["n_high"] == 2
    kept = next(r for r in gated if r["code"] == "600001")
    assert kept["risk_scan"]["status"] == "scanned"
    assert kept["risk_scan"]["overall_level"] == "low"


def test_gate_kick_reasons_carry_dimension_cn():
    comps = {"goodwill": {"level": "high", "value": 45.0, "note": "商誉/净资产 45%"}}
    rows = _rows(1)
    scan_map = {"600000": _scan("600000", "high", 1, components=comps)}
    _, summary = apply_risk_gate(rows, scan_map, top_k=1, gate_n=1)
    assert summary["kicked"], "high 应被踢"
    assert any("商誉" in r for r in summary["kicked"][0]["reasons"])


def test_gate_unknown_not_guilty():
    """全维度 unknown（扫描失败组件多）→ 不踢，只如实带 reliable/level。"""
    rows = _rows(1)
    scan_map = {"600000": {"code": "600000", "name": "x", "components": {},
                           "report": _report("unknown", 0, reliable=False), "errors": ["net"]}}
    gated, summary = apply_risk_gate(rows, scan_map, top_k=1, gate_n=1)
    assert [r["code"] for r in gated] == ["600000"]
    assert summary["kicked"] == []
    assert gated[0]["risk_scan"]["status"] == "scanned"
    assert gated[0]["risk_scan"]["reliable"] is False


def test_gate_unavailable_marks_not_scanned():
    rows = _rows(2)
    gated, summary = apply_risk_gate(rows, {}, top_k=2, gate_n=2)
    assert summary["status"] == "unavailable" and summary["scanned"] == 0
    assert summary["kicked"] == []
    assert all(r["risk_scan"] == {"status": "not_scanned"} for r in gated)
    assert [r["code"] for r in gated] == ["600000", "600001"], "降级不改变顺位"


def test_gate_backfill_from_tail():
    """闸门段踢出后不足 top_k → 从 tail 顺位补入，补入者标 not_scanned。"""
    rows = _rows(5)  # 600000..600004，composite 降序
    scan_map = {
        "600000": _scan("600000", "high", 1),
        "600001": _scan("600001", "high", 1),
        "600002": _scan("600002", "low"),
    }
    gated, summary = apply_risk_gate(rows, scan_map, top_k=3, gate_n=3)
    assert summary["status"] == "ok" and len(summary["kicked"]) == 2
    codes = [r["code"] for r in gated]
    # 闸门段保留 600002，tail(600003/600004) 原序跟随
    assert codes == ["600002", "600003", "600004"]
    assert gated[0]["risk_scan"]["status"] == "scanned"
    assert all(r["risk_scan"]["status"] == "not_scanned" for r in gated[1:])


def test_gate_gate_n_at_least_top_k():
    """gate_n < top_k 时取 max（闸门段必须覆盖潜在入选者）。"""
    rows = _rows(4)
    scan_map = {f"60000{i}": _scan(f"60000{i}", "low") for i in range(1, 4)}
    scan_map["600000"] = _scan("600000", "high", 1)
    gated, summary = apply_risk_gate(rows, scan_map, top_k=3, gate_n=1)
    assert summary["gate_size"] == 3, "gate_n 应放大到 max(1,3)=3"
    assert "600000" not in [r["code"] for r in gated]


def test_gate_summary_shape():
    rows = _rows(1)
    _, summary = apply_risk_gate(rows, {"600000": _scan("600000")}, top_k=1, gate_n=1)
    assert {"status", "gate_size", "scanned", "kicked", "reason"} <= set(summary)


def test_gate_never_mutates_input_order():
    rows = _rows(3)
    scan_map = {"600001": _scan("600001", "high", 1)}
    gated, _ = apply_risk_gate(rows, scan_map, top_k=3, gate_n=3)
    assert [r["code"] for r in gated] == ["600000", "600002"]
    assert [r["code"] for r in rows] == ["600000", "600001", "600002"], "不重排入参"


# ── 集成：generate_daily_recommendation 接线 ──
def _fake_df(n=100, base=10.0):
    rows = []
    for i in range(n):
        c = base + 0.01 * i
        rows.append({"date": f"2026-01-{(i % 28) + 1:02d}", "open": c, "high": c + 1,
                     "low": c - 1, "close": c, "volume": 1000.0})
    return pd.DataFrame(rows)


@pytest.fixture()
def wired_engine(monkeypatch):
    """把 generate_daily_recommendation 的全部外依赖替换为离线假件。"""
    codes = ["600000", "600001", "600002"]
    df = _fake_df()

    class FakeFetcher:
        def __init__(self, config_path="config.yaml"):
            pass

        def get_all_codes(self, limit=None):
            return codes

        def get_stock_basic(self, code):
            return None, f"股{code}"

        def get_daily(self, code, start=None, end=None):
            return df.copy()

    monkeypatch.setattr("modules.fetcher.StockFetcher", FakeFetcher)

    def fake_fetch_many(tasks, max_workers=8, timeout=None):
        return {name: (df.copy() if name.startswith("df_") else None)
                for name, _ in tasks}

    monkeypatch.setattr("modules.fetch_parallel.fetch_many", fake_fetch_many)

    def fake_score(self, df, strategy="multi_factor"):
        return {"score": 50.0 + codes.index(df["close"].iloc[0]) if False else 55.0,
                "reasons": ["fake"]}

    monkeypatch.setattr("modules.backtest.Backtester._score_for_picker", fake_score)
    monkeypatch.setattr("modules.recommend_engine._safe_fund_flow", lambda c: None)
    monkeypatch.setattr("modules.recommend_engine._safe_event_long_list", lambda: {})
    monkeypatch.setattr("modules.recommend_engine._safe_market_context", lambda: {})

    saved = {}

    def fake_save(rec, data_dir=None):
        saved["rec"] = rec

    monkeypatch.setattr("modules.recommend_engine.save_recommendation", fake_save)
    return saved


def test_gate_wired_kicks_and_marks(wired_engine, monkeypatch):
    saved = wired_engine
    scan_map = {
        "600000": _scan("600000", "high", 1),
        "600001": _scan("600001", "low"),
        "600002": _scan("600002", "low"),
    }
    monkeypatch.setattr("modules.recommend_engine._safe_risk_scan",
                        lambda cw: scan_map)
    rec = generate_daily_recommendation(universe_limit=10, enrich_top=3, top_k=2,
                                        data_dir="unused")
    assert rec["status"] == "ok"
    rg = rec["risk_gate"]
    assert rg["status"] == "ok" and rg["scanned"] == 3
    assert [k["code"] for k in rg["kicked"]] == ["600000"]
    pick_codes = [p["code"] for p in rec["picks"]]
    assert "600000" not in pick_codes and len(pick_codes) == 2
    assert all(p["risk_scan"]["status"] == "scanned" for p in rec["picks"])
    assert rg["unscanned_picks"] == 0
    assert saved["rec"] is rec


def test_gate_wired_unavailable_degrades(wired_engine, monkeypatch):
    monkeypatch.setattr("modules.recommend_engine._safe_risk_scan", lambda cw: {})
    rec = generate_daily_recommendation(universe_limit=10, enrich_top=3, top_k=2,
                                        data_dir="unused")
    assert rec["status"] == "ok", "排雷不可得不得阻塞荐股主流程"
    rg = rec["risk_gate"]
    assert rg["status"] == "unavailable"
    assert all(p["risk_scan"]["status"] == "not_scanned" for p in rec["picks"])
    assert rg["unscanned_picks"] == len(rec["picks"]) > 0


def test_gate_wired_scan_exception_degrades(wired_engine, monkeypatch):
    """_safe_risk_scan 内部已兜异常，但引擎层再兜一层：抛异常也不得炸主流程。"""
    def boom(cw):
        raise RuntimeError("network down")

    monkeypatch.setattr("modules.recommend_engine._safe_risk_scan", boom)
    rec = generate_daily_recommendation(universe_limit=10, enrich_top=3, top_k=2,
                                        data_dir="unused")
    assert rec["status"] == "ok"
    assert rec["risk_gate"]["status"] == "unavailable"


# ── 接线文本守卫（防脱落，同 test_recommend_guard 范式）──
def test_engine_generate_wires_risk_gate():
    import inspect

    from modules import recommend_engine as re_mod

    src = inspect.getsource(re_mod.generate_daily_recommendation)
    assert "apply_risk_gate" in src and "_safe_risk_scan" in src
    assert "risk_gate" in src
