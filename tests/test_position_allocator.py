# -*- coding: utf-8 -*-
"""T-326 方向B 仓位分配器测试。

覆盖：
- allocate 纯函数契约（比例分配 / cap waterfill / 评分缺失剔除 / unavailable 诚实语义 /
  等权明示降级 / Σ=市场仓位）；
- loader 薄层（快照 / 荐股 / 用户评分 / 自选池）诚实降级；
- build_allocation 三源编排；
- mutation 自验（exec 注入缺陷 → 证明测试断言可检出，防假绿）。

全部离线：快照/荐股走 tmp_path 注入，session 接口走 monkeypatch。
"""
import json
from pathlib import Path

import pytest

from modules import position_allocator as pa

SNAP = {"date": "2026-10-23", "temperature": 75.1,
        "position": {"pct": 40, "band": "中性", "reasons": ["测试快照"]}}

PICKS = [
    {"code": "600519", "name": "贵州茅台", "composite": 80.0},
    {"code": "000001", "name": "平安银行", "composite": 20.0},
]


def _mk_snapshot(tmp_path, snap=SNAP):
    (tmp_path / "daily_snapshot.json").write_text(
        json.dumps(snap, ensure_ascii=False), encoding="utf-8")


def _mk_recommendation(tmp_path, picks=PICKS, status="ok"):
    rec = {"status": status, "generated_at": "2026-10-23 17:00:00",
           "data_as_of": "2026-10-23", "picks": picks}
    (tmp_path / "daily_recommendation.json").write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def _by_code(result, code):
    return next(a for a in result["allocations"] if a["code"] == code)


# ─────────────────── allocate 纯函数 ───────────────────
class TestAllocate:
    def test_score_proportional_sum_is_market_pct(self):
        r = pa.allocate(30, [{"code": "A", "name": "甲", "score": 50},
                             {"code": "B", "name": "乙", "score": 30},
                             {"code": "C", "name": "丙", "score": 20}])
        assert r["status"] == "ok"
        assert _by_code(r, "A")["pct"] == 15.0
        assert _by_code(r, "B")["pct"] == 9.0
        assert _by_code(r, "C")["pct"] == 6.0
        assert _by_code(r, "A")["weight"] == 0.15
        assert r["meta"]["sum_pct"] == 30.0
        assert r["meta"]["target_pct"] == 30.0
        assert r["meta"]["mode"] == "score" and r["meta"]["degraded"] is False

    def test_cap_redistributes_residual(self):
        """超 cap 截断后剩余按权重重分：80/10/10、pct=30、cap=15 → 15/7.5/7.5。"""
        r = pa.allocate(30, [{"code": "A", "name": "甲", "score": 80},
                             {"code": "B", "name": "乙", "score": 10},
                             {"code": "C", "name": "丙", "score": 10}], cap_pct=15)
        assert _by_code(r, "A")["pct"] == 15.0
        assert _by_code(r, "B")["pct"] == 7.5
        assert _by_code(r, "C")["pct"] == 7.5
        assert r["meta"]["capped"] == ["A"]
        assert r["meta"]["sum_pct"] == 30.0 and r["meta"]["overflow_pct"] == 0

    def test_cap_overflow_honest_shortfall(self):
        """票太少 cap 封住总敞口：pct=100、2 票、cap=20 → 各 20、缺口 60 如实交代。"""
        r = pa.allocate(100, [{"code": "A", "name": "甲", "score": 50},
                              {"code": "B", "name": "乙", "score": 50}])
        assert [_by_code(r, c)["pct"] for c in "AB"] == [20.0, 20.0]
        assert r["meta"]["capped"] == ["A", "B"]
        assert r["meta"]["overflow_pct"] == 60.0
        assert r["meta"]["sum_pct"] == 40.0          # 少配 ≠ 凑满

    def test_missing_scores_excluded_not_fabricated(self):
        r = pa.allocate(40, [{"code": "A", "name": "甲", "score": 80},
                             {"code": "B", "name": "乙", "score": None},
                             {"code": "C", "name": "丙", "score": "abc"},
                             {"code": "D", "name": "丁", "score": -5}])
        assert r["status"] == "ok"
        assert {a["code"] for a in r["allocations"]} == {"A"}
        assert r["meta"]["n_excluded"] == 3
        assert all("不编造" in e["reason"] for e in r["excluded"])

    def test_all_scores_missing_unavailable(self):
        r = pa.allocate(40, [{"code": "A", "name": "甲", "score": None}])
        assert r["status"] == "unavailable" and "不编造" in r["reason"]

    def test_zero_total_score_unavailable(self):
        r = pa.allocate(40, [{"code": "A", "name": "甲", "score": 0},
                             {"code": "B", "name": "乙", "score": 0}])
        assert r["status"] == "unavailable" and "不编造" in r["reason"]

    def test_equal_mode_degraded_flagged(self):
        r = pa.allocate(30, [{"code": "A", "name": "甲", "score": None},
                             {"code": "B", "name": "乙", "score": None},
                             {"code": "C", "name": "丙", "score": None}], mode="equal")
        assert r["status"] == "ok"
        assert [a["pct"] for a in r["allocations"]] == [10.0, 10.0, 10.0]
        assert r["meta"]["mode"] == "equal_weight" and r["meta"]["degraded"] is True

    def test_equal_mode_also_capped(self):
        r = pa.allocate(100, [{"code": str(i), "name": str(i), "score": None}
                              for i in range(3)], mode="equal")
        assert [a["pct"] for a in r["allocations"]] == [20.0, 20.0, 20.0]
        assert r["meta"]["overflow_pct"] == 40.0

    @pytest.mark.parametrize("bad", [None, "abc", 0, -5, 150, float("inf")])
    def test_unavailable_market_pct(self, bad):
        r = pa.allocate(bad, [{"code": "A", "name": "甲", "score": 50}])
        assert r["status"] == "unavailable" and "不臆算" in r["reason"]

    def test_unavailable_bad_mode_or_pool_or_cap(self):
        good = [{"code": "A", "name": "甲", "score": 50}]
        assert pa.allocate(40, good, mode="foo")["status"] == "unavailable"
        assert pa.allocate(40, [])["status"] == "unavailable"
        assert pa.allocate(40, good, cap_pct=0)["status"] == "unavailable"
        assert pa.allocate(40, good, cap_pct=120)["status"] == "unavailable"

    def test_rounding_sum_within_tolerance(self):
        r = pa.allocate(33.333, [{"code": "A", "name": "甲", "score": 50},
                                 {"code": "B", "name": "乙", "score": 50},
                                 {"code": "C", "name": "丙", "score": 50}])
        assert abs(r["meta"]["sum_pct"] - r["meta"]["target_pct"]) <= 0.05 * 3


# ─────────────────── loader 薄层 ───────────────────
class TestLoaders:
    def test_load_market_pct_ok(self, tmp_path):
        _mk_snapshot(tmp_path)
        pct, meta = pa.load_market_pct(str(tmp_path))
        assert pct == 40.0
        assert meta["status"] == "ok" and meta["snapshot_date"] == "2026-10-23"
        assert meta["temperature"] == 75.1 and meta["band"] == "中性"

    def test_load_market_pct_missing_file_honest(self, tmp_path):
        pct, meta = pa.load_market_pct(str(tmp_path))
        assert pct is None and meta["status"] == "unavailable"
        assert "不实时臆算" in meta["reason"] and "daily_snapshot.json" in meta["reason"]

    def test_load_market_pct_corrupt_or_missing_pct(self, tmp_path):
        (tmp_path / "daily_snapshot.json").write_text("{oops", encoding="utf-8")
        assert pa.load_market_pct(str(tmp_path))[1]["status"] == "unavailable"
        (tmp_path / "daily_snapshot.json").write_text('{"date":"2026-10-23"}', encoding="utf-8")
        pct, meta = pa.load_market_pct(str(tmp_path))
        assert pct is None and "不臆算" in meta["reason"]

    def test_load_recommend_stocks_ok(self, tmp_path):
        _mk_recommendation(tmp_path)
        stocks, meta = pa.load_recommend_stocks(str(tmp_path))
        assert [s["code"] for s in stocks] == ["600519", "000001"]
        assert stocks[0]["score"] == 80.0 and meta["status"] == "ok"
        assert meta["generated_at"] == "2026-10-23 17:00:00"

    def test_load_recommend_stocks_unavailable(self, tmp_path):
        stocks, meta = pa.load_recommend_stocks(str(tmp_path))
        assert stocks == [] and meta["status"] == "unavailable"
        assert "荐股引擎" in meta["reason"]

    def test_load_user_scores_ok(self, monkeypatch):
        from modules import session as ss
        monkeypatch.setattr(ss, "api_get", lambda *a, **k: (
            200, {"data": [{"stock_code": "600519", "stock_name": "贵州茅台", "score": 90}]}))
        stocks, meta = pa.load_user_scores()
        assert stocks == [{"code": "600519", "name": "贵州茅台", "score": 90}]
        assert meta["status"] == "ok"

    def test_load_user_scores_failures_honest(self, monkeypatch):
        from modules import session as ss
        monkeypatch.setattr(ss, "api_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        stocks, meta = pa.load_user_scores()
        assert stocks == [] and "评分接口" in meta["reason"]
        monkeypatch.setattr(ss, "api_get", lambda *a, **k: (500, {}))
        stocks, meta = pa.load_user_scores()
        assert stocks == [] and "HTTP 500" in meta["reason"]
        monkeypatch.setattr(ss, "api_get", lambda *a, **k: (200, {"data": []}))
        stocks, meta = pa.load_user_scores()
        assert stocks == [] and "评分" in meta["reason"]

    def test_load_watchlist_stocks_ok_and_empty(self, monkeypatch):
        from modules import session as ss
        monkeypatch.setattr(ss, "get_watchlist",
                            lambda: [{"code": "A", "name": "甲"}, {"ticker": "B"}])
        stocks, meta = pa.load_watchlist_stocks()
        assert [s["code"] for s in stocks] == ["A", "B"]
        assert all(s["score"] is None for s in stocks) and meta["status"] == "ok"
        monkeypatch.setattr(ss, "get_watchlist", lambda: [])
        stocks, meta = pa.load_watchlist_stocks()
        assert stocks == [] and meta["status"] == "unavailable"


# ─────────────────── build_allocation 三源编排 ───────────────────
class TestBuildAllocation:
    def test_recommend_end_to_end(self, tmp_path):
        _mk_snapshot(tmp_path)
        _mk_recommendation(tmp_path)
        # cap=50：80/20 分、pct=40 → 32/8（不被默认 cap 干扰；默认 cap 行为由 allocate 单测覆盖）
        r = pa.build_allocation("recommend", data_dir=str(tmp_path), cap_pct=50)
        assert r["status"] == "ok"
        assert _by_code(r, "600519")["pct"] == 32.0      # 40 × 80/(80+20)
        assert _by_code(r, "000001")["pct"] == 8.0
        assert r["meta"]["market"]["snapshot_date"] == "2026-10-23"
        assert r["meta"]["source"]["label"] == "荐股引擎综合分"

    def test_no_snapshot_unavailable_not_improvised(self, tmp_path):
        _mk_recommendation(tmp_path)   # 评分源可得，也不许实时臆算仓位
        r = pa.build_allocation("recommend", data_dir=str(tmp_path))
        assert r["status"] == "unavailable" and "不实时臆算" in r["reason"]

    def test_source_unavailable_with_market_ok(self, tmp_path):
        _mk_snapshot(tmp_path)
        r = pa.build_allocation("recommend", data_dir=str(tmp_path))
        assert r["status"] == "unavailable"
        assert "评分源" in r["reason"] and "荐股引擎" in r["reason"]

    def test_equal_source_degraded_note(self, tmp_path, monkeypatch):
        _mk_snapshot(tmp_path)
        from modules import session as ss
        monkeypatch.setattr(ss, "get_watchlist",
                            lambda: [{"code": "A", "name": "甲"}, {"code": "B", "name": "乙"}])
        r = pa.build_allocation("equal", data_dir=str(tmp_path))
        assert r["status"] == "ok"
        assert r["meta"]["degraded"] is True
        assert "明示降级" in r["meta"]["degraded_note"]

    def test_unknown_source(self, tmp_path):
        assert pa.build_allocation("foo")["status"] == "unavailable"


# ─────────────────── mutation 自验（防假绿）───────────────────
_SRC = Path(pa.__file__).read_text(encoding="utf-8")


def _exec_mutated(old: str, new: str) -> dict:
    mutated = _SRC.replace(old, new)
    assert mutated != _SRC, f"mutation 种子失效：{old[:40]!r}"
    ns = {"__file__": str(Path(pa.__file__))}   # 模块顶层用到 __file__
    exec(compile(mutated, "<mutated-position-allocator>", "exec"), ns)
    return ns


def test_mutation_cap_removed_detected():
    """注入「永不封顶」缺陷 → 产出越 cap 的分配 → cap 断言可检出。"""
    ns = _exec_mutated(
        "over = [i for i in idx if share[i] > cap + _EPS]",
        "over = []",
    )
    r = ns["allocate"](30, [{"code": "A", "name": "甲", "score": 80},
                            {"code": "B", "name": "乙", "score": 10},
                            {"code": "C", "name": "丙", "score": 10}], cap_pct=15)
    a = _by_code(r, "A")["pct"]
    assert a > 15, f"mutation 未被检出——cap 守卫假绿（A={a}）"


def test_mutation_pct_validation_removed_detected():
    """注入「不校验仓位」缺陷 → 负仓位放行 → unavailable 断言可检出。"""
    ns = _exec_mutated(
        "if not math.isfinite(pct) or pct <= 0 or pct > 100:",
        "if False:",
    )
    r = ns["allocate"](-5, [{"code": "A", "name": "甲", "score": 50}])
    assert r["status"] == "ok", "mutation 未被检出——越界守卫假绿"


def test_mutation_equal_degraded_flag_removed_detected():
    """注入「等权不标降级」缺陷 → degraded=False → 降级断言可检出。"""
    ns = _exec_mutated('"degraded": mode == "equal",', '"degraded": False,')
    r = ns["allocate"](30, [{"code": "A", "name": "甲", "score": None}], mode="equal")
    assert r["meta"]["degraded"] is False, "mutation 未被检出——降级标注守卫假绿"
