"""
tests/test_shepherd_ladder.py — 连板晋级率落盘 + 跨日递推 + 接入预判引擎

覆盖：
  · record_ladder_snapshot 落盘（按日期覆盖、空分布不写）
  · ladder_promotion_rates 跨日晋级率（首板→二板 / 2→3 等）
  · current_promo_as_indicators 打包成 forecast 派生指标（缺历史返回 {}）
  · forecast_next_day 在 today 含 ladder_promo 时：drivers 出现该指标 + 命中晋级率联动规则
"""
import os

import modules.shepherd_ladder as sl


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "LADDER_FILE", str(tmp_path / "ladder.json"))


def _dist(*pairs):
    return [(b, c) for b, c in pairs]


def test_record_and_promotion_rates(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    # 昨日：首板100 / 2板20 / 3板5
    assert sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20), (3, 5)), 3, 25)
    # 今日：首板80 / 2板25 / 3板4
    assert sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25), (3, 4)), 3, 29)

    pr = sl.ladder_promotion_rates()
    assert pr["ready"] is True
    assert pr["days"] == 2
    # 首板→二板晋级率 = 25/100 = 25.0%
    assert pr["rates"]["2b"] == 25.0
    # 2→3 晋级率 = 4/20 = 20.0%
    assert pr["rates"]["3b"] == 20.0
    # 综合优先取首板→二板
    assert pr["overall"] == 25.0


def test_less_than_two_days_not_ready(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    pr = sl.ladder_promotion_rates()
    assert pr["ready"] is False
    assert pr["overall"] is None
    # 缺历史时不应污染 today
    assert sl.current_promo_as_indicators() == {}


def test_current_promo_packaging(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    ind = sl.current_promo_as_indicators()
    assert ind == {"ladder_promo": 25.0}


def test_overall_falls_back_when_2b_missing(tmp_path, monkeypatch):
    """2b 档算不出（昨日缺首板档）时，overall 必须回落到可用档均值而非 None。

    回归背景：页面曾用 `f"{rates['2b']:.1f}"` 直接格式化，2b 为 None 时抛 TypeError
    被 except 吞掉，表现为「晋级率整块不显示」。现页面改用 overall + 非空守卫，
    本用例锁死「overall 在 2b 缺失时仍有值」这一前提。
    """
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((2, 20)), 2, 20)   # 昨日无首板档
    sl.record_ladder_snapshot("2026-08-28", _dist((3, 4)), 3, 4)     # 今日 3板4家
    pr = sl.ladder_promotion_rates()
    assert pr["ready"] is True
    assert pr["rates"]["2b"] is None          # 首板→二板确实算不出
    assert pr["rates"]["3b"] == 20.0          # 4/20
    assert pr["overall"] == 20.0              # 回落到可用档均值，绝不是 None


def test_record_ignores_empty_distribution(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    assert sl.record_ladder_snapshot("2026-08-28", None) is False
    assert sl.record_ladder_snapshot("2026-08-28", []) is False
    assert not os.path.exists(sl.LADDER_FILE)


def test_forecast_includes_ladder_promo_driver_and_signal():
    import modules.shepherd_forecast as sf
    today = {"ladder_promo": 25.0}
    fc = sf.forecast_next_day(today, None)
    keys = [d["key"] for d in fc["drivers"]]
    assert "ladder_promo" in keys
    # 晋级率≥25% 应命中「接力延续」联动
    ids = [s["id"] for s in fc["signals"]]
    assert "relay_promo_strong" in ids


def test_forecast_relay_weak_when_low(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    # 造一段历史让 current_promo 返回低值，验证弱接力规则
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 200), (2, 50)), 2, 50)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 200), (2, 10)), 2, 10)  # 10/200=5%
    import modules.shepherd_forecast as sf
    today = sf.with_derived({})  # 空，先不注入
    # 直接注入低晋级率
    promo = sl.current_promo_as_indicators()
    assert promo["ladder_promo"] == 5.0
    fc = sf.forecast_next_day({"ladder_promo": 5.0}, None)
    ids = [s["id"] for s in fc["signals"]]
    assert "relay_promo_weak" in ids
