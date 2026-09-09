"""
render_entry_cards 的「新窗口」方案回归测试。

背景：R12 时因「Streamlit st.page_link 不支持 target=_blank、裸 <a> 全量重载可能掉登录」而暂缓。
R13+ 落实：app 登录态存于 URL query_params（modules/session.py），新窗口链接只要把当前
query_params（token/user）一并带过去，新标签页加载即由 init_session_state() 自动恢复登录，
不掉登录。本测试锁定：
1. nav_mode="new_window" 渲染出 target="_blank" 的裸 <a>（真·新标签页）。
2. 该 <a> 的 href 携带当前 query_params（含 auth_token）→ 新窗口登录态不丢。
"""
from __future__ import annotations

import os
import tempfile
import textwrap

import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_PAGE_SRC = textwrap.dedent("""
    import streamlit as st
    from modules.widgets import render_entry_cards
    render_entry_cards([
        {"path": "pages/10_行情看板.py", "label": "行情看板", "icon": "📈", "desc": "大盘/板块/个股实时行情"},
    ], columns=1, nav_mode="new_window")
""")


def _write_tmp_page():
    fd, path = tempfile.mkstemp(suffix=".py", dir=_PROJECT_ROOT)
    os.write(fd, _PAGE_SRC.encode("utf-8"))
    os.close(fd)
    return path


def test_new_window_mode_renders_target_blank_with_query_params():
    path = _write_tmp_page()
    try:
        at = AppTest.from_file(path, default_timeout=60)
        # 模拟已登录：把 token/user 放进 query_params，验证新窗口链接会一并带走
        try:
            at.query_params["auth_token"] = "dummy.jwt.token"
            at.query_params["auth_user"] = "demo"
        except Exception:
            pass
        at.run()

        joined = " ".join(getattr(w, "value", "") for w in at.markdown)
        assert 'target="_blank"' in joined, "新窗口模式未渲染 target=_blank 裸链接"
        assert "page=pages" in joined, "新窗口链接未带 page= 目标页参数"
        # 关键：当前登录态（auth_token）必须出现在 href 中，否则新标签页会掉登录
        assert "auth_token" in joined, "新窗口链接未携带 auth_token，新标签页将掉登录"
    finally:
        os.remove(path)


def test_page_link_mode_adds_new_window_affordance():
    """page_link/button 模式下，每张卡片额外渲染「↗ 新窗口打开」加法式链接（与默认导航并存）。"""
    src = _PAGE_SRC.replace('nav_mode="new_window"', 'nav_mode="page_link"')
    fd, path = tempfile.mkstemp(suffix=".py", dir=_PROJECT_ROOT)
    os.write(fd, src.encode("utf-8"))
    os.close(fd)
    try:
        at = AppTest.from_file(path, default_timeout=60)
        at.run()
        joined = " ".join(getattr(w, "value", "") for w in at.markdown)
        assert 'target="_blank"' in joined, "page_link 模式未渲染『↗ 新窗口打开』加法式链接"
        assert "新窗口打开" in joined, "未出现『↗ 新窗口打开』文案"
    finally:
        os.remove(path)
