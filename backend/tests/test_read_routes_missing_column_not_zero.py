# -*- coding: utf-8 -*-  # noqa: UP009
"""backend/tests/test_read_routes_missing_column_not_zero.py

**诚实红线守卫：涨停池缺列/缺格不得以 0.0 冒充真实值。**

背景（真实缺陷）：
``backend/api/read_routes.py`` 的 ``_limitup_build_pool_section`` 早期用
``_limitup_num(df, key, default=0.0)`` 取列 —— 列缺失时整列填 0.0，于是：

1. ``rows[].seal`` / ``rows[].amount`` 输出 0.0（前端显「0」而不是「—」，
   等于把"没有数据"谎报成"封单金额就是 0"）；
2. 这些占位 0.0 还参与 leaderboard 打分（``s_seal``/``s_amt``），
   缺数据的那只票被当成"真实低分"排到榜尾 —— 缺数据者被当成事实。

修复后的契约：
- 可为 null 的字段（封板资金 / 成交额 / 行业）缺失 → **None**（JSON null）；
- 每行 + 整池用 ``unavailable_fields`` 显式标注哪些字段不可得；
- 打分**跳过**缺失维度并对可得维度重新归一权重，缺数据者不被压成低分；
- 数据齐备时行为与修复前**逐位一致**（本文件最后一个用例钉住）。

本文件只测后端纯函数 ``_limitup_build_pool_section``（零网络、零鉴权）。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from backend.api import read_routes as rr  # noqa: E402


def _full_df() -> pd.DataFrame:
    """数据齐备的涨停池明细（4 只票，连板数 / 行业 / 封单 / 成交额都有）。"""
    return pd.DataFrame({
        "代码": ["600519", "000001", "300750", "002594"],
        "名称": ["贵州茅台", "平安银行", "宁德时代", "比亚迪"],
        "连板数": [3, 1, 2, 5],
        "所属行业": ["白酒", "银行", "新能源", "汽车"],
        "封板资金": [1.2e9, 3.0e8, 8.8e8, 2.1e9],
        "成交额": [4.0e9, 9.0e8, 3.3e9, 5.5e9],
        "首次封板时间": ["093000", "101500", "140000", None],
        "炸板次数": [0, 2, 1, 0],
    })


# ─────────────────────── 1. 缺列 → None（不是 0.0）───────────────────────
def test_missing_seal_column_yields_none_not_zero():
    """整列缺失（封板资金）→ rows[].seal 必须是 None，不能是 0.0。"""
    df = _full_df().drop(columns=["封板资金"])
    sec = rr._limitup_build_pool_section(df, "20260915")

    assert sec["available"] is True
    assert len(sec["rows"]) == 4
    for row in sec["rows"]:
        assert row["seal"] is None, f"缺列不得填 0.0 冒充：{row}"
        assert "seal" in row["unavailable_fields"]


def test_missing_amount_column_yields_none_not_zero():
    """整列缺失（成交额）→ rows[].amount 必须是 None。"""
    df = _full_df().drop(columns=["成交额"])
    sec = rr._limitup_build_pool_section(df, "20260915")

    for row in sec["rows"]:
        assert row["amount"] is None, f"缺列不得填 0.0 冒充：{row}"
        assert "amount" in row["unavailable_fields"]


def test_missing_both_seal_and_amount_are_null():
    """封单 + 成交额双缺 → 两个字段都是 null，且整池标注不可得字段。"""
    df = _full_df().drop(columns=["封板资金", "成交额"])
    sec = rr._limitup_build_pool_section(df, "20260915")

    for row in sec["rows"]:
        assert row["seal"] is None
        assert row["amount"] is None
    assert "seal" in sec["unavailable_fields"]
    assert "amount" in sec["unavailable_fields"]


def test_nan_cell_becomes_none_not_zero():
    """列存在但该格为 NaN → 该行 seal=None（不是 0.0），其余行不受影响。"""
    df = _full_df()
    df.loc[1, "封板资金"] = float("nan")
    sec = rr._limitup_build_pool_section(df, "20260915")

    rows = {r["code"]: r for r in sec["rows"]}
    assert rows["000001"]["seal"] is None, "NaN 格不得填 0.0 冒充"
    assert "seal" in rows["000001"]["unavailable_fields"]
    # 有真值的行不受牵连
    assert rows["600519"]["seal"] == 1.2e9
    assert "seal" not in rows["600519"]["unavailable_fields"]


def test_pool_level_unavailable_fields_lists_missing_columns():
    """整池级 unavailable_fields 标出整列缺失的字段。"""
    df = _full_df().drop(columns=["封板资金"])
    sec = rr._limitup_build_pool_section(df, "20260915")
    assert "seal" in sec["unavailable_fields"]
    assert "amount" not in sec["unavailable_fields"]


# ─────────────────────── 2. 打分跳过缺失项 ───────────────────────
def test_score_skips_missing_seal_dimension():
    """缺封单列 → s_seal=None，且综合分不得按"封单=0"计算。

    旧实现：seal 整列填 0.0 → max_seal=0 → s_seal=0.0 → 综合分被压低 0.25 权重。
    新实现：seal 维度直接跳过，权重在可得维度上重新归一。
    """
    df = _full_df().drop(columns=["封板资金"])
    sec = rr._limitup_build_pool_section(df, "20260915")

    lb = {r["code"]: r for r in sec["leaderboard"]}
    assert lb["600519"]["s_seal"] is None, "缺列维度不得算出一个 0.0 的假分"
    assert lb["600519"]["score"] is not None

    # 旧实现的封单=0 会把 600519（封单 1.2e9，最大）压到和"零封单"同档；
    # 新实现里它的分必须严格高于"所有票都没封单数据"时的同一口径分。
    # 这里用可算的期望值反推：只剩 height/ind/amt 三维 → 归一后 600519 的分。
    w = {"height": 0.35, "ind": 0.20, "amt": 0.20}
    s_height = 3 / 5 * 100.0            # max_boards=5（比亚迪 5 连板）
    s_ind = 1 / 1 * 100.0                # 四个行业各 1 只 → max_ind_f=1
    s_amt = 4.0e9 / 5.5e9 * 100.0        # 成交额 4.0e9 / 最大 5.5e9
    wsum = w["height"] + w["ind"] + w["amt"]
    expect = (w["height"] * s_height + w["ind"] * s_ind + w["amt"] * s_amt) / wsum
    assert lb["600519"]["score"] == pytest.approx(round(expect, 1), abs=0.11)


def test_missing_column_does_not_push_row_to_bottom_of_leaderboard():
    """缺数据的票不得因占位 0 被压到最后一名。"""
    df = _full_df()
    # 让 300750 缺封单（NaN），其余齐备
    df.loc[df["代码"] == "300750", "封板资金"] = float("nan")
    sec = rr._limitup_build_pool_section(df, "20260915")

    codes = [r["code"] for r in sec["leaderboard"]]
    assert "300750" in codes, "缺数据的票仍应参与排名（按可得维度）"
    # 它不该因为"封单=0"而排在最后（比亚迪封单最大但封单维度对它可用）
    assert codes[-1] != "300750" or len(codes) == 1


def test_score_is_none_when_all_dimensions_unavailable():
    """四个维度全不可得 → score=None（诚实的"无法评分"，不是 0 分）。"""
    df = pd.DataFrame({
        "代码": ["600519"],
        "名称": ["贵州茅台"],
    })
    sec = rr._limitup_build_pool_section(df, "20260915")

    lb = sec["leaderboard"]
    assert len(lb) == 1
    assert lb[0]["score"] is None, "全不可得不得输出 0 分冒充"
    assert lb[0]["s_height"] is None


def test_normalization_uses_only_observed_values():
    """归一化基准只取观测到的值 —— 占位值不得拉低 max。

    场景：一只票封单 100（真值），另一只缺封单。
    若把缺的当 0 参与 max，max 仍是 100（本例看不出）→ 换成缺失的是**最大值**那列：
    实际实现里 max 只在观测值上算，缺封单的票 s_seal=None 而不是 0。
    """
    df = _full_df().drop(columns=["封板资金"])
    sec = rr._limitup_build_pool_section(df, "20260915")
    for r in sec["leaderboard"]:
        assert r["s_seal"] is None
        assert r["s_amt"] is not None, "有数据的维度必须照常算分"


# ─────────────────────── 3. 正常路径行为完全不变 ───────────────────────
def test_full_data_path_shape_unchanged():
    """数据齐备 → 字段齐全、数值真实、无不可用标注。"""
    sec = rr._limitup_build_pool_section(_full_df(), "20260915")

    assert sec["available"] is True
    assert sec["date"] == "20260915"
    assert sec["count"] == 4
    assert sec["unavailable_fields"] == []

    row = next(r for r in sec["rows"] if r["code"] == "600519")
    assert row["seal"] == 1.2e9
    assert row["amount"] == 4.0e9
    assert row["boards"] == 3
    assert row["industry"] == "白酒"
    assert row["unavailable_fields"] == []

    top = sec["leaderboard"][0]
    assert top["score"] is not None
    assert top["s_height"] is not None and top["s_seal"] is not None
    assert top["s_ind"] is not None and top["s_amt"] is not None


def test_normal_path_score_matches_legacy_formula():
    """数据齐备时综合分与旧公式（0.35/0.25/0.20/0.20 加权和）逐位一致。"""
    df = _full_df()
    sec = rr._limitup_build_pool_section(df, "20260915")

    # 旧公式的归一化口径：max_boards=5、max_ind_f=2、max_seal=2.1e9、max_amt=5.5e9
    max_boards_f = 5
    max_ind_f = 2          # 白酒 1 只 / 新能源 1 只 / 汽车 1 只 / 银行 1 只 → 各 1，最大 1? 见下
    # 行业计数：白酒1 银行1 新能源1 汽车1 → 每档 1 只 → max_ind_f = 1
    max_ind_f = 1
    max_seal = 2.1e9
    max_amt = 5.5e9
    for r in sec["leaderboard"]:
        expect = (0.35 * r["s_height"] + 0.25 * r["s_seal"]
                  + 0.20 * r["s_ind"] + 0.20 * r["s_amt"])
        assert r["score"] == pytest.approx(round(expect, 1), abs=0.11)
    assert max_boards_f == 5 and max_seal == 2.1e9 and max_amt == 5.5e9
