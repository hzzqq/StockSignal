"""市场温度计模块守卫测试。

覆盖：分档边界、综合温度确定性（离线阈值退化）、贡献明细（排除观察项）、
极端区信号（触发/降级）、历史类比（monkeypatch 确定性 + 真实降级）。
"""
import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import market_temperature as mt
import modules.sentiment_edge as sentiment_edge


# ── 分档边界 ──────────────────────────────────────────────────────────────
def test_temperature_band_boundaries():
    assert mt.temperature_band(0)["label"] == "冰点"
    assert mt.temperature_band(19.9)["label"] == "冰点"
    assert mt.temperature_band(20)["label"] == "偏冷"
    assert mt.temperature_band(39.9)["label"] == "偏冷"
    assert mt.temperature_band(40)["label"] == "中性"
    assert mt.temperature_band(59.9)["label"] == "中性"
    assert mt.temperature_band(60)["label"] == "活跃"
    assert mt.temperature_band(79.9)["label"] == "活跃"
    assert mt.temperature_band(80)["label"] == "狂热"
    assert mt.temperature_band(100)["label"] == "狂热"


def test_temperature_band_nan_and_invalid():
    # NaN / None / 非数值 → 中性兜底（不抛错）
    assert mt.temperature_band(float("nan"))["label"] == "中性"
    assert mt.temperature_band(None)["label"] == "中性"
    assert mt.temperature_band("abc")["label"] == "中性"
    # 越界裁剪
    assert mt.temperature_band(-50)["label"] == "冰点"
    assert mt.temperature_band(999)["label"] == "狂热"


# ── 综合温度：极端热 / 极端冷（离线阈值退化，确定性）─────────────────────
_HOT = {"up_count": 4000, "down_count": 1000, "limit_up": 80, "limit_down": 2,
        "zt_prev_ret": 4.0, "red_ratio": 75.0, "connect_hl": 8, "zt_fail_ratio": 20.0}
_COLD = {"up_count": 1000, "down_count": 4000, "limit_up": 5, "limit_down": 40,
         "zt_prev_ret": -2.0, "red_ratio": 20.0, "connect_hl": 1, "zt_fail_ratio": 70.0}


def test_composite_temperature_hot():
    t = mt.composite_temperature(_HOT, hist_days=2000)
    assert 0 <= t <= 100
    assert t == 100.0  # 全部超 hot 阈值 → 满分
    assert mt.temperature_band(t)["label"] == "狂热"


def test_composite_temperature_cold():
    t = mt.composite_temperature(_COLD, hist_days=2000)
    assert 0 <= t <= 100
    assert t == 10.0  # 全部低于 warm 阈值 → 10 分
    assert mt.temperature_band(t)["label"] == "冰点"


def test_composite_temperature_empty_input():
    assert mt.composite_temperature({}, hist_days=2000) == 50.0
    assert mt.composite_temperature(None, hist_days=2000) == 50.0


# ── 贡献明细：排除观察项（dir=0），heat 取 0-100 ────────────────────────
def test_contributions_exclude_observation_items():
    today = dict(_HOT)
    today["avg_price"] = 12.5      # 观察项 dir=0，必须排除
    today["turnover_amt"] = 8000.0  # 观察项 dir=0，必须排除
    detail = mt.temperature_contributions(today, hist_days=2000)
    keys = {c["key"] for c in detail["contributions"]}
    assert "avg_price" not in keys
    assert "turnover_amt" not in keys
    for c in detail["contributions"]:
        assert 0 <= c["heat"] <= 100
        assert c["name"] and c["unit"] is not None


def test_contributions_keys_complete():
    detail = mt.temperature_contributions(_HOT, hist_days=2000)
    # 8 个核心指标全部在场（离线退化也应有 heat）
    assert len(detail["contributions"]) == 8
    assert detail["temp"] == 100.0


# ── 极端区信号：触发路径（monkeypatch 校准件）────────────────────────────
def test_extreme_zone_signal_triggered(monkeypatch):
    fake_cal = {
        "available": True,
        "base_next_day_up_rate": 0.498,
        "features": {
            "limit_down_ratio": {
                "publishable": True,
                "production_threshold": 5.0,
                "name": "跌停占比",
                "why": "test",
                "walk_forward": {"up_rate": 0.625, "trigger_days": 296, "z": 4.36},
            }
        },
        "strength_ic": {},
    }
    monkeypatch.setattr(sentiment_edge, "load_calibration", lambda: fake_cal)
    today = {"limit_down": 100, "up_count": 1000, "down_count": 1000, "flat_count": 0}
    sig = mt.extreme_zone_signal(today)
    assert sig["available"] is True
    assert sig["triggered"] is True
    assert sig["evaluated"] is True
    assert sig["prob"] == 0.625


def test_extreme_zone_signal_missing_calibration(monkeypatch):
    # 校准件不可用 → 优雅降级，不抛错
    monkeypatch.setattr(sentiment_edge, "load_calibration",
                        lambda: {"available": False, "reason": "test missing"})
    sig = mt.extreme_zone_signal({"limit_down": 100})
    assert sig["available"] is False
    assert sig["triggered"] is False


# ── 历史类比：monkeypatch 确定性 + 数据结构 ──────────────────────────────
def _fake_breadth_df():
    dates = pd.date_range("2024-01-01", periods=20, freq="D")
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "date": dates,
        "red_ratio": (50 + rng.normal(0, 8, 20)).tolist(),
        "limit_up": (30 + rng.normal(0, 10, 20)).astype(int).tolist(),
        "limit_down": (5 + rng.normal(0, 3, 20)).clip(0).astype(int).tolist(),
    })


def test_historical_analogs_structure(monkeypatch):
    monkeypatch.setattr("modules.market_temperature.mr.load_breadth_history", _fake_breadth_df)
    today = {"red_ratio": 60, "limit_up": 45, "limit_down": 3}
    ana = mt.historical_analogs(today, k=5)
    assert ana["available"] is True
    assert "analogs" in ana
    assert len(ana["analogs"]) == 5
    a0 = ana["analogs"][0]
    assert "date" in a0 and "distance" in a0 and "forward" in a0
    # 今日指标被正确记录
    assert ana["today_metrics"]["red_ratio"] == 60


def test_historical_analogs_missing_history(monkeypatch):
    monkeypatch.setattr("modules.market_temperature.mr.load_breadth_history",
                        lambda: pd.DataFrame(columns=["date"]))
    ana = mt.historical_analogs({"red_ratio": 60})
    assert ana["available"] is False
    assert "reason" in ana
