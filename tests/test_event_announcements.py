# -*- coding: utf-8 -*-
"""tests/test_event_announcements.py — 公告第三真实源适配器守卫。

锁四条：
1. 归一化：akshare 中文列（源码核实）→ 英文字段，行数/类型分布如实统计；
2. 诚实降级：源异常 → available=False + note，rows 恒空，绝不编造公告；
3. 空表 = 真数据（available=True, total=0），不与错误混淆；
4. 非法公告类型回落「重大事项」并留痕；缓存 key 按 (date, symbol) 隔离。
"""
import pandas as pd
import pytest

import modules.event_announcements as ea


class _FakeAk:
    """可编程 stub：按构造参数决定返回帧或抛错。"""

    def __init__(self, df=None, exc=None):
        self._df, self._exc = df, exc
        self.calls: list[tuple] = []

    def stock_notice_report(self, symbol, date):
        self.calls.append((symbol, date))
        if self._exc:
            raise self._exc
        return self._df


def test_normalize_columns_and_type_distribution(monkeypatch):
    df = pd.DataFrame({
        "代码": ["000001", "600519"],
        "名称": ["平安银行", "贵州茅台"],
        "公告标题": ["关于回购的公告", "重大合同中标"],
        "公告类型": ["融资公告", "重大事项"],
        "公告日期": ["2026-10-30", "2026-10-30"],
        "网址": ["http://a", "http://b"],
    })
    fake = _FakeAk(df=df)
    monkeypatch.setattr(ea, "_ak", lambda: fake)
    out = ea.fetch_notice_events("20261030", "全部")
    assert out["available"] is True and out["total"] == 2
    assert out["by_type"] == {"融资公告": 1, "重大事项": 1}
    assert out["rows"][0]["code"] == "000001" and out["rows"][1]["title"] == "重大合同中标"
    assert out["rows"][0]["name"] == "平安银行"
    assert fake.calls == [("全部", "20261030")]


def test_source_failure_degrades_honestly(monkeypatch):
    """不变量2：源异常 → available=False、rows 空、note 中文留痕（不编造）。"""
    fake = _FakeAk(exc=ConnectionError("eastmoney timeout"))
    monkeypatch.setattr(ea, "_ak", lambda: fake)
    out = ea.fetch_notice_events("20261030")
    assert out["available"] is False and out["rows"] == [] and out["total"] == 0
    assert "不可用" in out["note"]


def test_empty_frame_is_true_data_not_error(monkeypatch):
    """不变量3：空表（非交易日/当日无公告）= available=True, total=0。"""
    fake = _FakeAk(df=pd.DataFrame())
    monkeypatch.setattr(ea, "_ak", lambda: fake)
    out = ea.fetch_notice_events("20261101", "风险提示")
    assert out["available"] is True and out["total"] == 0 and out["by_type"] == {}


def test_illegal_symbol_falls_back(monkeypatch):
    fake = _FakeAk(df=pd.DataFrame())
    monkeypatch.setattr(ea, "_ak", lambda: fake)
    out = ea.fetch_notice_events("20261030", "不存在的类型xyz")
    assert out["symbol"] == "重大事项"
    assert fake.calls and fake.calls[0][0] == "重大事项"


def test_missing_optional_columns_tolerated(monkeypatch):
    """缺「网址/名称」等可选列 → 字段空串优雅降级，不 KeyError。

    用独立日期避免撞进程级 TTL 缓存（同 (date,symbol) key 会被前序测试缓存）。
    """
    df = pd.DataFrame({"代码": ["000001"], "公告标题": ["t"],
                       "公告类型": ["重大事项"], "公告日期": ["2026-10-30"]})
    fake = _FakeAk(df=df)
    monkeypatch.setattr(ea, "_ak", lambda: fake)
    out = ea.fetch_notice_events("20260102")
    assert out["rows"][0]["url"] == "" and out["rows"][0]["name"] == ""


def test_no_synthetic_guard_covers_adapter():
    """护栏一致性：event_announcements.py 必须在 no_synthetic 扫描名单内。"""
    import os
    from tests.test_event_factor_no_synthetic import EXTENDED_TARGETS
    assert any(p.endswith("event_announcements.py") for p in EXTENDED_TARGETS), (
        "新事件源模块必须纳入 no_synthetic AST 护栏"
    )
