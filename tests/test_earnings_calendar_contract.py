# -*- coding: utf-8 -*-
"""财报日历端点「列契约」守卫（2026-11-11 真缺陷回归）。

真缺陷：akshare.stock_report_disclosure 返回
  「股票代码 / 股票简称 / 首次预约 / 初次变更 / 二次变更 / 三次变更 / 实际披露」
而 modules/fundflow.get_disclosure_calendar 的 docstring 与前端表格按
  「报告期 / 披露时间 / 披露状态」
读取 —— 列名全部对不上，接真后端时披露时间/状态/报告期三列全显「—」，
端点 date 恒为 None；MSW 夹具因用旧列名而全绿，掩盖了漂移。

本守卫直接测纯函数 _normalize_disclosure_rows（零网络、无需 Flask app），
把「真实列名 → v2 契约列」以及「不编造」两条红线钉死。
"""
from __future__ import annotations

from backend.api.read_routes import _normalize_disclosure_rows


def test_real_akshare_columns_are_normalized_to_v2_contract():
    """真实 akshare 原始行 → 每行都带齐前端表格要读的 5 个契约列。"""
    rows = [
        {"股票代码": "000001", "股票简称": "平安银行",
         "首次预约": "2026-03-21T00:00:00.000", "初次变更": None,
         "二次变更": None, "三次变更": None,
         "实际披露": "2026-03-21T00:00:00.000"},
        {"股票代码": "000333", "股票简称": "美的集团",
         "首次预约": "2026-04-30T00:00:00.000", "实际披露": None},
    ]
    date = _normalize_disclosure_rows(rows, "2025年报")
    contract = ("股票代码", "股票简称", "报告期", "披露时间", "披露状态")
    assert all(all(k in r for k in contract) for r in rows), "契约列缺失会让表格全显「—」"
    assert rows[0]["披露时间"] == "2026-03-21"
    assert rows[0]["披露状态"] == "已披露"
    assert rows[0]["报告期"] == "2025年报"
    assert rows[0]["代码"] == "000001" and rows[0]["名称"] == "平安银行"
    # 仅有预约日期、无实际披露 → 派生「预约待披露」，不谎报已披露、也不编造日期
    assert rows[1]["披露时间"] == "2026-04-30"
    assert rows[1]["披露状态"] == "预约待披露"
    # date 只取「实际披露」最大值，未披露行不计入
    assert date == "2026-03-21"
    # 原始列必须保留（排障 / 后续扩展）
    assert "首次预约" in rows[0] and "实际披露" in rows[0]


def test_legacy_column_names_still_work():
    """旧版 akshare / 历史快照列名也要兼容，不能换版本就静默崩。"""
    rows = [{"股票代码": "600519", "股票简称": "贵州茅台",
             "预约披露日期": "2026-03-31T00:00:00.000", "披露日期": "2026-03-31T00:00:00.000"}]
    date = _normalize_disclosure_rows(rows, "2025年报")
    assert rows[0]["披露时间"] == "2026-03-31"
    assert rows[0]["披露状态"] == "预约待披露"  # 无「实际披露」列，不擅自判定已披露
    assert date is None  # 无实际披露事实 → 不编造数据日


def test_no_dates_means_no_fabrication():
    """取不到任何日期时如实返回 None/空值，绝不补零或编造。"""
    rows = [{"股票代码": "000001", "股票简称": "平安银行"}]
    date = _normalize_disclosure_rows(rows, "2025年报")
    assert date is None
    assert rows[0]["披露时间"] is None
    assert rows[0]["披露状态"] is None
    assert rows[0]["报告期"] == "2025年报"  # 请求期是事实，不是编造


def test_empty_rows_is_safe():
    """空表不抛异常、不产出数据日。"""
    assert _normalize_disclosure_rows([], "2025年报") is None
