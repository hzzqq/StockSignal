"""
backend/tests/test_parse_last_seen_contract.py
==============================================
离线单测 backend.api.market_alert_routes._parse_last_seen
（self-driving Cycle 80, SDD+TDD；spec: .workbuddy/specs/parse_last_seen_contract.md）

纯函数，无需 Flask 上下文 / DB。锁定 AC1–AC9：
脏 settings 字段（非 JSON / 非 dict / 缺键 / 非法时间戳）一律返回 None，
绝不抛异常——一个坏字段不得打挂 GET /api/market-alerts。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from backend.api.market_alert_routes import _parse_last_seen  # noqa: E402


class _User:
    """最小 user 替身：仅提供 settings 属性。"""

    def __init__(self, settings):
        self.settings = settings


# ─────────────────────────── AC1: 缺失 / None / 空串 ───────────────────────────
def test_settings_none_returns_none():
    assert _parse_last_seen(_User(None)) is None


def test_settings_missing_attr_returns_none():
    class _NoSettings:
        pass

    assert _parse_last_seen(_NoSettings()) is None


def test_settings_empty_string_returns_none():
    assert _parse_last_seen(_User("")) is None


# ─────────────────────────── AC2: 非合法 JSON ───────────────────────────
def test_invalid_json_returns_none():
    assert _parse_last_seen(_User("not-json{")) is None


# ─────────────────────────── AC3: 合法 JSON 但非 dict ───────────────────────────
def test_json_list_returns_none():
    assert _parse_last_seen(_User("[1, 2, 3]")) is None


def test_json_string_returns_none():
    assert _parse_last_seen(_User('"hello"')) is None


def test_json_number_returns_none():
    assert _parse_last_seen(_User("5")) is None


# ─────────────────────────── AC4: dict 但缺键 ───────────────────────────
def test_missing_key_returns_none():
    assert _parse_last_seen(_User(json.dumps({"other": 1}))) is None


# ─────────────────────────── AC5: 有键但假值 ───────────────────────────
@pytest.mark.parametrize("falsy", ["", None, 0])
def test_falsy_timestamp_returns_none(falsy):
    assert _parse_last_seen(_User(json.dumps({"last_seen_market_alert": falsy}))) is None


# ─────────────────────────── AC6: 合法 ISO 带 Z ───────────────────────────
def test_valid_iso_with_z_suffix():
    got = _parse_last_seen(_User(json.dumps({"last_seen_market_alert": "2026-09-01T12:00:00Z"})))
    assert got == datetime(2026, 9, 1, 12, 0, 0)
    assert got.tzinfo is None  # Z 被剥离，tz-naive


# ─────────────────────────── AC7: 合法 ISO 不带 Z ───────────────────────────
def test_valid_iso_without_z_suffix():
    got = _parse_last_seen(_User(json.dumps({"last_seen_market_alert": "2026-09-01T12:00:00"})))
    assert got == datetime(2026, 9, 1, 12, 0, 0)


# ─────────────────────────── AC8: 非法时间戳 ───────────────────────────
def test_invalid_timestamp_returns_none():
    assert _parse_last_seen(_User(json.dumps({"last_seen_market_alert": "not-a-date"}))) is None


# ─────────────────────────── AC9: 健壮性红线——绝不抛异常 ───────────────────────────
@pytest.mark.parametrize("dirty", [
    None, "", "not-json{", "[1,2]", '"str"', "5", "{}",
    json.dumps({"last_seen_market_alert": "not-a-date"}),
    json.dumps({"last_seen_market_alert": {"nested": "obj"}}),
])
def test_never_raises_on_dirty_settings(dirty):
    """任意畸形 settings 都返回 None，绝不抛异常（不得打挂 /api/market-alerts）。"""
    assert _parse_last_seen(_User(dirty)) is None
