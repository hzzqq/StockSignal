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


def _pad_days(days: int, end_date: str, dist=None):
    """在 end_date 之前垫 days 天占位快照，用于跨过 MIN_PROMO_DAYS 样本门槛。

    晋级率只用「最近 2 天」算，垫底天数不改变比率本身，只增加 days 计数；
    这样既能验证决策可达路径，又不扭曲被测比率。
    """
    from datetime import date, timedelta
    d_end = date.fromisoformat(end_date)
    d = dist or [(1, 100), (2, 20)]
    for i in range(days, 0, -1):
        sl.record_ladder_snapshot((d_end - timedelta(days=i)).isoformat(),
                                  list(d), 2, sum(c for _, c in d))


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
    _pad_days(sl.MIN_PROMO_DAYS - 2, "2026-08-27")   # 垫够样本门槛
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    ind = sl.current_promo_as_indicators()
    assert ind == {"ladder_promo": 25.0}


def test_promo_small_sample_not_actionable(tmp_path, monkeypatch):
    """样本不足 MIN_PROMO_DAYS 天：数值可展示，但不得驱动决策。

    回归背景（2026-09-05 锐评发现）：晋级率只用「最近 2 天」算，即 1 个交易日对；
    而 ready=True 仅代表"算得出来"，不代表"可信"。曾出现 6 天样本、单日比率 8.6%
    以 ready=True 身份经 current_promo_as_indicators() 注入 forecast 的 ladder_promo
    （weight=8）并驱动仓位建议——统计上属小样本过拟合。
    现引入 actionable 门控：数值仍返回供展示（confidence="low"），但不进决策链路。
    """
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)

    pr = sl.ladder_promotion_rates()
    assert pr["ready"] is True          # 技术语义：算得出来（保持不变）
    assert pr["days"] == 2
    assert pr["overall"] == 25.0        # 数值仍可用于页面展示
    assert pr["confidence"] == "low"
    assert pr["actionable"] is False    # 但不足以驱动决策
    # 核心守卫：小样本不得污染 forecast
    assert sl.current_promo_as_indicators() == {}


def test_promo_enough_sample_is_actionable(tmp_path, monkeypatch):
    """样本达到 MIN_PROMO_DAYS 天：actionable=True 且正常注入 forecast。"""
    _use_tmp(tmp_path, monkeypatch)
    _pad_days(sl.MIN_PROMO_DAYS - 2, "2026-08-27")
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)

    pr = sl.ladder_promotion_rates()
    assert pr["days"] == sl.MIN_PROMO_DAYS
    assert pr["confidence"] == "medium"
    assert pr["actionable"] is True
    assert sl.current_promo_as_indicators() == {"ladder_promo": 25.0}


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
    _pad_days(sl.MIN_PROMO_DAYS - 2, "2026-08-27")   # 垫够样本门槛
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


# ────────────────── 交易日判定 / 脏数据体检 / 软标记 ──────────────────
def test_trading_date_weekend_rolls_back_to_friday():
    """周末抓到的实时梯队其实是上周五收盘的数据，不能记成周六/周日。

    记错会让跨日晋级率递推把非交易日当「昨日」，结果直接算错。
    2026-08-28 周五 / 08-29 周六 / 08-30 周日 / 08-31 周一。
    """
    from datetime import datetime
    assert sl.trading_date(datetime(2026, 8, 28, 15, 30)) == "2026-08-28"
    assert sl.trading_date(datetime(2026, 8, 29, 10, 0)) == "2026-08-28"
    assert sl.trading_date(datetime(2026, 8, 30, 10, 0)) == "2026-08-28"
    assert sl.trading_date(datetime(2026, 8, 31, 10, 0)) == "2026-08-31"  # 周一 = 当天


def _set_updated_at(date, when):
    """改写某条的 updated_at。

    record_ladder_snapshot 写的是 now()，而测试造的历史日期都在过去 —— 不改写的话
    audit 的「补记滞后」判据会把它们全判成脏数据（生产环境不会这样：脚本当天跑，
    date 与 updated_at 天然同日）。要测「干净历史」就得先模拟成当天写入。
    """
    import json
    p = sl.LADDER_FILE
    h = json.load(open(p, encoding="utf-8"))
    if date in h:
        h[date]["updated_at"] = when
    with open(p, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def test_audit_detects_backfill_lag(tmp_path, monkeypatch):
    """主判据：updated_at 的日期 ≠ date → 补记数据，分布实为补记当日的梯队。"""
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 45), (2, 13), (3, 4), (6, 1)), 6, 18)
    # 模拟「8-30 打开页面时把当日梯队写到了 8-27 名下」
    _set_updated_at("2026-08-27", "2026-08-30T21:41:02")

    rep = sl.audit_history()
    assert "2026-08-27" in rep
    assert rep["2026-08-27"]["severity"] == "bad"
    assert rep["2026-08-27"]["reason"] == "补记滞后"


def test_audit_clean_history_is_empty(tmp_path, monkeypatch):
    """当天写、分布各异的历史不该被误报（避免审计变成狼来了）。"""
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    _set_updated_at("2026-08-27", "2026-08-27T15:30:00")
    _set_updated_at("2026-08-28", "2026-08-28T15:30:00")
    assert sl.audit_history() == {}


def test_audit_detects_duplicate_distribution(tmp_path, monkeypatch):
    """辅助判据：与相邻日分布逐档完全相同 → warn（真实市场极少完全一致）。"""
    _use_tmp(tmp_path, monkeypatch)
    d = _dist((1, 45), (2, 13), (3, 4), (6, 1))
    sl.record_ladder_snapshot("2026-08-27", d, 6, 18)
    sl.record_ladder_snapshot("2026-08-29", d, 6, 18)  # 与 8-27 逐档一致
    _set_updated_at("2026-08-27", "2026-08-27T15:30:00")
    _set_updated_at("2026-08-29", "2026-08-29T13:42:52")
    rep = sl.audit_history()
    assert any(r["severity"] == "warn" for r in rep.values())
    # 两条都是当天写的，不该被主判据（补记滞后）误伤
    assert all(r["reason"] != "补记滞后" for r in rep.values())


def test_audit_is_read_only(tmp_path, monkeypatch):
    """audit 只读，不改动文件 —— 它会被定时任务和人工反复跑。"""
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    before = open(sl.LADDER_FILE, encoding="utf-8").read()
    sl.audit_history()
    assert open(sl.LADDER_FILE, encoding="utf-8").read() == before


def test_mark_suspect_excludes_from_promotion(tmp_path, monkeypatch):
    """标记后该条不再参与晋级率计算。"""
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    assert sl.ladder_promotion_rates()["latest_date"] == "2026-08-28"

    assert sl.mark_suspect("2026-08-28") == 1
    pr = sl.ladder_promotion_rates()
    assert pr["latest_date"] == "2026-08-27"
    assert pr["ready"] is False  # 只剩一天，无法跨日递推


def test_unmark_suspect_restores(tmp_path, monkeypatch):
    """软标记必须可完整撤销 —— 数据从未被删除。"""
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    sl.mark_suspect("2026-08-28")
    assert sl.ladder_promotion_rates()["latest_date"] == "2026-08-27"

    assert sl.unmark_suspect("2026-08-28") == 1
    pr = sl.ladder_promotion_rates()
    assert pr["latest_date"] == "2026-08-28"
    assert pr["ready"] is True
    assert pr["latest"]["distribution"] == {1: 80, 2: 25}  # 原始数据完好


def test_mark_suspect_tolerates_missing_date(tmp_path, monkeypatch):
    """标记不存在的日期应安全返回 0，不抛异常。"""
    _use_tmp(tmp_path, monkeypatch)
    assert sl.mark_suspect("1999-01-01") == 0
    assert sl.unmark_suspect("1999-01-01") == 0


def test_prev_overall_returns_prior_day_rate(tmp_path, monkeypatch):
    """prev_overall 返回倒数第二天的综合晋级率（用于环比 delta）。"""
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    sl.record_ladder_snapshot("2026-08-29", _dist((1, 60), (2, 30)), 2, 30)
    # 2b 晋级率 = 当日2板 / 昨日1板：day3=30/80=37.5；day2=25/100=25.0
    assert sl.ladder_promotion_rates()["overall"] == 37.5
    assert sl.prev_overall() == 25.0


def test_prev_overall_insufficient_history(tmp_path, monkeypatch):
    """历史不足 3 日时 prev_overall 返回 None（无法算环比）。"""
    _use_tmp(tmp_path, monkeypatch)
    sl.record_ladder_snapshot("2026-08-27", _dist((1, 100), (2, 20)), 2, 20)
    sl.record_ladder_snapshot("2026-08-28", _dist((1, 80), (2, 25)), 2, 25)
    assert sl.prev_overall() is None
