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

import textwrap

import streamlit as st
from streamlit.testing.v1 import AppTest

st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

_PAGE_SRC = textwrap.dedent("""
    import streamlit as st
    from modules.widgets import render_entry_cards
    render_entry_cards([
        {"path": "pages/10_行情看板.py", "label": "行情看板", "icon": "📈", "desc": "大盘/板块/个股实时行情"},
    ], columns=1, nav_mode="new_window")
""")


def _write_tmp_page(tmp_path, src: str) -> str:
    """把探针页面写进 pytest 的 tmp_path（不再写项目根目录）。

    2026-09-10 修：原名用 ``tempfile.mkstemp(dir=项目根)`` + ``finally: os.remove``，
    有两个问题 —— ① 往仓库根目录塞 ``tmp*.py`` 垃圾；② 更致命的是沙箱有「按会话
    累计删除数」的批量删除守卫（阈值 50），长会话跑到本文件时 ``os.remove`` 直接抛
    ``SystemExit(1)``，于是「清理失败」被记成用例失败：全量跑必红、单跑必绿。
    改用 tmp_path 后由 pytest 统一回收，既不污染仓库也不触发守卫。
    """
    path = tmp_path / "probe_entry_cards.py"
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    return str(path)


def test_new_window_mode_renders_target_blank_with_query_params(tmp_path):
    path = _write_tmp_page(tmp_path, _PAGE_SRC)
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


def test_page_link_mode_adds_new_window_affordance_when_opted_in(tmp_path):
    """page_link 模式显式 show_new_window=True 时，卡片额外渲染『↗ 新窗口打开』加法式链接。"""
    src = _PAGE_SRC.replace('nav_mode="new_window"', 'nav_mode="page_link", show_new_window=True')
    path = _write_tmp_page(tmp_path, src)
    at = AppTest.from_file(path, default_timeout=60)
    at.run()
    joined = " ".join(getattr(w, "value", "") for w in at.markdown)
    assert 'target="_blank"' in joined, "显式 show_new_window=True 未渲染『↗ 新窗口打开』加法式链接"
    assert "新窗口打开" in joined, "未出现『↗ 新窗口打开』文案"


def test_page_link_mode_no_new_window_by_default(tmp_path):
    """默认 show_new_window=False：page_link 模式不应出现新窗口链接（保持原排版、不弹新窗口）。"""
    src = _PAGE_SRC.replace('nav_mode="new_window"', 'nav_mode="page_link"')
    path = _write_tmp_page(tmp_path, src)
    at = AppTest.from_file(path, default_timeout=60)
    at.run()
    joined = " ".join(getattr(w, "value", "") for w in at.markdown)
    assert 'target="_blank"' not in joined, "默认不应出现新窗口链接（用户要求恢复原排版）"


# ── 45_持仓中心 子模块卡：回退后应为同标签页原生跳转（不弹新窗口）──
_HUB_CARDS_SRC = textwrap.dedent("""
    import streamlit as st
    from modules.widgets import render_entry_cards
    render_entry_cards([
        {"path": "pages/46_自选股监控.py", "label": "⭐ 自选池", "icon": "⭐", "desc": "自选股实时行情 / 股票池管理"},
        {"path": "pages/40_仓位管理.py", "label": "💼 持仓", "icon": "💼", "desc": "持仓盈亏 / 导入导出"},
        {"path": "pages/41_组合收益.py", "label": "📈 收益归因", "icon": "📈", "desc": "净值曲线 / 基准对比 / 收益贡献"},
    ], columns=3)
""")


def test_hub_45_cards_render_same_window(tmp_path):
    """45_持仓中心 子模块卡片应为同标签页原生跳转（不弹新窗口）。回归 R18 试点回退。"""
    path = _write_tmp_page(tmp_path, _HUB_CARDS_SRC)
    at = AppTest.from_file(path, default_timeout=60)
    at.run()
    joined = " ".join(getattr(w, "value", "") for w in at.markdown)
    # 回退后不应再有 target="_blank" 新窗口链接（保留旧窗口）
    assert 'target="_blank"' not in joined, "45 卡片不应再弹新窗口（应保留旧窗口）"
    # 页面干净加载、无未捕获异常（卡片正常渲染由 render_entry_cards 保证）
    assert not at.exception, f"45 卡片渲染抛异常: {[str(e) for e in at.exception]}"
