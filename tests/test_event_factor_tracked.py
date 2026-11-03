# -*- coding: utf-8 -*-
"""tests/test_event_factor_tracked.py — 第四真实源（本地事件主表）守卫。

锁死 tracked_event_signal 的五态行为与口径：
1. 命中：近窗口内关联事件聚合出分，source=tracked-events，tracked 元数据齐备；
2. 无匹配：其他标的的事件不串味，available=False；
3. 损坏 CSV：诚实降级 available=False，绝不编造；
4. T-288 五档聚合：大利好+大利空 净权归零 → 52 中性；
5. 语音入库形态（ticker 关联 + type=利好）参与聚合；
6. keywords 语义：None 不过滤 / 空列表不匹配 / 非空按标题正则匹配。
诚实红线：本文件任何用例不得依赖网络与真实 data/events.csv（monkeypatch 隔离）。
"""
from pathlib import Path

import pandas as pd
import pytest

from modules.event_factor import tracked_event_signal


def _patch_db(monkeypatch, tmp_path, df=None, raw=None):
    """把事件主表路径指到 tmp 隔离文件（惰性导入在调用时绑定，patch 生效）。"""
    p = tmp_path / "events.csv"
    if raw is not None:
        p.write_text(raw, encoding="utf-8")
    elif df is not None:
        df.to_csv(p, index=False)
    monkeypatch.setattr("modules.signal.events_db_path",
                        lambda *a, **k: str(p))
    return p


def _recent(days_ago: int = 1) -> str:
    return str((pd.Timestamp.now() - pd.Timedelta(days=days_ago)).date())


def test_hit_aggregates_and_annotates(monkeypatch, tmp_path):
    """命中：关联事件聚合出分 + tracked 元数据 + hard_logic 可分类。"""
    df = pd.DataFrame({
        "date": [_recent(), _recent()],
        "ticker": ["601088", "601088"],
        "title": ["公司中标大额合同", "公司签署战略合作协议"],
        "type": ["大利好", "利好"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r = tracked_event_signal("601088")
    assert r["available"] is True
    assert r["source"] == "tracked-events"
    assert r["score"] == pytest.approx(76.0)  # 52 + 8*(大利好2+利好1) = 76，未触 95 上限
    assert r["signal"] == "看多"
    assert r["rank"] == pytest.approx(0.76)
    assert r["tracked"]["n_events"] == 2
    assert r["tracked"]["window_days"] == 30
    assert any("中标" in t for t in r["tracked"]["titles"])
    assert r["hard_logic"].get("hard_logic") is not None or r["hard_logic"].get("status")


def test_no_match_other_ticker(monkeypatch, tmp_path):
    """无匹配：其他标的的事件不串味，诚实 unavailable。"""
    df = pd.DataFrame({
        "date": [_recent()],
        "ticker": ["600519"],
        "title": ["贵州茅台公告"],
        "type": ["大利好"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r = tracked_event_signal("601088")
    assert r["available"] is False
    assert "关联事件" in r["reason"]


def test_corrupted_csv_degrades(monkeypatch, tmp_path):
    """损坏 CSV：诚实降级，不抛异常不编造。"""
    _patch_db(monkeypatch, tmp_path, raw="date,ticker,title,t\n不是,有,效,数,据\n")
    r = tracked_event_signal("601088")
    assert r["available"] is False


def test_five_tier_neutral_balance(monkeypatch, tmp_path):
    """五档聚合：大利好(+2) + 大利空(-2) 净权归零 -> 52 中性。"""
    df = pd.DataFrame({
        "date": [_recent(), _recent()],
        "ticker": ["601088", "601088"],
        "title": ["业绩预增翻倍", "立案调查公告"],
        "type": ["大利好", "大利空"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r = tracked_event_signal("601088")
    assert r["available"] is True
    assert r["score"] == pytest.approx(52.0)
    assert r["signal"] == "中性"


def test_bearish_aggregation(monkeypatch, tmp_path):
    """利空聚合：大利空(-2) + 小利空(-1) -> 52-24=28 看空。"""
    df = pd.DataFrame({
        "date": [_recent(), _recent()],
        "ticker": ["601088", "601088"],
        "title": ["被立案调查", "股东减持"],
        "type": ["大利空", "小利空"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r = tracked_event_signal("601088")
    assert r["score"] == pytest.approx(28.0)
    assert r["signal"] == "看空"


def test_voice_imported_entry_participates(monkeypatch, tmp_path):
    """语音入库形态（save_voice_event_to_db 写入的 ticker+type=利好）参与聚合。"""
    df = pd.DataFrame({
        "date": [_recent()],
        "ticker": ["601088"],
        "title": ["语音转写：公司获得大额订单"],
        "type": ["利好"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r = tracked_event_signal("601088")
    assert r["available"] is True
    assert r["score"] == pytest.approx(60.0)  # 52 + 8*1
    assert r["signal"] == "看多"


def test_stale_events_out_of_window(monkeypatch, tmp_path):
    """窗口外旧事件不参与（lookback_days=30 语义）。"""
    df = pd.DataFrame({
        "date": [str((pd.Timestamp.now() - pd.Timedelta(days=60)).date())],
        "ticker": ["601088"],
        "title": ["很久以前的事件"],
        "type": ["大利好"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r = tracked_event_signal("601088")
    assert r["available"] is False
    assert "近 30 日" in r["reason"]


def test_keywords_semantics(monkeypatch, tmp_path):
    """keywords：None 不过滤 / 空列表显式不匹配 / 非空按标题过滤。"""
    df = pd.DataFrame({
        "date": [_recent(), _recent()],
        "ticker": ["601088", "601088"],
        "title": ["中标公告", "股东减持"],
        "type": ["大利好", "大利空"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r_none = tracked_event_signal("601088", keywords=None)
    assert r_none["available"] and r_none["tracked"]["n_events"] == 2
    r_empty = tracked_event_signal("601088", keywords=[])
    assert r_empty["available"] is False  # 空列表显式不匹配（与 event_score 一致）
    r_kw = tracked_event_signal("601088", keywords=["中标"])
    assert r_kw["available"] and r_kw["tracked"]["n_events"] == 1
    assert r_kw["score"] == pytest.approx(68.0)  # 52 + 8*2


def test_market_level_placeholder_ticker_applies(monkeypatch, tmp_path):
    """市场级事件（空/占位 ticker）对所有标的生效——修正 event_score 死分支口径。"""
    df = pd.DataFrame({
        "date": [_recent()],
        "ticker": [""],
        "title": ["央行宣布降准"],
        "type": ["大利好"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    r = tracked_event_signal("601088")
    assert r["available"] is True
    assert r["tracked"]["n_events"] == 1


def test_missing_file_degrades(monkeypatch, tmp_path):
    """主表文件不存在：诚实 unavailable。"""
    _patch_db(monkeypatch, tmp_path, df=None, raw=None)
    # 不写文件，路径指向不存在的 csv
    r = tracked_event_signal("601088")
    assert r["available"] is False
    assert "不存在" in r["reason"]
