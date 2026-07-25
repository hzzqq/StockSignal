"""modules/fundamental_helpers 新增 _roe_status + 指标去重回归测试（无网依赖）。

覆盖：
- _roe_status：各档位阈值 + 无数据/非法值 → "—"
- _extract_metric_series：重复报告期去重（修复重复索引导致 yoy/qoq 命中错期的隐性 bug）
"""
import math

import numpy as np
import pandas as pd

import modules.fundamental_helpers as F


def test_roe_status_tiers():
    assert F._roe_status(None) == "—"
    assert F._roe_status(float("nan")) == "—"
    assert F._roe_status("x") == "—"
    assert F._roe_status(-3.0) == "亏损"
    assert F._roe_status(3.0) == "偏弱"
    assert F._roe_status(7.0) == "一般"
    assert F._roe_status(12.0) == "良好"
    assert F._roe_status(20.0) == "优秀"


def test_extract_metric_series_dedup_index():
    df = pd.DataFrame({
        "报告期": ["2023-12-31", "2023-12-31", "2022-12-31"],
        "归母净利润": [100, 999, 80],
    })
    s = F._extract_metric_series(df, ["归母净利润"])
    assert s is not None
    # 重复报告期被去重，索引唯一
    assert s.index.is_unique
    # 保留最后一次出现的值（999）
    assert s.loc[pd.Timestamp("2023-12-31")] == 999
    assert s.loc[pd.Timestamp("2022-12-31")] == 80


def test_extract_metric_series_normal_no_dup():
    df = pd.DataFrame({
        "报告期": ["2023-12-31", "2022-12-31"],
        "净资产收益率": [15.2, 12.1],
    })
    s = F._extract_metric_series(df, ["净资产收益率"])
    assert s is not None
    assert s.index.is_unique
    assert math.isclose(s.loc[pd.Timestamp("2023-12-31")], 15.2)
