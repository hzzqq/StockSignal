# -*- coding: utf-8 -*-
"""tests/test_stock_risk.py — H6 个股风险扫描测试。

全程离线：纯计算函数直接喂数据；取数函数用假的 ``akshare`` 模块注入，
**不触网**。重点覆盖「诚实红线」——取数失败必须是 ``unknown``，不能滑落成 ``low``。
"""
import sys
import types
from datetime import datetime, timedelta

import pandas as pd
import pytest

from modules import stock_risk as sr


# ─────────────────────────── 商誉 ───────────────────────────
def test_goodwill_high():
    r = sr.goodwill_risk({"goodwill": 40e8, "equity": 100e8, "report_date": "20260630"})
    assert r["level"] == sr.RISK_HIGH
    assert r["value"] == 40.0


def test_goodwill_medium_and_low():
    assert sr.goodwill_risk({"goodwill": 15e8, "equity": 100e8})["level"] == sr.RISK_MEDIUM
    assert sr.goodwill_risk({"goodwill": 2e8, "equity": 100e8})["level"] == sr.RISK_LOW


def test_goodwill_absent_is_low_not_unknown():
    """报表有净资产但商誉科目为空 = 未做并购 → 低风险（不能报未知）。"""
    r = sr.goodwill_risk({"goodwill": None, "equity": 50e8, "report_date": "20260630"})
    assert r["level"] == sr.RISK_LOW
    assert "未见商誉" in r["note"]


def test_goodwill_fetch_failure_is_unknown():
    """取数失败（bs=None）必须是未知，绝不高抬成低风险。"""
    r = sr.goodwill_risk(None)
    assert r["level"] == sr.RISK_UNKNOWN


def test_goodwill_bad_equity_is_unknown():
    assert sr.goodwill_risk({"goodwill": 1e8, "equity": 0})["level"] == sr.RISK_UNKNOWN


# ─────────────────────────── 质押 ───────────────────────────
def test_pledge_none_is_unknown_empty_is_low():
    assert sr.pledge_risk(None)["level"] == sr.RISK_UNKNOWN
    assert sr.pledge_risk([])["level"] == sr.RISK_LOW


def test_pledge_ignores_released():
    rows = [{"holder": "A", "ratio_total": 45.0, "status": "已解押"},
            {"holder": "B", "ratio_total": 8.0, "status": "未解押"}]
    r = sr.pledge_risk(rows)
    assert r["level"] == sr.RISK_LOW and r["value"] == 8.0


def test_pledge_high():
    r = sr.pledge_risk([{"holder": "A", "ratio_total": 33.0, "status": "未解押"}])
    assert r["level"] == sr.RISK_HIGH


# ─────────────────────────── 解禁 ───────────────────────────
def test_unlock_window_filtering():
    today = datetime(2026, 9, 17)
    q = [{"date": "2026-10-01", "pct_float": 25.0, "type": "定增"},
         {"date": "2027-06-01", "pct_float": 90.0, "type": "首发"}]
    r = sr.unlock_risk(q, today=today)
    assert r["level"] == sr.RISK_HIGH          # 窗口内 25% → 高
    assert r["value"] == 25.0                   # 不能用窗口外的 90%
    assert r["detail"][0]["距今天数"] == 14


def test_unlock_no_upcoming_is_low():
    today = datetime(2026, 9, 17)
    r = sr.unlock_risk([{"date": "2028-01-01", "pct_float": 50.0}], today=today)
    assert r["level"] == sr.RISK_LOW


def test_unlock_none_is_unknown():
    assert sr.unlock_risk(None)["level"] == sr.RISK_UNKNOWN


# ─────────────────────────── 减持 ───────────────────────────
def test_reduction_net_sell_high():
    today = datetime(2026, 9, 17)
    rows = [{"date": "2026-08-01", "change_pct_signed": -0.8, "change_amount": -5e7},
            {"date": "2026-08-20", "change_pct_signed": -0.5, "change_amount": -3e7}]
    r = sr.reduction_risk(rows, today=today)
    assert r["level"] == sr.RISK_HIGH
    assert r["value"] == pytest.approx(-1.3)


def test_reduction_net_buy_is_low():
    today = datetime(2026, 9, 17)
    r = sr.reduction_risk([{"date": "2026-08-01", "change_pct_signed": 0.6}], today=today)
    assert r["level"] == sr.RISK_LOW


def test_reduction_ignores_out_of_window():
    today = datetime(2026, 9, 17)
    r = sr.reduction_risk([{"date": "2024-01-01", "change_pct_signed": -9.0}], today=today)
    assert r["level"] == sr.RISK_LOW and r["value"] == 0.0


def test_reduction_none_is_unknown():
    assert sr.reduction_risk(None)["level"] == sr.RISK_UNKNOWN


# ─────────────────────────── 诉讼 / 处罚 ───────────────────────────
def test_litigation_high_keyword():
    r = sr.litigation_risk(["关于收到中国证监会立案调查通知书的公告", "2026年半年度报告"])
    assert r["level"] == sr.RISK_HIGH
    assert r["value"] == 1


def test_litigation_no_hit_is_low_but_notes():
    r = sr.litigation_risk(["2026年半年度报告", "关于董事会换届的公告"])
    assert r["level"] == sr.RISK_LOW
    assert "未见" in r["note"]


def test_litigation_none_is_unknown():
    assert sr.litigation_risk(None)["level"] == sr.RISK_UNKNOWN


# ─────────────────────────── ST ───────────────────────────
def test_st_by_name_and_by_flag():
    assert sr.st_risk("*ST海航")["level"] == sr.RISK_HIGH
    assert sr.st_risk("退市中新")["level"] == sr.RISK_HIGH
    assert sr.st_risk("贵州茅台")["level"] == sr.RISK_LOW
    # 市场级名单更权威：即便名字没有 ST 标识，名单说在就是高
    assert sr.st_risk("某股", is_st=True)["level"] == sr.RISK_HIGH
    assert sr.st_risk("某股", is_st=False)["level"] == sr.RISK_LOW


def test_st_no_name_is_unknown():
    assert sr.st_risk(None)["level"] == sr.RISK_UNKNOWN


# ─────────────────────────── 汇总 ───────────────────────────
def _comp(level):
    return {"level": level, "value": None, "note": "", "detail": []}


def test_build_report_takes_worst_and_counts():
    comps = {"goodwill": _comp(sr.RISK_HIGH), "pledge": _comp(sr.RISK_LOW),
             "unlock": _comp(sr.RISK_MEDIUM), "reduction": _comp(sr.RISK_LOW),
             "litigation": _comp(sr.RISK_LOW), "st": _comp(sr.RISK_LOW)}
    rep = sr.build_risk_report(comps)
    assert rep["overall_level"] == sr.RISK_HIGH
    assert (rep["n_high"], rep["n_medium"], rep["n_low"], rep["n_unknown"]) == (1, 1, 4, 0)
    assert rep["coverage_pct"] == 100.0 and rep["reliable"] is True
    assert rep["risk_score"] == 50  # 100 - 35 - 15


def test_build_report_all_unknown_stays_unknown():
    """零覆盖时必须报未知，绝不能给绿色结论。"""
    comps = {k: _comp(sr.RISK_UNKNOWN) for k, _, _ in sr.DIMENSIONS}
    rep = sr.build_risk_report(comps)
    assert rep["overall_level"] == sr.RISK_UNKNOWN
    assert rep["coverage_pct"] == 0.0 and rep["reliable"] is False


def test_build_report_low_coverage_not_reliable():
    comps = {k: _comp(sr.RISK_LOW) for k, _, _ in sr.DIMENSIONS}
    comps["goodwill"] = _comp(sr.RISK_UNKNOWN)
    comps["pledge"] = _comp(sr.RISK_UNKNOWN)
    comps["unlock"] = _comp(sr.RISK_UNKNOWN)
    rep = sr.build_risk_report(comps)
    assert rep["overall_level"] == sr.RISK_LOW
    assert rep["coverage_pct"] == 50.0 and rep["reliable"] is False


# ─────────────────────────── 取数归一化（假 akshare） ───────────────────────────
@pytest.fixture
def fake_ak(monkeypatch):
    """注入一个假 akshare 模块，覆盖本模块用到的接口。"""
    mod = types.ModuleType("akshare")

    mod.stock_zh_a_st_em = lambda: pd.DataFrame({"代码": ["000001", "600519"], "名称": ["*ST某", "贵州茅台"]})

    def _pledge(symbol):
        if symbol == "000002":
            raise RuntimeError("boom")
        if symbol == "000003":
            return pd.DataFrame()
        return pd.DataFrame({
            "股东名称": ["某控股"], "占总股本比例": ["12.345"], "状态": ["未解押"],
            "质押结束日期": ["2027-01-01"],
        })

    mod.stock_gpzy_individual_pledge_ratio_detail_em = _pledge

    def _queue(symbol):
        return pd.DataFrame({
            "解禁时间": ["2026-10-01"], "占流通市值比例": ["0.1523"], "限售股类型": ["定向增发"],
        })

    mod.stock_restricted_release_queue_em = _queue
    mod.stock_financial_report_sina = lambda stock, symbol: pd.DataFrame({
        "报告日": ["20260331", "20260630"], "商誉": [7e8, 8e8],
        "归属于母公司股东权益合计": [100e8, 110e8],
    })
    monkeypatch.setitem(sys.modules, "akshare", mod)

    # 清市场级缓存，避免跨测试污染
    sr._market_cache.clear()
    return mod


def test_fetch_st_set_and_lookup(fake_ak):
    s = sr.fetch_st_set()
    assert s == {"000001", "600519"}


def test_fetch_pledge_normalizes(fake_ak):
    rows = sr.fetch_pledge("000001")
    assert rows[0]["ratio_total"] == 12.345
    assert rows[0]["status"] == "未解押"
    # 失败 → None（未知），空表 → []（无记录）
    assert sr.fetch_pledge("000002") is None
    assert sr.fetch_pledge("000003") == []


def test_fetch_unlock_pct_scaled(fake_ak):
    q = sr.fetch_unlock_queue("000001")
    assert q[0]["pct_float"] == pytest.approx(15.23)  # 0.1523 → 15.23%


def test_fetch_balance_sheet_latest_row(fake_ak):
    bs = sr.fetch_balance_sheet("600519")
    assert bs["goodwill"] == 8e8          # 取最新报告期 20260630，不是 20260331
    assert bs["equity"] == 110e8
    assert bs["report_date"] == "20260630"


def test_scan_stock_assembles_report(fake_ak, monkeypatch):
    monkeypatch.setattr(sr, "fetch_announcement_titles", lambda code: ["关于收到警示函的公告"])
    monkeypatch.setattr(sr, "_hold_rows_for", lambda code: [])
    res = sr.scan_stock("600000", "浦发银行")   # 不在假 ST 名单里 → ST 低
    rep = res["report"]
    # 商誉 8/110=7.27% → 低；质押 12.345 → 低；解禁 15.23 → 中；诉讼 警示函 → 中；ST → 低
    assert rep["components"]["unlock"]["level"] == sr.RISK_MEDIUM
    assert rep["components"]["litigation"]["level"] == sr.RISK_MEDIUM
    assert rep["overall_level"] == sr.RISK_MEDIUM
    assert res["errors"] == []


def test_scan_stock_all_sources_down_stays_unknown(monkeypatch):
    """全部取数失败 → overall 必须是 unknown（不能因「没有坏消息」就报绿）。"""
    monkeypatch.setattr(sr, "fetch_st_set", lambda: None)
    monkeypatch.setattr(sr, "fetch_balance_sheet", lambda c: None)
    monkeypatch.setattr(sr, "fetch_pledge", lambda c: None)
    monkeypatch.setattr(sr, "fetch_unlock_queue", lambda c: None)
    monkeypatch.setattr(sr, "_hold_rows_for", lambda c: None)
    monkeypatch.setattr(sr, "fetch_announcement_titles", lambda c: None)
    res = sr.scan_stock("600000")
    assert res["report"]["overall_level"] == sr.RISK_UNKNOWN
    assert res["report"]["coverage_pct"] == 0.0
    assert res["report"]["reliable"] is False


# ─────────────────────────── 纯度红线 ───────────────────────────
def test_pure_functions_do_not_touch_network(monkeypatch):
    """纯计算函数在 akshare 不可用时也必须能跑（说明它们不触网）。"""
    monkeypatch.setitem(sys.modules, "akshare", None)
    assert sr.goodwill_risk({"goodwill": 5e7, "equity": 10e8})["level"] == sr.RISK_LOW
    assert sr.pledge_risk([])["level"] == sr.RISK_LOW
    assert sr.unlock_risk([])["level"] == sr.RISK_LOW
    assert sr.reduction_risk([])["level"] == sr.RISK_LOW
    assert sr.litigation_risk([])["level"] == sr.RISK_LOW
    assert sr.st_risk("浦发银行")["level"] == sr.RISK_LOW
