"""
tests/test_price_alert_current.py
==============================
回归：价格预警页 _current_price 对脏值行情字段稳健（不抛 ValueError）。

背景（真实脆弱点）：
- pages/47_价格预警.py:_current_price 原用 `if rt.get("current"): return float(rt["current"])`
  行情接口对缺失值常返回 "—" / None / 非数字字符串，float("—") 抛 ValueError 且无 try 包裹
  → 触发预警计算/检查的调用方崩溃。
- 修复：改用 to_float（失败返回 None，调用方已处理 None 分支），同时正确处理 0.0 真实价。

本测试通过 importlib 加载页面模块（streamlit 无运行时仅告警），mock 行情接口，
验证脏值不崩、数字/0.0 正确返回。若页面在当前环境无法导入则跳过（不视为失败）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "47_价格预警.py"


def _load_page():
    spec = importlib.util.spec_from_file_location("pg_price_alert_test", str(PAGE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def page_mod():
    try:
        return _load_page()
    except Exception as e:  # pragma: no cover - 环境相关
        pytest.skip(f"页面模块导入不可用: {e}")


class TestCurrentPriceRobust:
    def test_dash_current_returns_none_not_crash(self, page_mod):
        # 旧实现：float("—") 抛 ValueError；修复后返回 None
        with mock.patch.object(page_mod, "api_quote", return_value={"current": "—"}):
            with mock.patch.object(page_mod.fetcher, "get_realtime_quote", return_value={}):
                assert page_mod._current_price("600519") is None

    def test_numeric_current_returns_float(self, page_mod):
        with mock.patch.object(page_mod, "api_quote", return_value={"current": 12.34}):
            with mock.patch.object(page_mod.fetcher, "get_realtime_quote", return_value={}):
                assert page_mod._current_price("600519") == 12.34

    def test_zero_price_not_skipped(self, page_mod):
        # 0.0 是合法价格（停牌/特殊），应返回 0.0 而非因 falsy 被跳过
        with mock.patch.object(page_mod, "api_quote", return_value={"current": 0.0}):
            with mock.patch.object(page_mod.fetcher, "get_realtime_quote", return_value={}):
                assert page_mod._current_price("600519") == 0.0

    def test_fallback_to_fetcher_dash_returns_none(self, page_mod):
        # api_quote 无 current → 回退 fetcher，fetcher 返回 "abc" 脏值也应 None 而非崩
        with mock.patch.object(page_mod, "api_quote", return_value={}):
            with mock.patch.object(page_mod.fetcher, "get_realtime_quote", return_value={"current": "abc"}):
                assert page_mod._current_price("600519") is None

    def test_source_uses_to_float_not_bare_float(self):
        src = PAGE.read_text(encoding="utf-8")
        # 不再有裸 float(rt["current"]) / float(q["current"])
        assert 'float(rt["current"])' not in src
        assert 'float(q["current"])' not in src
        # 使用 to_float 稳健解析
        assert "to_float(rt.get(" in src
        assert "to_float(q.get(" in src
