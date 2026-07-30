"""
回归测试：session._parse_alert_summary 的悬空引用缺陷。

原 `_cached_alert_summary` 在 API 返回非 200 时，`data` 从未绑定却被无条件引用，
抛 NameError 后被 broad except 静默吞掉（行为看似正确实则脆弱）。
抽离为纯函数 _parse_alert_summary 后，覆盖：正常 dict / data 非 dict / 非 200 /
信封非 ok / body 非 dict / body 为 None 各分支，确保绝不抛异常且行为确定。
"""
import sys

import pytest


def _load_session():
    # modules.session 在测试环境可安全导入（conftest 已把 streamlit 注入 sys.modules）。
    from modules import session  # noqa: WPS433
    return session


def test_parse_alert_summary_ok_dict():
    session = _load_session()
    body = {"status": "ok", "data": {"unread_count": 3, "items": [{"id": 1}]}}
    assert session._parse_alert_summary(200, body) == {
        "unread_count": 3,
        "items": [{"id": 1}],
    }


def test_parse_alert_summary_ok_non_dict_data():
    # data 是非 dict（如 list）→ 回退 {}，不抛
    session = _load_session()
    assert session._parse_alert_summary(200, {"status": "ok", "data": [1, 2]}) == {}


def test_parse_alert_summary_non_200_was_unbound_nameerror():
    # 关键回归：原实现此处 data 未绑定 → NameError 被吞。
    # 修复后必须安全返回 {}，且不再依赖 broad except 兜底。
    session = _load_session()
    body = {"status": "ok", "data": {"x": 1}}
    assert session._parse_alert_summary(500, body) == {}
    assert session._parse_alert_summary(401, body) == {}
    assert session._parse_alert_summary(0, body) == {}


def test_parse_alert_summary_envelope_not_ok():
    session = _load_session()
    assert session._parse_alert_summary(200, {"status": "error", "data": {"x": 1}}) == {}


def test_parse_alert_summary_non_dict_body():
    session = _load_session()
    assert session._parse_alert_summary(200, "not a dict") == {}
    assert session._parse_alert_summary(200, 12345) == {}


def test_parse_alert_summary_none_body():
    session = _load_session()
    assert session._parse_alert_summary(200, None) == {}
    assert session._parse_alert_summary(-1, None) == {}
