"""
tests/test_recommend_r4r5.py
============================
T-270 荐股引擎 R4（市况自适应权重）+ R5（相对大盘强度）守卫。

R4 契约（market_regime_weights 纯函数）：
- 高温（≥70）：momentum/breakout/dual_trend 上调、multi_factor/fund_flow 下调、和=1；
- 低温（≤30）：multi_factor/fund_flow 上调、和=1；
- 中间档 / None / 非数值 / NaN → None（回落静态默认，诚实降级）；
- 主流程接线：fusion_score 收到 regime_weights（None 时静态默认），pick 元数据
  如实携带 weights_source + temperature（防「悄悄换权重」）。

R5 契约（_momentum_score 相对大盘强度）：
- 传入 index_ret20 → 用「个股 20 日收益 − 指数 20 日收益」打分，reasons 如实标注；
- index_ret20=None → 如实回落绝对动量（reasons 标注「大盘强度不可得」）；
- 主流程接线：指数收益循环外一次性取（_index_ret20_safe），pick 元数据携带。

mutation：R4 高温方向反转 / R5 删相对计算 → 对应用例变红。
"""
import numpy as np
import pandas as pd
import pytest

from modules import recommend_engine as re_eng


def _static():
    return dict(re_eng.ALGO_WEIGHTS)


# ─────────────── R4 ───────────────
def test_r4_hot_regime_shifts_to_trend():
    w = re_eng.market_regime_weights(80)
    s = _static()
    assert w is not None
    assert w["momentum"] > s["momentum"] and w["breakout"] > s["breakout"]
    assert w["dual_trend"] > s["dual_trend"]
    assert w["multi_factor"] < s["multi_factor"] and w["fund_flow"] < s["fund_flow"]
    assert abs(sum(w.values()) - 1.0) < 1e-6, "权重和必须守恒为 1"


def test_r4_cold_regime_shifts_to_reversal():
    w = re_eng.market_regime_weights(20)
    s = _static()
    assert w is not None
    assert w["multi_factor"] > s["multi_factor"] and w["fund_flow"] > s["fund_flow"]
    assert w["momentum"] < s["momentum"] and w["breakout"] < s["breakout"]
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_r4_neutral_or_unavailable_returns_none():
    """中间档 / None / 非数值 / NaN → None（诚实降级，不假装自适应）。"""
    assert re_eng.market_regime_weights(50) is None
    assert re_eng.market_regime_weights(None) is None
    assert re_eng.market_regime_weights("abc") is None
    assert re_eng.market_regime_weights(float("nan")) is None


def test_r4_wiring_and_metadata_in_source():
    """主流程接线契约：regime_weights 传入 fusion_score + 元数据防悄悄换权重。"""
    src = (re_eng, )
    import inspect
    code = inspect.getsource(re_eng.generate_daily_recommendations if hasattr(
        re_eng, "generate_daily_recommendations") else re_eng)
    assert "market_regime_weights(regime_temperature)" in code
    assert "fusion_score(algo_raw, weights=regime_weights)" in code
    assert '"weights_source"' in code, "权重来源元数据缺失（防悄悄换权重）"


# ─────────────── R5 ───────────────
def _df(ret20: float, n: int = 30) -> pd.DataFrame:
    """构造 n 行日线：前 n-1 行收盘 100，末行 = 100×(1+ret20)。量能恒定（量比 1）。"""
    close = [100.0] * (n - 1) + [round(100.0 * (1 + ret20), 4)]
    return pd.DataFrame({
        "close": close, "volume": [1_000_000.0] * n,
        "high": [c * 1.01 for c in close], "low": [c * 0.99 for c in close],
    })


def test_r5_relative_beats_absolute_when_stock_lags_index():
    """普涨日场景：个股 +5%、大盘 +4% → 相对动量分应低于绝对动量分（区分度恢复）。"""
    df = _df(0.05)
    rel = re_eng._momentum_score(df, index_ret20=0.04)
    absolute = re_eng._momentum_score(df)
    assert rel["score"] < absolute["score"], "相对大盘强度未生效（普涨日区分度未恢复）"
    assert "相对大盘" in rel["reasons"][0] and "指数" in rel["reasons"][0]


def test_r5_fallback_when_index_unavailable():
    """指数不可得 → 如实回落绝对动量并标注（绝不编造大盘数字）。"""
    df = _df(0.05)
    r = re_eng._momentum_score(df, index_ret20=None)
    assert "大盘强度不可得" in r["reasons"][0]
    assert r == re_eng._momentum_score(df)  # 与不传参数完全一致


def test_r5_negative_relative_underperforms():
    """个股 -2% 而大盘 +3% → 相对 -5%，分数应低于 50（跑输大盘的票不该拿动量高分）。"""
    r = re_eng._momentum_score(_df(-0.02), index_ret20=0.03)
    assert r["score"] < 50
    assert "相对大盘" in r["reasons"][0]


def test_r5_wiring_single_fetch_in_source():
    """接线契约：指数收益循环外一次性取；pick 行携带 regime 与 index_ret20 元数据。"""
    import inspect
    code = inspect.getsource(re_eng)
    assert "_idx_ret20 = _index_ret20_safe()" in code
    assert "_momentum_score(df, index_ret20=_idx_ret20)" in code
    assert '"regime": regime_meta' in code and '"index_ret20": _idx_ret20' in code
