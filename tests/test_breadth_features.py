"""数据可用性闸门回归测试（锁定方案⑥–⑩ R1 修复）。

核心防回退断言：离线健康镜像中 connect_hl/zt_fail_ratio/zt_prev_ret 近乎全 NaN、
connect_2b/fc_ratio/touch_down 等字段缺失（被填 0），绝不能当作真实数据进入任何新页计算。
"""
import pandas as pd

from modules import breadth_features as bf
from modules import market_regime as mr
from modules import lead_lag_matrix as ll
from modules import similar_day_cluster as sdc
from modules import inflection_scanner as ins


def test_usable_dims_drops_sparse_and_missing():
    df = mr.load_breadth_history()
    # 默认候选 = REAL_FEATURES，应全部保留
    usable, dropped = bf.usable_dims(df)
    for c in ["up_count", "down_count", "flat_count", "limit_up", "limit_down", "red_ratio"]:
        assert c in usable, f"{c} 应被保留为可用维度"
    # 把离线缺真值维度也放进候选集 → 必须被剔除（关键防回退）
    cand = list(bf.REAL_FEATURES) + ["connect_2b", "fc_ratio", "touch_down",
                                     "median_chg", "connect_hl", "zt_fail_ratio", "zt_prev_ret"]
    usable2, dropped2 = bf.usable_dims(df, candidate=cand)
    assert set(usable2) == set(bf.REAL_FEATURES), "可用维度应恰好是 6 个真实字段"
    for bad in ["connect_2b", "fc_ratio", "touch_down", "median_chg",
                "connect_hl", "zt_fail_ratio", "zt_prev_ret"]:
        assert bad in dropped2, f"{bad} 应被剔除（离线缺真值）"
    # 离线缺真值维度绝不应进入可用集
    assert not (set(usable2) & set(bf.OFFLINE_MISSING.keys()))


def test_availability_report_classifies():
    df = mr.load_breadth_history()
    rep = bf.availability_report(df)
    assert rep["red_ratio"]["status"] == "available"
    assert rep["connect_2b"]["status"] == "missing"
    assert rep["connect_hl"]["status"] in ("sparse", "missing")


def test_lead_lag_only_real_features():
    res = ll.lead_lag_matrix()
    assert res["available"] is True
    assert set(res["dims"]) <= set(bf.REAL_FEATURES)
    assert "connect_2b" not in res["dims"]
    assert "connect_hl" not in res["dims"]


def test_similar_day_only_real_features():
    res = sdc.similar_day_cluster()
    assert res["available"] is True
    assert set(res["dims"]) <= set(bf.REAL_FEATURES)
    assert "touch_down" not in res["dims"]


def test_inflection_only_real_features():
    res = ins.list_events()
    assert res["available"] is True
    assert set(res["dims"]) <= set(bf.REAL_FEATURES)
    # 离线缺真值维度绝不应进入扫描维度
    assert not any(b in res["dims"] for b in
                   ["connect_2b", "connect_hl", "fc_ratio", "touch_down", "zt_fail_ratio"])


def test_phase_no_silent_neutral_on_empty():
    # 构造一行全空的最新记录 → 应诚实标注「数据不足」而非误判「中性」
    empty = pd.DataFrame([{"date": "2026-09-11", "up_count": None, "down_count": None,
                           "flat_count": None, "limit_up": None, "limit_down": None,
                           "red_ratio": None}])
    cur = __import__("modules.speculative_clock", fromlist=["current_phase"]).current_phase(df=empty)
    assert cur["phase"] == "数据不足"
