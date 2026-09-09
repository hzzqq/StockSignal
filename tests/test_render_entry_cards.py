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


# ── 45_持仓中心 试点：三张子模块卡整体走 new_window ──
_HUB_CARDS_SRC = textwrap.dedent("""
    import streamlit as st
    from modules.widgets import render_entry_cards
    render_entry_cards([
        {"path": "pages/46_自选股监控.py", "label": "⭐ 自选池", "icon": "⭐", "desc": "自选股实时行情 / 股票池管理"},
        {"path": "pages/40_仓位管理.py", "label": "💼 持仓", "icon": "💼", "desc": "持仓盈亏 / 导入导出"},
        {"path": "pages/41_组合收益.py", "label": "📈 收益归因", "icon": "📈", "desc": "净值曲线 / 基准对比 / 收益贡献"},
    ], columns=3, nav_mode="new_window")
""")


def test_hub_45_cards_use_new_window():
    """45_持仓中心 试点：三个子模块入口卡片整体走 new_window（target=_blank 且各带 page= 目标）。"""
    fd, path = tempfile.mkstemp(suffix=".py", dir=_PROJECT_ROOT)
    os.write(fd, _HUB_CARDS_SRC.encode("utf-8"))
    os.close(fd)
    try:
        at = AppTest.from_file(path, default_timeout=60)
        try:
            at.query_params["auth_token"] = "dummy.jwt.token"
            at.query_params["auth_user"] = "demo"
        except Exception:
            pass
        at.run()
        from urllib.parse import unquote
        joined = " ".join(getattr(w, "value", "") for w in at.markdown)
        joined_dec = unquote(joined)  # href 中文文件名被 URL 编码，解码后比对
        # 三张子模块卡均为新窗口链接
        assert joined.count('target="_blank"') >= 3, f"应有 ≥3 个新窗口链接，实际 {joined.count('target=\"_blank\"')}"
        for sub in ("46_自选股监控", "40_仓位管理", "41_组合收益"):
            assert f"page=pages/{sub}" in joined_dec, \
                f"子模块 {sub} 未出现在新窗口 href 中"
        # 登录态必须随 href 带走，否则新标签页掉登录
        assert "auth_token" in joined, "新窗口链接未携带 auth_token"
    finally:
        os.remove(path)

