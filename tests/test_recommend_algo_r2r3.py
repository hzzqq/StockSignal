"""R2 放量新高突破路 + R3 Value Trap 轻量评分单测（T-246，全离线）。

规格（docs/algorithm_benchmark.md 采纳清单 R2/R3 + T-246 spec 冻结）：

R2 `_breakout_score(df)`（纯本地，qfq 日线含 volume/amount）：
  - C1 52周新高闸：close > 前 min(250, n-1) 日最高收盘；不满足 → 0 分（非右侧强势股）；
  - C2 巨量：当日量 ≥ 前 20 日均量 ×2 或 近3日均量 ≥ 前60日均量 ×1.5；
  - C3 连站 MA5：近 3 日 close 均高于当日 MA5；
  - C4 成交额：近 3 日 amount 累计 > 24 亿（列缺失 → 该条件 unavailable）；
  - C5 换手 ≤50%：本引擎数据链无换手率字段 → 恒 unavailable，reasons 如实标注；
  - score = 100×(0.4 + 0.6×命中数/可用数)（C1 闸过后）；诚实：不可得条件不计分母。

R3 `value_trap_score(df)`（纯本地 4 分量，命中/可用 归一）：
  - V1 250 日价格分位 ≤0.25；V2 ret20<0 且 close<MA60；V3 ret120<-30%（不足 121 行→unavailable）；
    V4 近 20 日创 20 日新低次数 ≥5；
  - `pe_pb_low_pct_boost(pe_pct, pb_pct)`：PE 低位 +6 / PB 低位 +4（富集段确认项，取不到不加）；
  - 接线：enrich 段 vt_total = score + boost，≥50 且 A1 存在 → A1 分数 ×0.7 并注明；
  - ALGO_WEIGHTS 增 breakout=0.15 六路重分配，和恒为 1。

mutation 基线：
  - C1 判定放宽（假新高也过闸）→ test_breakout_* 变红；
  - 去掉 A1 ×0.7 折减 → test_trap_wired_* 变红；
  - 不可得条件计分母（谎报）→ test_breakout_no_amount / test_trap_short_history 变红。
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
    ALGO_WEIGHTS, _breakout_score, generate_daily_recommendation, value_trap_score,
)
from modules.recommend_engine import pe_pb_low_pct_boost  # noqa: E402


# ── 造数 ──
def _df(closes, vols=None, amounts=None):
    n = len(closes)
    vols = vols or [1e6] * n
    rows = []
    for i in range(n):
        c = closes[i]
        r = {"date": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
             "open": c, "high": c * 1.02, "low": c * 0.98, "close": c,
             "volume": vols[i],
             "amount": amounts[i] if amounts is not None else vols[i] * closes[i]}
        rows.append(r)
    return pd.DataFrame(rows)


def _rising(n=260, base=10.0, slope=0.04):
    return [base + slope * i for i in range(n)]


def _declining(n=260, base=100.0, slope=-0.23):
    return [base + slope * i for i in range(n)]


# ── R2：_breakout_score ──
def test_breakout_perfect_conditions():
    """新高+巨量+连站MA5+巨额成交 → 满分。"""
    closes = _rising()
    vols = [1e6] * 260
    vols[-1] = 3e6                       # 当日巨量 ≥ 2×MA20
    amounts = [1e6 * c for c in closes]  # ≈2e7/日
    amounts[-3] = amounts[-2] = amounts[-1] = 9e8   # 3 日累计 27 亿 > 24 亿
    out = _breakout_score(_df(closes, vols, amounts))
    assert out["score"] == 100.0
    assert any("52周新高" in r for r in out["reasons"])
    assert any("换手率不可得" in r for r in out["reasons"]), "C5 恒不可得必须如实标注"


def test_breakout_no_new_high_zero():
    """未创 52 周新高 → 0 分（C1 是闸门，不是加分项）。"""
    closes = [20.0 - 0.01 * i for i in range(260)]   # 单边下跌
    out = _breakout_score(_df(closes))
    assert out["score"] == 0.0
    assert any("未创" in r for r in out["reasons"])


def test_breakout_flat_series_zero():
    closes = [20.0] * 260                  # 持平：未「创」新高
    out = _breakout_score(_df(closes))
    assert out["score"] == 0.0


def test_breakout_missing_volume_condition():
    """新高但量能平淡 → C2 未命中，C3/C4 命中 → 0.4+0.6×2/3≈80。"""
    closes = _rising()
    amounts = [9e8] * 260
    out = _breakout_score(_df(closes, vols=None, amounts=amounts))
    assert out["score"] == pytest.approx(80.0, abs=0.1)


def test_breakout_small_amount_fails_c4():
    """3 日累计成交额不足 24 亿 → C4 未命中。"""
    closes = _rising()
    vols = [1e6] * 260
    vols[-1] = 3e6
    out = _breakout_score(_df(closes, vols))   # amount=volume*close ≈ 2e7
    assert out["score"] == pytest.approx(80.0, abs=0.1)
    assert any("成交额" in r for r in out["reasons"])


def test_breakout_no_amount_column_renormalizes():
    """df 无 amount 列 → C4 unavailable 不计分母（绝不按 0 处理）。"""
    closes = _rising()
    vols = [1e6] * 260
    vols[-1] = 3e6
    df = _df(closes, vols).drop(columns=["amount"], errors="ignore")
    out = _breakout_score(df)
    assert out["score"] == 100.0           # C2/C3 全命中，分母=2
    assert any("成交额不可得" in r for r in out["reasons"])


def test_breakout_short_history_uses_available_window():
    """90 行短历史：52 周窗口收缩为前 89 日，功能可用不炸。"""
    closes = _rising(90)
    vols = [1e6] * 90
    vols[-1] = 3e6
    amounts = [9e8] * 90
    out = _breakout_score(_df(closes, vols, amounts))
    assert out["score"] == 100.0


# ── R3：value_trap_score ──
def test_trap_full_flags():
    """深跌+低位+跌势未止+持续新低 → 全命中 100。"""
    out = value_trap_score(_df(_declining()))
    assert out["score"] == 100.0
    assert len(out["flags"]) == 4


def test_trap_healthy_zero():
    out = value_trap_score(_df(_rising()))
    assert out["score"] == 0.0 and out["flags"] == []


def test_trap_short_history_renormalizes():
    """100 行：V3（需 121 日）unavailable → 分母=3，三命中仍 100，flags 如实。"""
    closes = _declining(100, base=50.0, slope=-0.15)
    out = value_trap_score(_df(closes))
    assert out["score"] == 100.0
    assert any("120日" in f or "深跌" in f for f in out["unavailable"])


def test_pe_pb_boost_rules():
    assert pe_pb_low_pct_boost(0.2, 0.2) == 10
    assert pe_pb_low_pct_boost(0.2, 0.5) == 6
    assert pe_pb_low_pct_boost(None, 0.2) == 4
    assert pe_pb_low_pct_boost(None, None) == 0
    assert pe_pb_low_pct_boost(0.5, 0.5) == 0


def test_weights_sum_and_breakout():
    """六路权重和=1，breakout=0.15。"""
    assert ALGO_WEIGHTS.get("breakout") == pytest.approx(0.15)
    assert sum(ALGO_WEIGHTS.values()) == pytest.approx(1.0)


# ── 集成：value trap 折减接线 ──
def _fake_df(closes):
    n = len(closes)
    rows = []
    for i in range(n):
        c = closes[i]
        rows.append({"date": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                     "open": c, "high": c + 1, "low": c - 1, "close": c,
                     "volume": 1000.0, "amount": 5e8})
    return pd.DataFrame(rows)


@pytest.fixture()
def wired_engine2(monkeypatch):
    codes = ["600000", "600001"]
    df = _fake_df(_declining(260, base=80.0, slope=-0.12))   # 全体深度陷阱形态

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
    monkeypatch.setattr("modules.fetch_parallel.fetch_many",
                        lambda tasks, max_workers=8, timeout=None:
                        {name: (df.copy() if name.startswith("df_") else None)
                         for name, _ in tasks})
    monkeypatch.setattr("modules.backtest.Backtester._score_for_picker",
                        lambda self, df, strategy="multi_factor":
                        {"score": 55.0, "reasons": ["fake"]})
    monkeypatch.setattr("modules.recommend_engine._safe_fund_flow", lambda c: None)
    monkeypatch.setattr("modules.recommend_engine._safe_event_long_list", lambda: {})
    monkeypatch.setattr("modules.recommend_engine._safe_market_context", lambda: {})
    monkeypatch.setattr("modules.recommend_engine._safe_risk_scan", lambda cw: {})
    monkeypatch.setattr("modules.recommend_engine._safe_pe_pb_series", lambda c: None)
    monkeypatch.setattr("modules.recommend_engine.save_recommendation",
                        lambda rec, data_dir=None: None)
    return df


def test_trap_wired_a1_discounted(wired_engine2):
    """vt≥50 → A1 分数 ×0.7（55→38.5），reasons 带 ValueTrap 标注；A2 不动。"""
    rec = generate_daily_recommendation(universe_limit=10, enrich_top=2, top_k=2,
                                        data_dir="unused")
    assert rec["status"] == "ok"
    pick = rec["picks"][0]
    raw_a1 = pick["algorithms"]["multi_factor"]["raw"]
    assert raw_a1 == pytest.approx(38.5, abs=0.1), f"A1 应 55×0.7=38.5, got {raw_a1}"
    assert any("[ValueTrap]" in r for r in pick["reasons"])
    assert pick["algorithms"]["dual_trend"]["raw"] == 55.0, "A2 不受 trap 折减影响"


def test_trap_wired_below_threshold_untouched(wired_engine2, monkeypatch):
    """vt<50（健康形态）→ A1 分数原样。"""
    rising = _fake_df(_rising(260))
    monkeypatch.setattr("modules.fetch_parallel.fetch_many",
                        lambda tasks, max_workers=8, timeout=None:
                        {name: (rising.copy() if name.startswith("df_") else None)
                         for name, _ in tasks})
    rec = generate_daily_recommendation(universe_limit=10, enrich_top=2, top_k=2,
                                        data_dir="unused")
    pick = rec["picks"][0]
    assert pick["algorithms"]["multi_factor"]["raw"] == 55.0
    assert not any("[ValueTrap]" in r for r in pick["reasons"])
