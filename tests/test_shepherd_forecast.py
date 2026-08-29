"""
tests/test_shepherd_forecast.py — 牧羊人「次日走势预判」引擎单元测试

锁住以下不变量（防止后续调阈值/加规则时悄悄改坏）：
- 情绪周期六阶段定位的判定优先级与核心阈值
- 关键联动规则（V反双确认 / 主升确认 / 退潮确认 / 弱修复 / 恐慌见底）
- 缺失数据（None/NaN）不误触发规则、不抛异常
- 次日情绪评分归一化（缺失维度不计入分母）
- 方向投票与置信度区间

全程离线，纯函数调用，绝不触网。
"""
import pytest

from modules import shepherd_forecast as sf


# ─────────────────────────────────────────────────────────────
#  联动规则
# ─────────────────────────────────────────────────────────────
def test_v_reversal_double_confirm():
    """炸板率≥50% 且 回头波≥30家 → 触发 V反双确认（杨哥核心规律）。"""
    hits = sf.eval_linkages({"zt_fail_ratio": 55.0, "hb_wave10": 35.0})
    ids = [h["id"] for h in hits]
    assert "v_reversal_double" in ids


def test_v_reversal_not_trigger_below_threshold():
    """未达阈值不触发（炸板率 45% <50%）。"""
    hits = sf.eval_linkages({"zt_fail_ratio": 45.0, "hb_wave10": 35.0})
    assert "v_reversal_double" not in [h["id"] for h in hits]


def test_main_rise_confirm():
    """炸板率<20% + 最高板≥5 + 昨板溢价>1% → 主升确认。"""
    hits = sf.eval_linkages({
        "zt_fail_ratio": 15.0, "connect_hl": 6.0, "zt_prev_ret": 2.5,
    })
    assert "main_rise_confirm" in [h["id"] for h in hits]


def test_retreat_confirm():
    """炸板率≥40% + 梯队<8家 → 退潮确认。"""
    hits = sf.eval_linkages({"zt_fail_ratio": 45.0, "connect_2b": 3.0})
    assert "retreat_confirm" in [h["id"] for h in hits]


def test_panic_bottom():
    """跌停≥60 且 中位数跌幅>3% → 恐慌见底。"""
    hits = sf.eval_linkages({"limit_down": 90.0, "median_chg": -5.0})
    assert "panic_bottom" in [h["id"] for h in hits]


def test_weak_repair_needs_prev():
    """缩量弱修复需要 prev 做环比；无 prev 时不触发（避免误判）。"""
    today = {"turnover_amt": 15000.0, "zt_fail_ratio": 30.0}
    # 无 prev → 不触发
    assert "weak_repair" not in [h["id"] for h in sf.eval_linkages(today)]
    # 有 prev 且今日缩量 → 触发
    prev = {"turnover_amt": 20000.0}
    assert "weak_repair" in [h["id"] for h in sf.eval_linkages(today, prev)]
    # 有 prev 但今日放量 → 不触发
    prev2 = {"turnover_amt": 12000.0}
    assert "weak_repair" not in [h["id"] for h in sf.eval_linkages(today, prev2)]


def test_weak_repair_none_safe():
    """prev 中 turnover_amt 为 None → 不触发且不抛异常（回归：曾报 float(None) TypeError）。"""
    today = {"turnover_amt": 15000.0, "zt_fail_ratio": 30.0}
    prev = {"turnover_amt": None}
    assert "weak_repair" not in [h["id"] for h in sf.eval_linkages(today, prev)]


def test_missing_indicator_no_crash():
    """全空输入不抛异常、不命中任何规则。"""
    assert sf.eval_linkages({}) == []
    assert sf.eval_linkages({}, {}) == []


def test_nan_value_no_crash():
    """NaN 值不误触发规则。"""
    nan = float("nan")
    hits = sf.eval_linkages({"zt_fail_ratio": nan, "hb_wave10": nan})
    assert "v_reversal_double" not in [h["id"] for h in hits]


# ─────────────────────────────────────────────────────────────
#  情绪周期定位
# ─────────────────────────────────────────────────────────────
def test_locate_ice_point():
    """跌停≥80 且 最高板≤4 → 冰点。"""
    c = sf.locate_cycle({"limit_down": 100.0, "connect_hl": 3.0, "limit_up": 30.0})
    assert c["id"] == "ice"


def test_locate_ice_point_without_limit_down():
    """无跌停数据时，涨停枯竭(<30) + 高度≤3 也能判冰点（历史数据鲁棒性）。"""
    c = sf.locate_cycle({"limit_up": 25.0, "connect_hl": 3.0})
    assert c["id"] == "ice"


def test_locate_retreat_by_height_cliff():
    """最高板断崖 ≥2 板 → 退潮。"""
    c = sf.locate_cycle({"connect_hl": 4.0}, {"connect_hl": 7.0})
    assert c["id"] == "retreat"


def test_locate_retreat_by_thin_ladder():
    """梯队≤2家 + 炸板率≥45% → 退潮（无跌停数据时也能判）。"""
    c = sf.locate_cycle({"connect_2b": 2.0, "zt_fail_ratio": 50.0})
    assert c["id"] == "retreat"


def test_locate_diverge():
    """炸板率≥40 + 涨停≥50 → 高潮分化。"""
    c = sf.locate_cycle({"zt_fail_ratio": 45.0, "limit_up": 60.0})
    assert c["id"] == "diverge"


def test_locate_main_rise():
    """最高板≥6 + 炸板率<20 → 主升高潮。"""
    c = sf.locate_cycle({"connect_hl": 7.0, "zt_fail_ratio": 15.0, "zt_prev_ret": 3.0})
    assert c["id"] == "main"
    assert any("7 板" in r for r in c["reasons"])


def test_locate_confirm_on_height_upgrade():
    """炸板率<25 + 高度晋级 → 修复确认。"""
    c = sf.locate_cycle(
        {"zt_fail_ratio": 20.0, "connect_hl": 5.0, "zt_prev_ret": 1.5},
        {"connect_hl": 4.0},
    )
    assert c["id"] == "confirm"


def test_locate_probe_fallback_robust():
    """只给核心指标但不达标 → 落修复试探，且 reasons 说明为何没进更乐观档位。

    这是历史回测的关键：不能因为 limit_down/median_chg 缺失就全落兜底，
    也不能因为缺数据就崩。本例炸板率 30%≥25%，应明确给出「封板质量未达标」。
    """
    c = sf.locate_cycle({"zt_fail_ratio": 30.0, "connect_hl": 4.0})
    assert c["id"] == "probe"
    assert any("未达标" in r or "炸板率" in r for r in c["reasons"])


def test_locate_empty_input_safe():
    """空输入不崩，落兜底。"""
    c = sf.locate_cycle({})
    assert c["id"] == "probe"


# ─────────────────────────────────────────────────────────────
#  次日情绪评分
# ─────────────────────────────────────────────────────────────
def test_score_all_dims_present():
    """五项齐全 → 满分 100 归一化，强情绪应得高分。"""
    s = sf.score_next_day({
        "zt_prev_ret": 4.0, "connect_hl": 8.0, "connect_2b": 25.0,
        "zt_fail_ratio": 10.0, "limit_down": 2.0,
    })
    assert 0 <= s["total"] <= 100
    assert s["covered"] == 100
    assert s["total"] >= 70  # 强势市场应高分


def test_score_weak_market_low():
    """弱势市场应得低分。"""
    s = sf.score_next_day({
        "zt_prev_ret": -3.0, "connect_hl": 2.0, "connect_2b": 2.0,
        "zt_fail_ratio": 45.0, "limit_down": 40.0,
    })
    assert s["total"] <= 35


def test_score_partial_dims_normalized():
    """缺失维度不计入分母：只给昨板溢价满分，归一化后仍接近 100。"""
    s = sf.score_next_day({"zt_prev_ret": 5.0})
    assert s["covered"] == 25
    assert s["total"] == pytest.approx(100.0, abs=0.5)


def test_score_empty_returns_neutral():
    """空输入返回中性 50，covered=0。"""
    s = sf.score_next_day({})
    assert s["total"] == 50.0
    assert s["covered"] == 0


def test_score_zt_fail_ratio_u_shape():
    """炸板率评分是 U 型：极低(封板稳)与极高(抛压释放)都偏正面，中段最差。"""
    low = sf._score_dim("zt_fail_ratio", 10.0, 100)     # 封板稳
    mid = sf._score_dim("zt_fail_ratio", 32.0, 100)     # 分歧
    high = sf._score_dim("zt_fail_ratio", 60.0, 100)    # 抛压释放
    assert low > mid
    assert high > mid


# ─────────────────────────────────────────────────────────────
#  主入口 forecast_next_day
# ─────────────────────────────────────────────────────────────
def test_forecast_structure_complete():
    """返回结构完整（页面依赖这些键）。"""
    r = sf.forecast_next_day({
        "zt_fail_ratio": 15.0, "connect_hl": 6.0, "zt_prev_ret": 3.0,
        "connect_2b": 18.0, "limit_down": 3.0,
    })
    for k in ("cycle", "score", "score_dims", "bias", "confidence",
              "scenario", "signals", "drivers", "summary"):
        assert k in r, f"缺少返回键 {k}"
    assert len(r["scenario"]) == 3
    assert sum(s["prob"] for s in r["scenario"]) == 100


def test_forecast_bullish_on_main_rise():
    """主升确认 + 接力环境好 → 方向偏多。"""
    r = sf.forecast_next_day({
        "zt_fail_ratio": 12.0, "connect_hl": 7.0, "zt_prev_ret": 3.5,
        "connect_2b": 18.0, "limit_down": 2.0, "limit_up": 80.0,
    })
    assert r["bias"] == "偏多"
    assert r["cycle"]["id"] == "main"


def test_forecast_bearish_on_retreat():
    """退潮定位 → 方向偏空。"""
    r = sf.forecast_next_day(
        {"connect_hl": 3.0, "zt_fail_ratio": 50.0, "connect_2b": 2.0, "limit_down": 25.0},
        {"connect_hl": 7.0},
    )
    assert r["bias"] == "偏空"


def test_forecast_confidence_bounded():
    """有数据时置信度恒在 10~95（不能过度自信）。"""
    for data in (
        {"zt_fail_ratio": 50.0, "hb_wave10": 40.0, "connect_hl": 7.0,
         "zt_prev_ret": 3.0, "connect_2b": 20.0, "limit_down": 2.0},
        {"connect_hl": 1.0},
        {"zt_fail_ratio": 16.3, "connect_hl": 7.0, "zt_prev_ret": 3.17,
         "connect_2b": 18.0, "limit_down": 3.0, "limit_up": 82.0},
    ):
        r = sf.forecast_next_day(data)
        assert 10 <= r["confidence"] <= 95


def test_forecast_empty_input_safe():
    """空输入返回中性 50 且不抛异常；无数据即零置信（confidence=0，早退分支）。

    注意：空输入走 forecast_next_day 顶部的早退分支，confidence=0 而非 10~95，
    语义是「完全没有数据 → 完全不可信」，与「有数据但方向不明 → 低置信」区分开。
    """
    r = sf.forecast_next_day({})
    assert r["bias"] == "中性"
    assert r["score"] == 50.0
    assert r["signals"] == []
    assert r["confidence"] == 0
    assert r["cycle"] is None


def test_forecast_drivers_sorted_by_weight():
    """drivers 按权重倒序（页面展示「最相关的指标」在最前）。"""
    r = sf.forecast_next_day({
        "zt_fail_ratio": 20.0, "hb_wave10": 10.0, "zt_prev_ret": 2.0,
        "connect_hl": 5.0, "connect_2b": 10.0, "fc_ratio": 0.5, "limit_down": 5.0,
    })
    weights = [d["weight"] for d in r["drivers"]]
    assert weights == sorted(weights, reverse=True)


def test_forecast_drivers_exclude_missing():
    """缺失指标不进入 drivers（避免页面显示空行）。"""
    r = sf.forecast_next_day({"zt_fail_ratio": 20.0})
    keys = [d["key"] for d in r["drivers"]]
    assert "zt_fail_ratio" in keys
    assert "connect_hl" not in keys


def test_forecast_bands_hit():
    """档位解读命中：炸板率 60% 应命中「抛压释放」档（V反）。"""
    r = sf.forecast_next_day({"zt_fail_ratio": 60.0})
    drv = [d for d in r["drivers"] if d["key"] == "zt_fail_ratio"][0]
    assert drv["band"] == "抛压释放"
    assert "V" in drv["desc"]
