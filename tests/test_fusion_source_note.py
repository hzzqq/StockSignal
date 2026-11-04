# -*- coding: utf-8 -*-
"""tests/test_fusion_source_note.py — 事件融合来源旁注守卫（B 方向）。

锁死 fusion_source_note 的三态纯展示行为：
1. 命中：本地事件库命中 N 条 -> 文案含「命中 N 条（与 P1 事件因子加权融合）」；
2. 无关联：其他标的事件不串味 / 窗口外 -> 文案含「无关联事件」；
3. 取数异常：tracked_event_signal 抛错 -> 优雅降级「暂不可用」，绝不向上抛。

诚实红线：本文件任何用例不得依赖网络与真实 data/events.csv（monkeypatch 隔离）。
"""
from pathlib import Path

import pandas as pd
import pytest

from modules.event_factor import fusion_source_note


def _patch_db(monkeypatch, tmp_path, df=None, raw=None):
    """把事件主表路径指到 tmp 隔离文件（与 test_event_factor_tracked 同款装置）。"""
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


def test_note_shows_hit_count(monkeypatch, tmp_path):
    """命中：本地事件库命中 N 条 -> 文案含命中数与融合说明。"""
    df = pd.DataFrame({
        "date": [_recent(), _recent()],
        "ticker": ["601088", "601088"],
        "title": ["公司中标大额合同", "公司签署战略合作协议"],
        "type": ["大利好", "利好"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    note = fusion_source_note("601088")
    assert "命中 2 条" in note
    assert "与 P1 事件因子加权融合" in note


def test_note_shows_no_related_event(monkeypatch, tmp_path):
    """无关联：其他标的事件不串味 -> 文案含「无关联事件」。"""
    df = pd.DataFrame({
        "date": [_recent()],
        "ticker": ["600519"],
        "title": ["贵州茅台公告"],
        "type": ["大利好"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    note = fusion_source_note("601088")
    assert "无关联事件" in note
    assert "命中" not in note


def test_note_degrades_on_exception(monkeypatch, tmp_path):
    """取数异常：tracked_event_signal 抛错 -> 优雅降级「暂不可用」，不向上抛。"""
    def _boom(*a, **k):
        raise RuntimeError("simulated source failure")
    monkeypatch.setattr("modules.event_factor.tracked_event_signal", _boom)
    note = fusion_source_note("601088")
    assert "暂不可用" in note


def test_note_keywords_passthrough_no_crash(monkeypatch, tmp_path):
    """keywords 透传：非空关键词过滤后仍走正常三态，不抛错。"""
    df = pd.DataFrame({
        "date": [_recent(), _recent()],
        "ticker": ["601088", "601088"],
        "title": ["中标公告", "股东减持"],
        "type": ["大利好", "大利空"],
    })
    _patch_db(monkeypatch, tmp_path, df)
    note = fusion_source_note("601088", keywords=["中标"])
    # 仅「中标」命中 1 条 -> 命中 1 条
    assert "命中 1 条" in note


def test_note_empty_db_no_related_event(monkeypatch, tmp_path):
    """空主表：文件存在但无内容 -> 诚实「无关联事件」，不编造。"""
    _patch_db(monkeypatch, tmp_path, raw="date,ticker,title,type\n")
    note = fusion_source_note("601088")
    assert "无关联事件" in note
