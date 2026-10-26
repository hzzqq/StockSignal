# -*- coding: utf-8 -*-
"""
tests/test_macd_divergence.py
====================================
T-333 R7 MACD 底背离确认守卫（benchmark 采纳清单 L153：K 线斜率向下 + MACD 上拐 +
放量，作 A1 加分确认，减少超跌假反弹）。

契约（spec 冻结 2026-10-26，含 v2 修正：破位幅度上限）：

technical.detect_bullish_divergence(df, lookback=30, recent_n=5) 纯函数，三条件 AND：
- A 价微破新低：min(close[recent 段]) < min(close[prior 段])，且破位幅度
  (prior_min - recent_min) / prior_min ≤ 5%（磨底微破位语义——崩盘式暴破
  （如 5 根 -25%）属趋势加速，不作反弹确认）；
- B MACD 不创新低：min(hist[recent]) > min(hist[prior])（柱背离）或
  min(dif[recent]) > min(dif[prior])（DIF 背离）；MACD 口径与 compute_macd
  完全一致（EMA dropna 后计算，dif=EMA12-EMA26、dea=EMA(dif,9)、hist=(dif-dea)*2）；
- C 放量确认：vol[-1] > mean(vol[-recent_n-5:-recent_n])（末根 > 前 5 根均量）；
- 数据不足（close dropna 后 < lookback+30）/ 缺 close 或 volume 列 / 全 NaN →
  {"divergence": False, "status": "unavailable", "reason": ...}（不编造判定）。

recommend_engine.apply_divergence_confirm(a1, dv)：
- a1 为 None → None；
- dv 无效（None / 非 dict / status != "ok" / divergence 为 False）→ a1 原样返回（同一对象）；
- 命中 → a1 的**副本**：score = min(100, score + 5)（确认加分封顶 100），reasons
  归一化后追加「MACD底背离确认（放量）」并保持逗号拼接 str 形态（与
  _score_for_picker 输出形态一致，阶段 3 _normalize_reasons 兼容）。

主流程接线（generate_daily_recommendation candidates 组装循环）：
- a1 算分后调用 apply_divergence_confirm(a1, detect_bullish_divergence(df))；
- 不动 backtest._score_for_picker 本体（回测口径零影响）。

mutation：价新低比较符反转 / 确认加分旁路 / 放量条件旁路 / 不可得谎报 ok → 对应用例变红。
"""
import inspect

import numpy as np
import pandas as pd
import pytest

from modules import recommend_engine as re_eng
from modules.technical import detect_bullish_divergence


# ─────────────── 合成数据（参数经 E:/tmp/t333_calib2.py 数值校准） ───────────────
def _classic_divergence_df(break_tail=None):
    """经典底背离：缓跌 75 根(20→10) → 反弹 20 根(10→12.5) → 5 根微破位 + 放量。"""
    tail = list(np.linspace(12.5, 9.8, 5)) if break_tail is None else break_tail
    closes = list(np.linspace(20, 10, 75)) + list(np.linspace(10, 12.5, 20)) + tail
    vols = [1_000_000.0] * 95 + [3_000_000.0] * 5
    return _mk(closes, vols)


def _mk(closes, vols):
    return pd.DataFrame({
        "close": closes, "volume": vols,
        "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
    })


# ─────────────── 纯函数：detect_bullish_divergence ───────────────
def test_classic_divergence_detected():
    """经典底背离（微破位 2% + DIF 不创新低 + 放量）→ 命中。"""
    r = detect_bullish_divergence(_classic_divergence_df())
    assert r["status"] == "ok"
    assert r["divergence"] is True
    assert r["volume_confirm"] is True
    assert r["kind"] in ("dif", "hist", "hist+dif")


def test_break_within_5pct_boundary_confirmed():
    """破位恰好 5%（≤ 上限边界）→ 仍算磨底微破位，命中。"""
    tail = list(np.linspace(12.5, 9.5, 5))  # 9.5/10.0 = 破位 5%
    r = detect_bullish_divergence(_classic_divergence_df(break_tail=tail))
    assert r["status"] == "ok" and r["divergence"] is True


def test_crash_break_beyond_5pct_rejected():
    """崩盘式暴破（5 根 -25%，远超 5% 上限）→ 不作反弹确认。"""
    tail = list(np.linspace(12.5, 7.5, 5))
    r = detect_bullish_divergence(_classic_divergence_df(break_tail=tail))
    assert r["status"] == "ok" and r["divergence"] is False


def test_no_volume_rejected():
    """形态成立但未放量 → 三条件 AND 不满足，不确认。"""
    closes = (list(np.linspace(20, 10, 75)) + list(np.linspace(10, 12.5, 20))
              + list(np.linspace(12.5, 9.8, 5)))
    r = detect_bullish_divergence(_mk(closes, [1_000_000.0] * 100))
    assert r["status"] == "ok" and r["divergence"] is False
    assert r["volume_confirm"] is False


def test_flat_and_uptrend_no_divergence():
    """平价 / 单边上涨 → 无价新低，不确认。"""
    flat = detect_bullish_divergence(_mk([100.0] * 100, [1e6] * 100))
    up = detect_bullish_divergence(_mk(list(np.linspace(10, 20, 100)), [1e6] * 100))
    assert flat["divergence"] is False and up["divergence"] is False


def test_short_history_unavailable_not_false_ok():
    """close 样本 < lookback+30 → unavailable（不编造「无背离」）。"""
    r = detect_bullish_divergence(_mk([100.0, 101.0] * 25, [1e6] * 50))  # 50 根
    assert r["status"] == "unavailable"
    assert r["divergence"] is False
    assert r["reason"]


def test_missing_columns_or_all_nan_unavailable():
    """缺 volume 列 / close 全 NaN → unavailable。"""
    df = _classic_divergence_df().drop(columns=["volume"])
    r1 = detect_bullish_divergence(df)
    assert r1["status"] == "unavailable" and r1["divergence"] is False
    df2 = _classic_divergence_df()
    df2["close"] = np.nan
    r2 = detect_bullish_divergence(df2)
    assert r2["status"] == "unavailable" and r2["divergence"] is False


def test_none_or_empty_df_unavailable():
    """df=None / 空 DataFrame → unavailable 不抛异常。"""
    for bad in (None, pd.DataFrame()):
        r = detect_bullish_divergence(bad)
        assert r["status"] == "unavailable" and r["divergence"] is False


# ─────────────── apply_divergence_confirm（A1 确认加分） ───────────────
def _hit_dv():
    return {"divergence": True, "kind": "dif", "volume_confirm": True,
            "status": "ok", "reason": None}


def test_confirm_adds_5_capped_at_100_and_annotates():
    """命中：+5 封顶 100，reasons 保持 str 且含确认标注。"""
    a1 = {"score": 98.0, "reasons": "强趋势,短期趋势"}
    out = re_eng.apply_divergence_confirm(a1, _hit_dv())
    assert out is not a1, "必须返回副本，不得原地改 _score_for_picker 的返回"
    assert out["score"] == pytest.approx(100.0, abs=1e-9), "98+5 应封顶 100"
    assert out["reasons"] == "强趋势,短期趋势,MACD底背离确认（放量）"
    assert a1["score"] == 98.0, "原 dict 不得被改"


def test_confirm_midrange_score_adds_5():
    """中段分：82+5=87（封顶逻辑只在高分生效）。"""
    a1 = {"score": 82.0, "reasons": "超跌反弹"}
    out = re_eng.apply_divergence_confirm(a1, _hit_dv())
    assert out["score"] == pytest.approx(87.0, abs=1e-9)
    assert "MACD底背离确认（放量）" in out["reasons"]


def test_confirm_no_hit_or_invalid_returns_same_object():
    """未命中 / dv 无效 / a1 None → 原样返回（同一对象），不改分不加词。"""
    a1 = {"score": 82.0, "reasons": "超跌反弹"}
    no_hit = {"divergence": False, "kind": None, "volume_confirm": False,
              "status": "ok", "reason": None}
    unavail = {"divergence": False, "kind": None, "volume_confirm": None,
               "status": "unavailable", "reason": "x"}
    for dv in (None, {}, no_hit, unavail):
        out = re_eng.apply_divergence_confirm(a1, dv)
        assert out is a1, f"dv={dv!r} 应原样返回同一对象"
        assert out["score"] == 82.0
    assert re_eng.apply_divergence_confirm(None, _hit_dv()) is None


def test_confirm_with_list_reasons_normalized():
    """a1 reasons 为 list 形态（如调用方已归一）也能正确拼接。"""
    a1 = {"score": 82.0, "reasons": ["超跌反弹", "强趋势"]}
    out = re_eng.apply_divergence_confirm(a1, _hit_dv())
    assert isinstance(out["reasons"], str)
    assert "超跌反弹" in out["reasons"] and "MACD底背离确认（放量）" in out["reasons"]


# ─────────────── 主流程接线（源码契约） ───────────────
def test_wiring_in_source():
    src_eng = inspect.getsource(re_eng)
    assert "apply_divergence_confirm(a1, detect_bullish_divergence(df)" in src_eng, \
        "candidates 组装循环未接 MACD 底背离确认"
    assert "from modules.technical import" in src_eng or \
        "detect_bullish_divergence" in src_eng, "未导入背离检测函数"
    # backtest 本体不得被改（回测口径零影响）
    from modules import backtest as bt
    src_bt = inspect.getsource(bt)
    assert "detect_bullish_divergence" not in src_bt, "backtest 模块不得引入背离检测"
