# -*- coding: utf-8 -*-
"""决策「数据新鲜度守卫」回归测试。

锁死的核心契约：
    仓位建议必须如实暴露其所依赖数据的**真实截止日**；数据陈旧时必须在仓位旁
    直接告警，绝不让「半个月前的情绪/事件信号」冒充当日结论。

背景（真实事故，本测试即为防其复发而写）：
    P1 事件信号 ``latest_date=2026-08-14``、牧羊人情绪历史末行 ``2026-08-21``，
    而快照日期是 ``2026-09-04``。底层两个源**都有**日期，但聚合层把它丢了：
    ``snapshot['event_factor']`` 只剩 ``{available, long_count, adj}``，
    面板于是显示「数据滞后 0 日」且零警示——用户拿着 3 周前的信号加仓而不自知。

全部用例离线、确定性，**不读 11MB 的 P1 信号文件**。
"""
import datetime as _dt

import modules.decision as D
import modules.decision_track as DT
import modules.event_factor as EF
import modules.p1_signal as P1


def _iso(days_ago: int) -> str:
    """距今 N 天的日期串（用于构造可控的滞后天数）。"""
    return (_dt.date.today() - _dt.timedelta(days=days_ago)).isoformat()


# ──────────────────────────────────────────────
# assess_freshness：阈值判定
# ──────────────────────────────────────────────
def test_assess_freshness_ok_within_weekend_gap():
    """滞后 ≤3 天（覆盖周五→周一的正常周末间隔）仍算新鲜。"""
    out = D.assess_freshness({"源A": _iso(3), "源B": _iso(0)})
    assert out["status"] == "ok"
    assert out["max_lag_days"] == 3


def test_assess_freshness_warn_at_4_days():
    out = D.assess_freshness({"源A": _iso(4)})
    assert out["status"] == "warn"
    assert out["sources"]["源A"]["lag_days"] == 4


def test_assess_freshness_stale_at_8_days():
    out = D.assess_freshness({"源A": _iso(8)})
    assert out["status"] == "stale"


def test_assess_freshness_worst_source_wins():
    """任一源陈旧即整体陈旧，不能被新鲜源的平均/多数掩盖。"""
    out = D.assess_freshness({"新": _iso(1), "旧": _iso(20)})
    assert out["status"] == "stale"
    assert out["max_lag_days"] == 20


def test_assess_freshness_unknown_when_no_date():
    out = D.assess_freshness({"源A": None})
    assert out["status"] == "unknown"
    assert out["sources"]["源A"]["lag_days"] is None


# ──────────────────────────────────────────────
# _compute_event_adj：聚合层不得丢弃数据日期
# ──────────────────────────────────────────────
def test_compute_event_adj_carries_as_of(monkeypatch):
    """事件因子聚合结果必须带上 P1 信号的真实数据截止日。"""

    class _FakeLoader:
        def __init__(self, *a, **k):
            pass

        def latest_date(self, model):
            return "2026-08-14"

    # 两处均为函数内惰性导入，必须 patch 到各自模块上才生效
    monkeypatch.setattr(P1, "P1SignalLoader", _FakeLoader)
    monkeypatch.setattr(EF, "event_driven_long_list",
                        lambda top_n=50, model="ev", loader=None:
                        [{"symbol": f"s{i}"} for i in range(20)])

    out = D._compute_event_adj(top_n=50)
    assert out["adj"] == 2
    assert out["long_count"] == 20
    # 聚合层若再次丢弃日期，此断言立即失败
    assert out["as_of"] == "2026-08-14"


# ──────────────────────────────────────────────
# build_snapshot：暴露新鲜度 + 陈旧告警 + 不误报
# ──────────────────────────────────────────────
def _snap(event_as_of, temp_as_of, monkeypatch):
    monkeypatch.setattr(
        D, "_event_position_adj",
        lambda *a, **k: {"adj": 2, "long_count": 20, "as_of": event_as_of})
    return D.build_snapshot(
        date="2026-09-04",
        indicators={"date": temp_as_of} if temp_as_of else {},
        temp=33.0,
        forecast={"score": 0.4, "bias": 0.1, "confidence": 0.7},
        promo={"overall": 0.6},
    )


def test_snapshot_exposes_data_freshness(monkeypatch):
    snap = _snap(_iso(21), _iso(14), monkeypatch)
    fr = snap["data_freshness"]
    assert fr["status"] == "stale"
    assert fr["max_lag_days"] == 21
    assert fr["sources"]["事件因子"]["as_of"] == _iso(21)
    assert fr["sources"]["牧羊人情绪"]["lag_days"] == 14


def test_snapshot_warns_when_stale(monkeypatch):
    """陈旧数据必须在仓位理由里给出可见告警，且守卫已真的降仓（不是只"仅供参考"）。"""
    snap = _snap(_iso(21), _iso(14), monkeypatch)
    reasons = " ".join(snap["position"]["reasons"])
    assert "数据陈旧" in reasons
    assert "滞后 21 天" in reasons
    assert "主动降仓" in reasons
    assert "仅供参考" not in reasons  # 已真的降仓，不再是"仅供参考"的空头提示


def test_snapshot_silent_when_fresh(monkeypatch):
    """新鲜数据不得误报——否则警示会被当成「狼来了」而遭忽略。"""
    snap = _snap(_iso(1), _iso(1), monkeypatch)
    assert snap["data_freshness"]["status"] == "ok"
    reasons = " ".join(snap["position"]["reasons"])
    assert "数据陈旧" not in reasons


def test_snapshot_event_factor_carries_as_of(monkeypatch):
    snap = _snap("2026-08-14", "2026-08-21", monkeypatch)
    assert snap["event_factor"]["as_of"] == "2026-08-14"


def test_snapshot_temp_as_of_param_overrides_indicators(monkeypatch):
    """显式 temp_as_of 优先于 indicators['date']（温度来自非当日历史行时）。"""
    monkeypatch.setattr(D, "_event_position_adj",
                        lambda *a, **k: {"adj": 2, "long_count": 20, "as_of": None})
    snap = D.build_snapshot(
        date="2026-09-04", indicators={"date": "2026-09-04"}, temp=33.0,
        forecast={}, promo={}, temp_as_of="2026-08-21")
    assert snap["data_freshness"]["sources"]["牧羊人情绪"]["as_of"] == "2026-08-21"


# ──────────────────────────────────────────────
# 决策随新鲜度诚实降级（自找缺口 S12）：守卫必须真的让位，而非只提示
# ──────────────────────────────────────────────
def test_derive_position_caps_at_40_when_stale():
    """陈旧输入必须真的降仓：激进仓位被封顶 40%（不是只附一句"仅供参考"）。"""
    pos = D.derive_position(
        temp=85, bias="偏多", cycle_name="主升", overall_promo=65,
        event_adj=5, freshness_status="stale")
    assert pos["pct"] == 40
    _r = " ".join(pos["reasons"])
    assert "数据陈旧" in _r
    assert "封顶 40%" in _r


def test_derive_position_caps_at_60_when_warn():
    """偏旧输入（warn）封顶 60%。"""
    pos = D.derive_position(
        temp=85, bias="偏多", cycle_name="主升", overall_promo=65,
        event_adj=5, freshness_status="warn")
    assert pos["pct"] == 60
    _r = " ".join(pos["reasons"])
    assert "封顶 60%" in _r


def test_derive_position_no_freshness_action_when_ok():
    """新鲜数据：不施加新鲜度封顶，仓位保持激进原值；默认(None)等同 ok。"""
    pos_full = D.derive_position(
        temp=85, bias="偏多", cycle_name="主升", overall_promo=65, event_adj=5)
    pos_ok = D.derive_position(
        temp=85, bias="偏多", cycle_name="主升", overall_promo=65, event_adj=5,
        freshness_status="ok")
    assert pos_full["pct"] == pos_ok["pct"] == 95
    assert "封顶" not in " ".join(pos_ok["reasons"])


def test_derive_position_low_position_untouched_when_stale():
    """陈旧但本就保守的仓位：仅封顶不抬底，不得被惩罚性改动。"""
    pos = D.derive_position(
        temp=15, bias="中性", cycle_name="冰点", overall_promo=10,
        event_adj=0, freshness_status="stale")
    assert "封顶" not in " ".join(pos["reasons"])


def test_snapshot_caps_position_when_stale(monkeypatch):
    """集成：build_snapshot 把新鲜度透传后，陈旧场景下仓位被真正封顶。"""
    monkeypatch.setattr(
        D, "_event_position_adj",
        lambda *a, **k: {"adj": 2, "long_count": 20, "as_of": _iso(21)})
    snap = D.build_snapshot(
        date="2026-09-04",
        indicators={"date": _iso(14)},
        temp=85.0,
        forecast={"score": 0.4, "bias": "偏多", "confidence": 0.7},
        promo={"overall": 65},
    )
    assert snap["data_freshness"]["status"] == "stale"
    assert snap["position"]["pct"] <= 40
    assert "封顶" in " ".join(snap["position"]["reasons"])


# ──────────────────────────────────────────────
# 决策级守卫全量覆盖（自找缺口 S14）：收口 S12 部分 theater
# ──────────────────────────────────────────────
def test_snapshot_full_coverage_caps_when_ladder_stale(monkeypatch):
    """连板晋级率陈旧(即便牧羊人/事件/温度都新鲜)→ 整体 stale 且仓位封顶（守卫须覆盖全部输入源）。"""
    monkeypatch.setattr(
        D, "_event_position_adj",
        lambda *a, **k: {"adj": 2, "long_count": 20, "as_of": _iso(1)})
    snap = D.build_snapshot(
        date="2026-09-04",
        indicators={"date": _iso(1)},
        temp=85.0,
        forecast={"score": 0.4, "bias": "偏多", "confidence": 0.7},
        promo={"overall": 65},
        ladder_as_of=_iso(21),        # 连板晋级率滞后 21 天
        market_temp_as_of=_iso(1),    # 市场温度新鲜
    )
    assert "连板晋级率" in snap["data_freshness"]["sources"]
    assert snap["data_freshness"]["status"] == "stale"
    assert snap["position"]["pct"] <= 40
    assert "封顶" in " ".join(snap["position"]["reasons"])


def test_snapshot_full_coverage_ok_when_all_fresh(monkeypatch):
    """全部输入源新鲜（含连板晋级率/市场温度透传）→ 不误报、不封顶。"""
    monkeypatch.setattr(
        D, "_event_position_adj",
        lambda *a, **k: {"adj": 2, "long_count": 20, "as_of": _iso(1)})
    snap = D.build_snapshot(
        date="2026-09-04",
        indicators={"date": _iso(1)},
        temp=85.0,
        forecast={"score": 0.4, "bias": "偏多", "confidence": 0.7},
        promo={"overall": 65},
        ladder_as_of=_iso(1),
        market_temp_as_of=_iso(1),
    )
    assert snap["data_freshness"]["status"] == "ok"
    assert "封顶" not in " ".join(snap["position"]["reasons"])


def test_snapshot_legacy_call_excludes_unpassed_sources(monkeypatch):
    """不传 ladder/market_temp as_of（旧调用约定）→ 守卫只覆盖牧羊人+事件，行为向后兼容。"""
    monkeypatch.setattr(
        D, "_event_position_adj",
        lambda *a, **k: {"adj": 2, "long_count": 20, "as_of": _iso(1)})
    snap = D.build_snapshot(
        date="2026-09-04",
        indicators={"date": _iso(1)},
        temp=85.0,
        forecast={"score": 0.4, "bias": "偏多", "confidence": 0.7},
        promo={"overall": 65},
    )
    _srcs = snap["data_freshness"]["sources"]
    assert "连板晋级率" not in _srcs
    assert "市场温度缓存" not in _srcs
    assert snap["data_freshness"]["status"] == "ok"


# ──────────────────────────────────────────────
# 事件因子 efficacy 护栏（自找缺口 S15）：无统计优势则不施加催化
# ──────────────────────────────────────────────
def _fake_by_event(on_acc, off_acc, n_on=25, n_off=25):
    """构造 by_event 的受控返回：事件开/事件关 命中率与样本数。"""
    def _fn(min_samples=0):
        return [
            {"group": "事件开", "n": n_on, "n_call": n_on,
             "hits": int(n_on * on_acc / 100), "accuracy": on_acc},
            {"group": "事件关", "n": n_off, "n_call": n_off,
             "hits": int(n_off * off_acc / 100), "accuracy": off_acc},
        ]
    return _fn


def _patch_event_signal(monkeypatch):
    """让 _compute_event_adj 拿到真实多头池（不打 11MB 文件）。"""
    class _FakeLoader:
        def __init__(self, *a, **k):
            pass

        def latest_date(self, model):
            return "2026-08-14"
    monkeypatch.setattr(P1, "P1SignalLoader", _FakeLoader)
    monkeypatch.setattr(EF, "event_driven_long_list",
                        lambda top_n=50, model="ev", loader=None:
                        [{"symbol": f"s{i}"} for i in range(20)])


def test_event_adj_zeroed_when_no_edge(monkeypatch):
    """事件开命中率不优于事件关（无统计优势）→ event_adj 归零，不往仓位注噪声。"""
    monkeypatch.setattr(DT, "by_event", _fake_by_event(on_acc=45.0, off_acc=55.0))
    _patch_event_signal(monkeypatch)
    assert D._compute_event_adj() is None


def test_event_adj_applied_when_edge(monkeypatch):
    """事件开明显优于事件关（有统计优势）→ 正常施加催化。"""
    monkeypatch.setattr(DT, "by_event", _fake_by_event(on_acc=62.0, off_acc=48.0))
    _patch_event_signal(monkeypatch)
    out = D._compute_event_adj()
    assert out is not None
    assert out["adj"] == 2


def test_event_adj_applied_when_unknown(monkeypatch):
    """样本不足无法确认优势 → 维持现状（真实信号、待验证），不擅自归零。"""
    monkeypatch.setattr(DT, "by_event", _fake_by_event(on_acc=45.0, off_acc=55.0, n_on=5, n_off=5))
    _patch_event_signal(monkeypatch)
    out = D._compute_event_adj()
    assert out is not None  # 样本不足 → 不归零
    assert out["adj"] == 2


# ──────────────────────────────────────────────
# 事件因子 edge UI 展示（自找缺口 S16）：把 efficacy 诚实摊到 UI
# ──────────────────────────────────────────────
def _edge(known, edge, on=60.0, off=48.0, n_on=25, n_off=25):
    return {"known": known, "edge": edge, "on_acc": on, "off_acc": off,
            "diff": on - off, "n_on": n_on, "n_off": n_off}


def test_format_event_edge_no_edge_is_warn():
    out = D.format_event_edge(_edge(True, False), None)
    assert out["level"] == "warn"
    assert "无统计优势" in out["text"]


def test_format_event_edge_has_edge_applied_is_ok():
    out = D.format_event_edge(_edge(True, True), 2)
    assert out["level"] == "ok"
    assert "有统计优势" in out["text"]
    assert "+2pt" in out["text"]


def test_format_event_edge_has_edge_not_applied_is_info():
    out = D.format_event_edge(_edge(True, True), 0)
    assert out["level"] == "info"
    assert "多头池偏窄" in out["text"]


def test_format_event_edge_unknown_is_info():
    out = D.format_event_edge({"known": False, "edge": None}, 2)
    assert out["level"] == "info"
    assert "待验证" in out["text"]


def test_format_event_edge_none_returns_none():
    assert D.format_event_edge(None, 2) is None
