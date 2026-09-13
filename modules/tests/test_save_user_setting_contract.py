"""Cycle 79 (SDD+TDD): `save_user_setting` 按账号持久化用户设置行为契约测试。

靶子: modules/session.py:410 — 把用户自定义设置按当前登录账号持久化到后端
settings JSON 并本地乐观更新。原测试套件对它有**零引用**(真零覆盖安全盲区)。

复用 fake_st 模式 mock st.session_state; 另 mock get_token/get_user/http_post 三个依赖,
使逻辑可纯函数验证(不依赖真实网络/streamlit runtime)。
"""
import types
from unittest.mock import MagicMock

import pytest

import modules.session as S


@pytest.fixture
def fake_st(monkeypatch):
    ns = types.SimpleNamespace(session_state={})
    monkeypatch.setattr(S, "st", ns)
    return ns


@pytest.fixture
def auth(monkeypatch):
    """默认: 已登录(有 token + user), 可捕获 http_post 调用。"""
    monkeypatch.setattr(S, "get_token", lambda: "tok123")
    monkeypatch.setattr(
        S, "get_user",
        lambda: {"username": "bob", "role": "user", "settings": {"theme_mode": "dark"}},
    )
    post = MagicMock()
    monkeypatch.setattr(S, "http_post", post)
    return post


# ── AC1: 未登录不 POST、不改 session_state ──────────────────
def test_ac1_no_token_no_post(fake_st, monkeypatch):
    monkeypatch.setattr(S, "get_token", lambda: None)
    post = MagicMock()
    monkeypatch.setattr(S, "http_post", post)
    S.save_user_setting("scan_pool", ["a", "b"])
    post.assert_not_called()
    assert fake_st.session_state == {}, "未登录不得误改 session_state"


# ── AC2: 已登录 + 成功 → 本地更新 + 正确 POST ───────────────
def test_ac2_updates_local_and_posts(fake_st, auth):
    S.save_user_setting("scan_pool", ["x", "y"])
    # 本地乐观更新
    assert fake_st.session_state[S.KEY_USER]["settings"]["scan_pool"] == ["x", "y"]
    # 保留其他字段
    assert fake_st.session_state[S.KEY_USER]["username"] == "bob"
    # http_post 调用一次, json 含合并后的完整 settings
    auth.assert_called_once()
    kwargs = auth.call_args.kwargs
    assert kwargs["json"] == {"settings": {"theme_mode": "dark", "scan_pool": ["x", "y"]}}
    assert kwargs["headers"]["Authorization"] == "Bearer tok123"


# ── AC3: http_post 抛异常 → 静默忽略, 本地仍更新 ───────────
def test_ac3_post_failure_silent(fake_st, monkeypatch):
    monkeypatch.setattr(S, "get_token", lambda: "tok")
    monkeypatch.setattr(S, "get_user", lambda: {"settings": {}})

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(S, "http_post", boom)
    S.save_user_setting("font_size", 16)  # 不得抛
    assert fake_st.session_state[S.KEY_USER]["settings"]["font_size"] == 16


# ── AC4: user 为 None → 从空 user 新建 settings ───────────
def test_ac4_user_none_creates_settings(fake_st, monkeypatch):
    monkeypatch.setattr(S, "get_token", lambda: "tok")
    monkeypatch.setattr(S, "get_user", lambda: None)
    post = MagicMock()
    monkeypatch.setattr(S, "http_post", post)
    S.save_user_setting("font_size", 16)
    assert fake_st.session_state[S.KEY_USER]["settings"]["font_size"] == 16
    assert post.call_args.kwargs["json"] == {"settings": {"font_size": 16}}


# ── AC5: 只改 settings[key], 保留其他用户字段 ──────────────
def test_ac5_preserves_other_user_fields(fake_st, auth):
    S.save_user_setting("font_size", 18)
    u = fake_st.session_state[S.KEY_USER]
    assert u["username"] == "bob"
    assert u["role"] == "user"
    assert u["settings"]["theme_mode"] == "dark"
    assert u["settings"]["font_size"] == 18
