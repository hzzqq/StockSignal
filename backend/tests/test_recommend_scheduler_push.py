# -*- coding: utf-8 -*-  # noqa: UP009
"""backend/tests/test_recommend_scheduler_push.py — F3 推送新鲜度守卫。

_regression_: 微信推送摘要此前只读 ``data_staleness.stale`` 布尔，完全不消费
``assess_data_staleness()`` 已返回的 ``freshness`` 四值；5~7 天「数据偏旧、
谨慎参考」（warn）被整段吞掉，用户收不到任何提示。本文件锁死：

1. 有 freshness 时以权威字段为准（warn/stale 出警示，ok/unknown 不出）；
2. 无 freshness 时兼容旧落盘的 stale 布尔（不丢原行为，不在调度器自抄阈值）；
3. data_staleness 缺失绝不抛异常、绝不空打警示；
4. 顺带修复：push_text() 真实返回 {"sent",...} 无 "ok" 键，日志不再恒写「未成功」。

范式：sys.path 注入同 test_recommend_routes_gate.py；_maybe_push 为函数内延迟
import，monkeypatch 模块属性即可拦截，不起服务、不真发推送。
"""
from __future__ import annotations

import logging
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.recommend_scheduler import _maybe_push  # noqa: E402


def _make_rec(staleness: dict | None = None) -> dict:
    """最小推荐样本；staleness=None 表示完全不带 data_staleness 键。"""
    rec = {
        "date": "2026-11-27",
        "picks": [{"name": "贵州茅台", "code": "600519", "composite": 72}],
    }
    if staleness is not None:
        rec["data_staleness"] = staleness
    return rec


@pytest.fixture
def push_capture(monkeypatch):
    """开启推送开关，把 push_text 换成纯捕获假函数（绝不真发）。"""
    monkeypatch.setenv("STOCKSIGNAL_RECOMMEND_PUSH", "1")
    captured: list[str] = []

    def _fake_push_text(text, prefer="auto"):
        captured.append(text)
        return {"sent": True, "channel": "stub", "reason": "ok"}

    monkeypatch.setattr("modules.push_channel.push_text", _fake_push_text)
    return captured


def _push_once(captured: list[str], rec: dict) -> str:
    """调用一次 _maybe_push 并返回捕获的推送文本（断言恰好推送一次）。"""
    captured.clear()
    _maybe_push(rec)
    assert len(captured) == 1, f"期望恰好推送 1 次，实际 {len(captured)} 次"
    return captured[0]


# 1. 核心反证用例：warn（滞后 5 天、数据偏旧）必须出警示
def test_warn_freshness_pushes_note_with_warning(push_capture):
    note = "行情数据最新 2026-11-22，滞后 5 天（数据偏旧，谨慎参考）"
    text = _push_once(push_capture, _make_rec(
        {"freshness": "warn", "stale": False, "note": note}))
    assert note in text, f"warn 的 note 未进推送文本：{text}"
    assert "⚠️" in text, f"warn 缺警示符号：{text}"


# 2. stale 权威字段必须出警示（即使 stale 布尔缺失也要靠 freshness 判定）
def test_stale_freshness_pushes_note(push_capture):
    note = "行情数据最新 2026-11-19，滞后 8 天（≥8 天，荐股依据已过时/陈旧）"
    text = _push_once(push_capture, _make_rec({"freshness": "stale", "note": note}))
    assert note in text, f"stale 的 note 未进推送文本：{text}"
    assert "⚠️" in text


# 3. ok 不出警示、不带 note
def test_ok_freshness_no_warning(push_capture):
    note = "行情数据最新 2026-11-27（滞后 0 天，数据新鲜）"
    text = _push_once(push_capture, _make_rec(
        {"freshness": "ok", "stale": False, "note": note}))
    assert note not in text, f"ok 不该带 note：{text}"
    assert "⚠️" not in text, f"ok 不该出警示：{text}"


# 3b. unknown 也不出警示（权威字段优先，即使旧布尔为 True）
def test_unknown_freshness_no_warning(push_capture):
    note = "无任何行情日期可考（数据源全部不可用）"
    text = _push_once(push_capture, _make_rec(
        {"freshness": "unknown", "stale": True, "note": note}))
    assert note not in text, f"unknown 不该带 note：{text}"
    assert "⚠️" not in text, f"unknown 不该出警示：{text}"


# 4. 旧格式：无 freshness 但 stale=True → 保持原行为
def test_legacy_stale_bool_without_freshness_still_warns(push_capture):
    note = "旧落盘格式：行情数据滞后"
    text = _push_once(push_capture, _make_rec({"stale": True, "note": note}))
    assert note in text, f"旧格式 stale=True 应保留 note：{text}"
    assert "⚠️" in text


# 5. data_staleness 完全缺失：不抛异常、不空打警示
def test_missing_data_staleness_never_raises(push_capture):
    text = _push_once(push_capture, _make_rec())
    assert "⚠️" not in text, f"无 data_staleness 不该出警示：{text}"
    assert "每日荐股" in text  # 主流程仍照常推送摘要


# 6. freshness=warn 但 note 缺失 → 兜底文案，不空警示
def test_warn_without_note_uses_fallback(push_capture):
    text = _push_once(push_capture, _make_rec({"freshness": "warn"}))
    assert "行情数据滞后" in text, f"note 缺失时应有兜底文案：{text}"
    assert "⚠️" in text


# 7. 顺带修复：返回 {"sent": True} 时日志必须写「微信推送成功」
def test_sent_true_logs_success(push_capture, caplog):
    caplog.set_level(logging.INFO, logger="backend.recommend_scheduler")
    _push_once(push_capture, _make_rec({"freshness": "ok", "note": "数据新鲜"}))
    assert "微信推送成功" in caplog.text, (
        f"push_text 返回 sent=True 时日志应报成功：{caplog.text}")


# 8. 开关默认关：未开启或设 0 时假 push_text 零调用
@pytest.mark.parametrize("switch", ["0", None])
def test_push_switch_off_never_calls(monkeypatch, switch):
    if switch is None:
        monkeypatch.delenv("STOCKSIGNAL_RECOMMEND_PUSH", raising=False)
    else:
        monkeypatch.setenv("STOCKSIGNAL_RECOMMEND_PUSH", switch)
    called: list[str] = []

    def _fake_push_text(text, prefer="auto"):
        called.append(text)
        return {"sent": True, "channel": "stub", "reason": "ok"}

    monkeypatch.setattr("modules.push_channel.push_text", _fake_push_text)
    _maybe_push(_make_rec({"freshness": "warn", "note": "开关关不该推送"}))
    assert called == [], f"开关={switch!r} 时不应调用 push_text，实际 {called}"
