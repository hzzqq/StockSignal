"""R22：fundflow 纯转换函数无网单测。

覆盖两个可离线单测的纯转换：
- _to_wan_yi：金额(元) → 亿(≥1e8, 2位)/万(≥1e4, 1位)/原值(0位)；
              非数字（字符串/None）→ "—"。
- _normalize_individual_df：akshare 个股资金流 df → 统一 dict
  （source/main_net/big_net/super_net/main_net_pct/latest_date）；
  含 None/空串 → None、备选列名回退、日期 Timestamp→"YYYY-MM-DD"、负数保持符号。
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from modules.fundflow import _to_wan_yi, _normalize_individual_df


# ---------- _to_wan_yi ----------

def test_to_wan_yi_yi():
    assert _to_wan_yi(123456789) == "1.23亿"


def test_to_wan_yi_wan():
    assert _to_wan_yi(12345) == "1.2万"


def test_to_wan_yi_small_original():
    assert _to_wan_yi(999) == "999"


def test_to_wan_yi_zero():
    assert _to_wan_yi(0) == "0"


def test_to_wan_yi_negative_yi():
    assert _to_wan_yi(-123456789) == "-1.23亿"


def test_to_wan_yi_negative_wan():
    assert _to_wan_yi(-12345) == "-1.2万"


def test_to_wan_yi_non_numeric_string():
    assert _to_wan_yi("abc") == "—"


def test_to_wan_yi_none():
    assert _to_wan_yi(None) == "—"


# ---------- _normalize_individual_df ----------

def test_normalize_full_row():
    df = pd.DataFrame({
        "日期": [pd.Timestamp("2024-01-01")],
        "主力净流入-净额": [123456789],
        "大单净流入-净额": [50000000],
        "超大单净流入-净额": [70000000],
        "主力净流入-净占比": [3.5],
    })
    res = _normalize_individual_df(df)
    assert res["source"] == "akshare"
    assert res["main_net"] == 123456789.0
    assert res["big_net"] == 50000000.0
    assert res["super_net"] == 70000000.0
    assert res["main_net_pct"] == 3.5
    assert res["latest_date"] == "2024-01-01"


def test_normalize_none_and_empty_become_none():
    df = pd.DataFrame({
        "日期": [pd.Timestamp("2024-02-01")],
        "主力净流入-净额": [None],
        "主力净流入-净占比": [""],
    })
    res = _normalize_individual_df(df)
    assert res["main_net"] is None
    assert res["main_net_pct"] is None
    assert res["big_net"] is None
    assert res["super_net"] is None
    assert res["latest_date"] == "2024-02-01"


def test_normalize_fallback_column_names():
    df = pd.DataFrame({
        "日期": [pd.Timestamp("2024-03-01")],
        "主力净流入": [1000000],  # 备选列名，无 "-净额" 后缀
    })
    res = _normalize_individual_df(df)
    assert res["main_net"] == 1000000.0
    assert res["big_net"] is None
    assert res["super_net"] is None


def test_normalize_date_as_string():
    df = pd.DataFrame({
        "日期": ["2024-04-01"],
        "主力净流入-净额": [2000000],
    })
    res = _normalize_individual_df(df)
    assert res["latest_date"] == "2024-04-01"


def test_normalize_negative_main_net():
    df = pd.DataFrame({"主力净流入-净额": [-50000000]})
    res = _normalize_individual_df(df)
    assert res["main_net"] == -50000000.0
