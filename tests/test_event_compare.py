"""
方案② 守卫：event_compare 模块
覆盖：池缺失降级 / 看多看空拆分 / 对照判定逻辑 / 表格生成 / 广度缺失降级
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from modules import event_compare as ec


def _pool(bull=2, bear=1, score_bull=90.0, score_bear=40.0):
    pool = []
    for i in range(bull):
        pool.append(dict(rank=i + 1, symbol=f"sh60000{i}", signal="看多", score=score_bull, source="P1-ev-top_long"))
    for i in range(bear):
        pool.append(dict(rank=bull + i + 1, symbol=f"sz0000{i}", signal="看空", score=score_bear, source="P1-ev-top_short"))
    return dict(available=True, date="2026-09-03", pool=pool, stale=False, live=False, note="", source="brief")


def _breadth(red_ratio=55.0, up=2000, down=1500, lu=40, ld=10):
    return dict(available=True, date="2026-09-11", red_ratio=red_ratio,
                up_count=up, down_count=down, limit_up=lu, limit_down=ld, note="")


# ── 池缺失 / 空池降级 ──
def test_pool_missing_degrades():
    res = ec.load_event_pool(path="E:/no_such_file_event_pool.json")
    assert res.get("available") in (False, None) or res.get("pool") == []
    # 即使池不可用，对照函数也不应抛异常
    cmp = ec.signal_breadth_compare(pool_result=res, breadth=_breadth())
    assert cmp["alignment_kind"] == "unknown"
    assert cmp["n"] == 0


def test_empty_pool():
    cmp = ec.signal_breadth_compare(pool_result=dict(available=True, pool=[]), breadth=_breadth())
    assert cmp["n"] == 0
    assert cmp["bull_pct"] is None


# ── 看多/看空拆分与占比 ──
def test_bull_bear_split():
    cmp = ec.signal_breadth_compare(pool_result=_pool(bull=2, bear=1), breadth=_breadth())
    assert cmp["bull"] == 2 and cmp["bear"] == 1
    assert abs(cmp["bull_pct"] - 200 / 3) < 1e-6
    assert abs(cmp["bull_score_avg"] - 90.0) < 1e-9
    assert abs(cmp["bear_score_avg"] - 40.0) < 1e-9


# ── 对照判定逻辑（四种语义）──
def test_alignment_momentum():
    cmp = ec.signal_breadth_compare(pool_result=_pool(bull=3, bear=0), breadth=_breadth(red_ratio=60.0))
    assert cmp["alignment_kind"] == "momentum"


def test_alignment_contrarian():
    cmp = ec.signal_breadth_compare(pool_result=_pool(bull=3, bear=0), breadth=_breadth(red_ratio=30.0))
    assert cmp["alignment_kind"] == "contrarian"


def test_alignment_diverge_hot():
    cmp = ec.signal_breadth_compare(pool_result=_pool(bull=0, bear=3), breadth=_breadth(red_ratio=60.0))
    assert cmp["alignment_kind"] == "diverge_hot"


def test_alignment_cautious():
    cmp = ec.signal_breadth_compare(pool_result=_pool(bull=0, bear=3), breadth=_breadth(red_ratio=30.0))
    assert cmp["alignment_kind"] == "cautious"


def test_alignment_unknown_when_breadth_missing():
    cmp = ec.signal_breadth_compare(pool_result=_pool(), breadth=dict(available=False, red_ratio=None))
    assert cmp["alignment_kind"] == "unknown"


# ── 表格生成按强度降序，且带市场红盘率上下文 ──
def test_build_compare_rows_sorted_and_context():
    pool = _pool(bull=1, bear=1)
    pool["pool"][0]["score"] = 30.0   # 看多但分低
    pool["pool"][1]["score"] = 95.0   # 看空但分高
    rows = ec.build_compare_rows(pool_result=pool, breadth=_breadth(red_ratio=42.0))
    assert len(rows) == 2
    assert rows[0]["score"] == 95.0  # 高分在前
    assert rows[1]["score"] == 30.0
    assert all(r["market_red_ratio"] == 42.0 for r in rows)


# ── 广度缺失降级不抛异常 ──
def test_breadth_missing_safe():
    b = ec.current_breadth.__wrapped__ if hasattr(ec.current_breadth, "__wrapped__") else None
    # current_breadth 在测试环境若取不到数据应 available=False 而非抛
    res = ec.current_breadth(days=1)
    assert isinstance(res, dict)
    assert "available" in res


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
