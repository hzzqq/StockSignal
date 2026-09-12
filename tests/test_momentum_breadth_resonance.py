"""
方案④ 守卫：momentum_breadth_resonance 模块
覆盖：矩阵形状/分档 / 当前格定位 / 共现强度 / empty df 兜底 / 分档边界
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest
from modules import momentum_breadth_resonance as mbr


def _df():
    rows = []
    # 构造：广度与动量正相关——热度越高动量越强
    for i in range(500):
        rr = 10 + (i % 100) * 0.9          # 10..~99
        mom = -2.0 + (i % 100) * 0.05      # -2..~3
        rows.append(dict(date=f"2020-{(i%12)+1:02d}-{(i%27)+1:02d}",
                         red_ratio=rr, zt_prev_ret=mom))
    return pd.DataFrame(rows)


def test_matrix_shape_and_totals():
    m = mbr.resonance_matrix(_df())
    assert m["available"] is True
    assert len(m["matrix"]) == 5 and all(len(r) == 5 for r in m["matrix"])
    assert len(m["totals_row"]) == 5 and len(m["totals_col"]) == 5
    assert sum(m["totals_row"]) == m["n_days"] == 500
    assert sum(m["totals_col"]) == 500


def test_matrix_empty_safe():
    m = mbr.resonance_matrix(pd.DataFrame())
    assert m["available"] is False
    assert m["n_days"] == 0
    assert sum(sum(r) for r in m["matrix"]) == 0


def test_current_cell():
    cur = mbr.current_cell(_df())
    assert cur["available"] is True
    assert cur["rr_band"] is not None and 0 <= cur["rr_band"] <= 4
    assert cur["mom_band"] is not None and 0 <= cur["mom_band"] <= 4
    assert cur["rr_label"] in mbr._RR_LABELS
    assert cur["mom_label"] in mbr._MOM_LABELS


def test_current_cell_missing_values():
    # current_cell 取「最新日期行」(sort_values("date").iloc[-1])，并非索引末行；
    # _df() 日期为乱序字符串，二者不一致。故在最新日期行上设 NaN 才是真语义。
    df = _df()
    s = df.sort_values("date")
    s.loc[s.index[-1], "red_ratio"] = np.nan
    s.loc[s.index[-1], "zt_prev_ret"] = np.nan
    cur = mbr.current_cell(s)
    assert cur["available"] is True
    assert cur["rr_band"] is None  # 最新日期行缺值 → 不定位
    assert cur["mom_band"] is None


def test_resonance_stats():
    m = mbr.resonance_matrix(_df())
    s = mbr.resonance_stats(m)
    assert s["available"] is True
    assert 0.0 <= s["co_hot"] <= 100.0
    assert 0.0 <= s["co_cold"] <= 100.0
    assert s["dominant_cell"] is not None
    assert len(s["dominant_cell"]) == 3


def test_resonance_stats_empty():
    s = mbr.resonance_stats(mbr.resonance_matrix(pd.DataFrame()))
    assert s["available"] is False


def test_band_functions_boundaries():
    # 红盘率边界
    assert mbr._rr_band(0) == 0
    assert mbr._rr_band(19.9) == 0
    assert mbr._rr_band(20) == 1
    assert mbr._rr_band(100) == 4
    assert mbr._rr_band(None) is None
    assert mbr._rr_band(float("nan")) is None
    # 动量边界
    assert mbr._mom_band(-5) == 0
    assert mbr._mom_band(-1) == 1
    assert mbr._mom_band(0) == 2
    assert mbr._mom_band(5) == 4
    assert mbr._mom_band(None) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
