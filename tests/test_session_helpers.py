"""session 纯助手 / 安全辅助回归测试（无网依赖，mock st.session_state）。

覆盖：
- _parse_iso / _rel_time / _parse_ts（ISO 解析统一入口；tz-aware 与 naive 不再冲突）
- 新能力 mask_token（token 安全脱敏，避免日志泄露明文凭证）
- auth_headers / is_admin / is_authenticated（mock st.session_state）
"""
import datetime as _dt
import time
import types

import jwt
import pytest

import modules.session as S


@pytest.fixture
def fake_st(monkeypatch):
    """用一个普通命名空间替换 streamlit.st，使 session_state 可自由读写。"""
    ns = types.SimpleNamespace(session_state={})
    monkeypatch.setattr(S, "st", ns)
    return ns


# ── ISO 解析统一入口 ──────────────────────────────────────
def test_parse_iso_basic():
    dt = S._parse_iso("2026-07-25T10:00:00")
    assert isinstance(dt, _dt.datetime)
    assert dt.tzinfo is None  # 时区已丢弃，便于与 datetime.now() 比较


def test_parse_iso_with_z():
    dt = S._parse_iso("2026-07-25T10:00:00Z")
    assert dt == _dt.datetime(2026, 7, 25, 10, 0, 0)


def test_parse_iso_with_offset():
    # +08:00 / +00:00 被剥离，结果按朴素时间解释
    dt = S._parse_iso("2026-07-25T10:00:00+08:00")
    assert dt == _dt.datetime(2026, 7, 25, 10, 0, 0)


def test_parse_iso_invalid():
    assert S._parse_iso("") is None
    assert S._parse_iso(None) is None
    assert S._parse_iso("not-a-time") is None


def test_rel_time_recent():
    recent = (_dt.datetime.now() - _dt.timedelta(minutes=2)).isoformat()
    assert S._rel_time(recent) == "2分钟前"


def test_rel_time_empty():
    assert S._rel_time("") == ""
    assert S._rel_time(None) == ""


def test_rel_time_invalid_returns_truncated():
    out = S._rel_time("garbage-value")
    assert isinstance(out, str)


def test_parse_ts_delegates():
    assert S._parse_ts("2026-07-25T10:00:00") == _dt.datetime(2026, 7, 25, 10, 0, 0)
    assert S._parse_ts("") is None


# ── 新能力 mask_token（安全脱敏）────────────────────────
def test_mask_token_none():
    assert S.mask_token(None) == ""
    assert S.mask_token("") == ""


def test_mask_token_long():
    out = S.mask_token("abcdef123456")
    assert out == "abcd****3456"
    assert "*" in out
    assert "abcdef123456" not in out  # 完整凭证不泄露


def test_mask_token_short():
    assert S.mask_token("ab") == "****"
    assert S.mask_token("abcde") == "****"


# ── 鉴权辅助（mock st.session_state）────────────────────
def test_auth_headers_with_token(fake_st):
    fake_st.session_state[S.KEY_TOKEN] = "tok123"
    assert S.auth_headers() == {"Authorization": "Bearer tok123"}


def test_auth_headers_no_token(fake_st):
    assert S.auth_headers() == {}


def test_is_admin(fake_st):
    fake_st.session_state[S.KEY_USER] = {"role": "admin"}
    assert S.is_admin() is True
    fake_st.session_state[S.KEY_USER] = {"role": "user"}
    assert S.is_admin() is False
    fake_st.session_state[S.KEY_USER] = None
    assert S.is_admin() is False


def test_is_authenticated_valid(fake_st):
    token = jwt.encode({"exp": int(time.time()) + 3600}, "s", algorithm="HS256")
    fake_st.session_state[S.KEY_TOKEN] = token
    assert S.is_authenticated() is True


def test_is_authenticated_expired(fake_st):
    token = jwt.encode({"exp": int(time.time()) - 10}, "s", algorithm="HS256")
    fake_st.session_state[S.KEY_TOKEN] = token
    # 过期 → 清理登录态并返回 False（clear_auth 在 fake session 上可安全执行）
    assert S.is_authenticated() is False
    assert fake_st.session_state[S.KEY_TOKEN] is None
