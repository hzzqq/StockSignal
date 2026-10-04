# -*- coding: utf-8 -*-
"""tests/test_dual_factor_wiring.py — T-183 双因子生产接线守卫。

覆盖：compute_dual_factor_inputs 汇聚正确性 / 诚实降级（缺文件·缺数日）/
缓存纪律（成功才缓存）/ keep_nan 门控隐患修复 / build_snapshot 自动接线。
"""
from __future__ import annotations

import json
from datetime import date as _date

import numpy as np
import pandas as pd
import pytest

from modules import decision
from modules.market_regime import load_breadth_history

# T-202：快照/指标 date 必须时钟相对——硬编码历史日期会随真实时钟漂移，令
# build_snapshot 的新鲜度守卫（滞后≥FRESH_WARN_DAYS 封顶 60%）误触发，掩盖
# 本文件真正要测的 herd/regime 语义（2026-10-04 实证：硬编码 2026-09-30 滞后 4 天恒红）。
_TODAY = _date.today().isoformat()


# ───────────── 夹具 ─────────────

def _mk_history_dicts(n: int = 30, missing_last: bool = False) -> list[dict]:
    """中性 25 日 + 末 5 日极端红挤（末日 rr=93 / 涨停 240）。missing_last 模拟缺数日。"""
    import random
    rng = random.Random(11)
    rows = []
    base = pd.date_range("2026-07-01", periods=n + 1, freq="B").strftime("%Y-%m-%d")
    for i in range(n - 4):
        rows.append({"date": base[i], "red_ratio": 50 + rng.uniform(-4, 4),
                     "limit_up": float(rng.randint(20, 40)),
                     "limit_down": float(rng.randint(0, 8)),
                     "up_count": 2000.0, "down_count": 2000.0})
    for j, i in enumerate(range(n - 4, n + 1)):  # 末 5 日连续强红 + 涨停爆量
        r = {"date": base[i], "red_ratio": 85.0 + 2 * j, "limit_up": 200.0 + 10 * j,
             "limit_down": 2.0, "up_count": 3800.0, "down_count": 300.0}
        if missing_last and j == 4:
            r["red_ratio"] = None
            r["limit_up"] = None
        rows.append(r)
    return rows


@pytest.fixture()
def history_file(tmp_path):
    p = tmp_path / "shepherd_history.json"
    p.write_text(json.dumps(_mk_history_dicts(), ensure_ascii=False), encoding="utf-8")
    return str(p)


@pytest.fixture(autouse=True)
def _clear_cache():
    decision._dual_factor_cache["value"] = None
    decision._dual_factor_cache["ts"] = 0.0
    yield
    decision._dual_factor_cache["value"] = None
    decision._dual_factor_cache["ts"] = 0.0


# ───────────── keep_nan 门控隐患修复 ─────────────

def test_keep_nan_preserves_missing_day(tmp_path):
    """keep_nan=True 保留缺数日 NaN（可甄别）；默认 False 填 0（既有类比行为）。"""
    p = tmp_path / "h.json"
    p.write_text(json.dumps(_mk_history_dicts(missing_last=True)), encoding="utf-8")
    df_nan = load_breadth_history(path=str(p), keep_nan=True)
    assert np.isnan(df_nan["red_ratio"].iloc[-1])
    df_fill = load_breadth_history(path=str(p))
    assert df_fill["red_ratio"].iloc[-1] == 0.0


# ───────────── compute_dual_factor_inputs ─────────────

def test_inputs_unavailable_when_file_missing(tmp_path):
    """历史文件缺失 → available=False + 全 None（不臆造），且不写缓存。"""
    out = decision.compute_dual_factor_inputs(history_path=str(tmp_path / "nope.json"))
    assert out["available"] is False
    assert out["herd_score"] is None and out["regime_state"] is None
    assert decision._dual_factor_cache["value"] is None  # 失败不缓存（下次重试）


def test_inputs_from_fixture(tmp_path):
    """末 5 日极端红挤 → 普涨(conf≈0.8) + 拥挤度≥85 greed + as_of=末日。"""
    p = tmp_path / "h.json"
    p.write_text(json.dumps(_mk_history_dicts()), encoding="utf-8")
    out = decision.compute_dual_factor_inputs(history_path=str(p))
    assert out["available"] is True
    assert out["regime_state"] == "普涨"
    assert out["regime_confidence"] == pytest.approx(0.8, abs=0.05)
    assert out["herd_score"] is not None and out["herd_score"] >= 85
    assert out["herd_side"] == "greed"
    assert out["detail"]["rows"] == 31


def test_success_result_cached(tmp_path):
    """成功结果写缓存（同参二次调用命中，不再读盘）。"""
    p = tmp_path / "h.json"
    p.write_text(json.dumps(_mk_history_dicts()), encoding="utf-8")
    decision.compute_dual_factor_inputs(history_path=str(p))
    # history_path 注入不缓存——用默认路径（DATA_DIR）验证缓存写入
    (tmp_path / "shepherd_history.json").write_text(
        json.dumps(_mk_history_dicts()), encoding="utf-8")
    import unittest.mock as mock
    decision._dual_factor_cache["value"] = None
    with mock.patch.object(decision, "DATA_DIR", str(tmp_path)):
        a = decision.compute_dual_factor_inputs()
        assert a["available"] is True
        assert decision._dual_factor_cache["value"] is not None
        b = decision.compute_dual_factor_inputs()
        assert b is decision._dual_factor_cache["value"]


# ───────────── build_snapshot 自动接线 ─────────────

def test_build_snapshot_wires_herd(tmp_path, monkeypatch):
    """快照链自动消费双因子：极端红挤日 reasons 含「羊群」，仓位 93→85。"""
    (tmp_path / "shepherd_history.json").write_text(
        json.dumps(_mk_history_dicts()), encoding="utf-8")
    monkeypatch.setattr(decision, "DATA_DIR", str(tmp_path))
    snap = decision.build_snapshot(
        _TODAY, {"date": _TODAY}, 80.0,
        {"score": 70, "bias": "偏多", "cycle": {"name": "主升高潮"}},
        {"overall": None, "actionable": True}, None, event_adj=0)
    pos = snap["position"]
    assert pos["pct"] == 85  # 80+8+5=93；红挤极端 -8 → 85（勿用 90：103-8=95 被 clamp 吞）
    assert any("羊群" in r for r in pos["reasons"])


def test_build_snapshot_degrades_without_history(tmp_path, monkeypatch):
    """无历史文件 → 双因子全 None → 快照行为与旧版一致（reasons 无羊群条目）。"""
    monkeypatch.setattr(decision, "DATA_DIR", str(tmp_path))
    snap = decision.build_snapshot(
        _TODAY, {"date": _TODAY}, 90.0,
        {"score": 70, "bias": "偏多", "cycle": {"name": "主升高潮"}},
        {"overall": None, "actionable": True}, None, event_adj=0)
    pos = snap["position"]
    assert pos["pct"] == 95  # 103→clamp95；无 herd 调节
    assert not any("羊群" in r for r in pos["reasons"])
    assert not any("状态门控" in r for r in pos["reasons"])
