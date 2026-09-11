"""market_regime 引擎单元测试。

守卫要点：
* classify_state 五档分类正确且互斥；
* 转移矩阵每行概率和为 1（或全 0）；
* find_analogs 排除目标日及其邻居，且无前视泄漏（类比日不得晚于目标日）；
* regime_report 在真实 4771 天历史上可用，latest.date == 历史末日。
"""

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import market_regime as mr  # noqa: E402


def _row(rr, ld, lu=30):
    return {"red_ratio": rr, "limit_down": ld, "limit_up": lu}


def test_classify_state_five_buckets():
    assert mr.classify_state(_row(100, 0, 100)) == "普涨"
    assert mr.classify_state(_row(60, 5, 50)) == "结构牛"
    assert mr.classify_state(_row(50, 5, 30)) == "震荡"
    assert mr.classify_state(_row(10, 60, 5)) == "恐慌"
    assert mr.classify_state(_row(10, 200, 5)) == "暴跌"
    # 跌停爆量优先于红盘率（即便红盘率不极低）
    assert mr.classify_state(_row(40, 150, 10)) == "暴跌"


def test_transition_matrix_rows_sum_to_one():
    df = mr.load_breadth_history()
    mat = mr.build_transition_matrix(df)
    for a in mr.STATE_ORDER:
        s = sum(mat[a].values())
        # 末日无后继 → 全 0；否则严格归一
        assert s == 0.0 or abs(s - 1.0) < 1e-9


def test_find_analogs_excludes_target_and_no_lookahead():
    df = mr.load_breadth_history()
    # 取中段目标日，验证不会「看见未来」
    target_idx = len(df) // 2
    target_date = df["date"].iloc[target_idx]
    analogs = mr.find_analogs(df, target_idx, k=8, exclude_window=5)
    assert len(analogs) == 8
    for a in analogs:
        a_date = pd.to_datetime(a["date"])
        # 不得等于目标日
        assert a_date != target_date
        # 不得落在目标日 ±5 邻居内（无前视/平凡匹配）
        gap = abs((a_date - target_date).days)
        assert gap > 5
        # 不得晚于目标日（历史类比只看过去，杜绝前视泄漏）
        assert a_date <= target_date
        # 前瞻统计存在（至少 d5）
        assert "d5" in a["forward"]


def test_regime_report_integration():
    rep = mr.regime_report(k=8)
    assert rep["available"] is True
    assert rep["data"]["rows"] == 4771
    # latest 应为历史末日
    assert rep["latest"]["date"] == rep["data"]["end"]
    # 状态分布五档齐全
    assert set(rep["state_distribution"].keys()) == set(mr.STATE_ORDER)
    # 至少 1 个类比且带前瞻
    assert len(rep["analogs"]) >= 1
    assert "forward" in rep["analogs"][0]


def test_write_regime_report(tmp_path):
    out = tmp_path / "market_regime.json"
    rep = mr.write_regime_report(out_path=str(out), k=5)
    assert rep["available"] is True
    assert os.path.exists(out)
    import json
    with open(out, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["available"] is True
    assert len(loaded["analogs"]) == 5
