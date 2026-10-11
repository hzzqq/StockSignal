"""recommend_engine 单测（纯函数 + 持久化 + 融合契约，全离线）。

T-233：荐股引擎核心逻辑守卫。mutation 基线：
  - minmax_normalize 去掉 min-max（全返 0.5）→ test_minmax_span_red 变红
  - fusion_score 缺失算法不重归一化 → test_fusion_missing_renorm 变红
"""
from __future__ import annotations

import json
import math
import os
import sys

import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.recommend_engine import (  # noqa: E402
    atr14, fusion_score, load_latest_recommendation, minmax_normalize,
    rec_paths, save_recommendation, trade_levels, today_generated,
)


# ── minmax_normalize ──
def test_minmax_normalize_basic():
    out = minmax_normalize({"a": 10, "b": 20, "c": 30})
    assert out["a"] == 0.0 and out["b"] == 0.5 and out["c"] == 1.0


def test_minmax_no_discrimination_returns_half():
    """全相同值 → 全 0.5（不假装有区分度）。"""
    out = minmax_normalize({"a": 7, "b": 7, "c": 7})
    assert out["a"] == out["b"] == out["c"] == 0.5


def test_minmax_none_preserved():
    out = minmax_normalize({"a": 10, "b": None, "c": 30})
    assert out["b"] is None and out["a"] == 0.0 and out["c"] == 1.0


# ── fusion_score ──
def test_fusion_missing_algo_renormalizes():
    """某算法缺失 → 其权重归零，其余按可用权重重归一化（和仍为 1）。"""
    composite, breakdown = fusion_score({"multi_factor": 100, "momentum": 0})
    assert composite is not None
    # 可用权重 0.30+0.10=0.40 → 各自 effective = w/0.40
    assert breakdown["multi_factor"]["effective_weight"] == pytest.approx(0.75)
    assert breakdown["momentum"]["effective_weight"] == pytest.approx(0.25)
    # 100 分 vs 0 分 → composite = 0.75*100 + 0.25*0 = 75
    assert composite == pytest.approx(75.0)
    assert breakdown["fund_flow"]["effective_weight"] == 0.0
    assert breakdown["fund_flow"]["raw"] is None


def test_fusion_all_missing_returns_none():
    composite, breakdown = fusion_score({"multi_factor": None, "momentum": None})
    assert composite is None and all(v["effective_weight"] == 0.0 for v in breakdown.values())


def test_fusion_breakdown_sum_effective_weights():
    """全算法可用时 effective_weight 之和 = 1。"""
    _, breakdown = fusion_score({k: 50 for k in ("multi_factor", "dual_trend",
                                                 "fund_flow", "event_factor", "momentum")})
    assert sum(v["effective_weight"] for v in breakdown.values()) == pytest.approx(1.0)


# ── trade_levels / atr14 ──
def test_trade_levels_atr_ratios():
    lv = trade_levels(100.0, 2.0)
    assert lv["entry"] == 100.0 and lv["stop"] == 96.0 and lv["target"] == 106.0
    # 盈亏比 = 3ATR / 2ATR = 1.5
    risk = lv["entry"] - lv["stop"]
    reward = lv["target"] - lv["entry"]
    assert reward / risk == pytest.approx(1.5)


def test_trade_levels_nan_safe():
    lv = trade_levels(float("nan"), 2.0)
    assert math.isnan(lv["entry"]) and lv["target"] is None and lv["stop"] is None
    lv2 = trade_levels(100.0, None)
    assert lv2["target"] is None


def test_atr14_basic():
    # 20 根固定波幅 K 线：high-low=2，ATR14=2
    rows = [{"date": f"2024-01-{d:02d}", "open": 10, "high": 11, "low": 9,
             "close": 10, "volume": 1000} for d in range(1, 21)]
    assert atr14(pd.DataFrame(rows)) == pytest.approx(2.0)


def test_atr14_insufficient():
    assert math.isnan(atr14(pd.DataFrame(columns=["high", "low", "close"])))


# ── 持久化（tmp 目录注入）──
def test_save_load_roundtrip(tmp_path):
    rec = {"status": "ok", "date": "2026-10-11", "picks": [{"code": "600519"}],
           "disclaimer": "x"}
    save_recommendation(rec, data_dir=str(tmp_path))
    archive, latest = rec_paths(str(tmp_path))
    assert os.path.exists(archive) and os.path.exists(latest)
    assert today_generated(str(tmp_path))
    back = load_latest_recommendation(str(tmp_path))
    assert back["status"] == "ok" and back["picks"][0]["code"] == "600519"
    with open(archive, encoding="utf-8") as f:
        assert json.load(f)["date"] == "2026-10-11"


def test_load_missing_is_unavailable_not_fake(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.recommend_engine.rec_paths",
        lambda data_dir=None: (str(tmp_path / "a.json"), str(tmp_path / "b.json")))
    out = load_latest_recommendation()
    assert out["status"] == "unavailable" and "尚未生成" in out["reason"]


def test_load_corrupt_is_unavailable(tmp_path, monkeypatch):
    latest = tmp_path / "b.json"
    latest.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(
        "modules.recommend_engine.rec_paths",
        lambda data_dir=None: (str(tmp_path / "a.json"), str(latest)))
    out = load_latest_recommendation()
    assert out["status"] == "unavailable"
