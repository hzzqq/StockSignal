"""Cycle 78 (SDD+TDD): `_apply_user_settings` 行为契约测试。

靶子: modules/session.py:373 — 按账号把后端用户偏好(theme_mode/font_size)应用到
当前会话 session_state。原测试套件对它有**零引用**(真零覆盖安全盲区)。

复用 test_session_helpers 的 fake_st 模式: 用 SimpleNamespace 替换 modules.session.st，
使 session_state 成为可自由读写的普通 dict(无需 streamlit runtime)。
"""
import types

import pytest

import modules.session as S


@pytest.fixture
def fake_st(monkeypatch):
    """用一个普通命名空间替换 streamlit.st，使 session_state 可自由读写。"""
    ns = types.SimpleNamespace(session_state={})
    monkeypatch.setattr(S, "st", ns)
    return ns


# ── AC1: user=None 安全返回 ────────────────────────────────
def test_ac1_user_none_noop(fake_st):
    S._apply_user_settings(None)
    assert fake_st.session_state == {}, "user=None 不得修改 session_state"


# ── AC2: settings 非 dict / 缺失 安全返回 ──────────────────
def test_ac2_settings_not_dict_noop(fake_st):
    for bad in ["dark", [], 123, None]:
        S._apply_user_settings({"settings": bad})
        assert fake_st.session_state == {}, f"settings={bad!r} 不应修改 session_state"
    # settings 键缺失
    S._apply_user_settings({})
    assert fake_st.session_state == {}


# ── AC3 / AC4: 合法 theme 应用 ─────────────────────────────
def test_ac3_theme_dark(fake_st):
    S._apply_user_settings({"settings": {"theme_mode": "dark"}})
    assert fake_st.session_state["theme_mode"] == "dark"


def test_ac4_theme_light(fake_st):
    S._apply_user_settings({"settings": {"theme_mode": "light"}})
    assert fake_st.session_state["theme_mode"] == "light"


# ── AC5: 非法 theme 拒绝（防污染/注入）────────────────────
def test_ac5_illegal_theme_rejected(fake_st):
    S._apply_user_settings({"settings": {"theme_mode": "neon"}})
    assert "theme_mode" not in fake_st.session_state, "非法 theme 不得污染 session_state"
    # 另一个越界值
    S._apply_user_settings({"settings": {"theme_mode": 123}})
    assert "theme_mode" not in fake_st.session_state


# ── AC6: 空 font_size 拒绝（防清空污染）────────────────────
def test_ac6_empty_font_rejected(fake_st):
    fake_st.session_state["font_size"] = 15
    S._apply_user_settings({"settings": {"font_size": ""}})
    assert fake_st.session_state["font_size"] == 15, "空 font_size 不得清空"
    S._apply_user_settings({"settings": {"font_size": None}})
    assert fake_st.session_state["font_size"] == 15, "None font_size 不得清空"


# ── AC7: 两者都应用 ────────────────────────────────────────
def test_ac7_both_applied(fake_st):
    S._apply_user_settings({"settings": {"theme_mode": "dark", "font_size": 18}})
    assert fake_st.session_state["theme_mode"] == "dark"
    assert fake_st.session_state["font_size"] == 18


# ── AC8: 只给 font 不动 theme 默认值 ──────────────────────
def test_ac8_only_font_does_not_touch_theme(fake_st):
    fake_st.session_state["theme_mode"] = "light"
    S._apply_user_settings({"settings": {"font_size": 20}})
    assert fake_st.session_state["theme_mode"] == "light", "只给 font 不应动 theme"
    assert fake_st.session_state["font_size"] == 20
