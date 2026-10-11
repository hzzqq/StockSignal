"""
tests/test_top_nav_active_crumb.py
==================================
T-264 顶栏当前位置指示守卫（用户截图：在「实盘交易」页时顶栏「持仓交易」类目无任何高亮，
用户不知道自己在哪个模块）。

契约：
1. _locate_current 纯函数：cur_base 命中六类目条目 → (类目名, 页名)；命中 hero → 决策中枢；
   未命中（我的/星辰AI 等）/空串 → (None, None)。
2. render_topnav 产物：当前页所属一级类目 div.ss-menu 必须带 ss-menu-active 且含
   ss-crumb「› 页名」；其他类目不得带；hero 页命中时决策中枢带高亮；cur_base=app.py
   仅首页高亮。
3. 面包屑页名必须 html.escape（XSS 契约对齐）。
4. TOPNAV_CSS 必须含 .ss-crumb 视觉契约。

mutation 验证：断开 render_topnav 内 _locate_current 接线（强制 (None,None)）→ 用例 2 变红。
"""
import html as _html

from modules import top_nav


GROUPS = [
    ("💰 持仓交易", [("", [
        ("pages/43_实盘交易.py", "实盘交易", "💰"),
        ("pages/45_持仓中心.py", "持仓中心", "🏦"),
    ])]),
    ("🌐 市场广度·温度", [("", [
        ("pages/20_牧羊人.py", "牧羊人", "🐑"),
    ])]),
]
HERO = [("pages/54_今日决策面板.py", "今日决策面板", "🎯")]


def test_locate_current_group_hit():
    assert top_nav._locate_current("43_实盘交易.py", GROUPS, HERO) == ("💰 持仓交易", "实盘交易")


def test_locate_current_hero_hit():
    assert top_nav._locate_current("54_今日决策面板.py", GROUPS, HERO) == ("🎯 决策中枢", "今日决策面板")


def test_locate_current_miss_and_empty():
    assert top_nav._locate_current("91_我的.py", GROUPS, HERO) == (None, None)
    assert top_nav._locate_current("", GROUPS, HERO) == (None, None)
    assert top_nav._locate_current(None, GROUPS, HERO) == (None, None)
    assert top_nav._locate_current("43_实盘交易.py", [], []) == (None, None)


def _render(cur_base: str, monkeypatch) -> str:
    """渲染 render_topnav 并捕获注入 HTML（patch streamlit.markdown；函数内 import 同模块对象）。"""
    captured = {}

    def _fake_md(payload, *a, **kw):
        if "ss-topnav" in payload:
            captured["html"] = payload
        return None

    import streamlit
    monkeypatch.setattr(streamlit, "markdown", _fake_md)
    top_nav.render_topnav(
        nav_groups=GROUPS, nav_hero=HERO, nav_admin=[],
        favorites=[], recents=[], current_style="classic",
        is_admin_user=False, cur_base=cur_base, nav_qs="")
    assert "html" in captured, "顶栏 HTML 未注入"
    return captured["html"]


def _menu_segment(html: str, keyword: str) -> str:
    """截取含 keyword 的 .ss-menu div 片段（到下一个 ss-menu 开头或结尾）。"""
    i = html.index(keyword)
    start = html.rindex('<div class="ss-menu', 0, i)
    nxt = html.find('<div class="ss-menu', i)
    end = html.find("</div></div></div>", start) + len("</div></div></div>")
    return html[start:max(end, nxt if nxt > start else end)]


def test_render_marks_active_group_with_crumb(monkeypatch):
    html = _render("43_实盘交易.py", monkeypatch)
    seg = _menu_segment(html, "💰 持仓交易")
    assert 'ss-menu has-mega ss-menu-active' in seg, "当前类目未高亮"
    assert 'ss-crumb' in seg and "› 实盘交易" in seg, "面包屑缺失/页名不符"
    # 其他类目不得误亮
    other = _menu_segment(html, "🌐 市场广度·温度")
    assert "ss-menu-active" not in other and "ss-crumb" not in other, "非当前类目被误高亮"


def test_render_marks_hero_group_with_crumb(monkeypatch):
    html = _render("54_今日决策面板.py", monkeypatch)
    seg = _menu_segment(html, "🎯 决策中枢")
    assert 'ss-menu has-mega ss-menu-active' in seg
    assert "› 今日决策面板" in seg


def test_render_home_only_home_active(monkeypatch):
    html = _render("app.py", monkeypatch)
    home_seg = html[html.index('<a class="ss-menu'):html.index('<div class="ss-menu')]
    assert "ss-menu-active" in home_seg
    assert html.count('class="ss-crumb"') == 0, "首页不应显示面包屑"


def test_render_unknown_page_no_highlight(monkeypatch):
    html = _render("91_我的.py", monkeypatch)
    assert 'class="ss-crumb"' not in html
    # 仅允许 0 个 has-mega 类目高亮（首页 <a> 也不亮）
    for kw in ("💰 持仓交易", "🌐 市场广度·温度", "🎯 决策中枢"):
        assert "ss-menu-active" not in _menu_segment(html, kw)


def test_crumb_html_escapes_xss():
    got = top_nav._crumb_html('<img src=x onerror=alert(1)>')
    assert "<img" not in got and "&lt;img" in got
    assert got == f'<i class="ss-crumb">› {_html.escape("<img src=x onerror=alert(1)>")}</i>'


def test_current_page_basename_ctx_attr(monkeypatch):
    """兜底分支：ctx.main_script_path 可得且 _active_page 缺失时返回其 basename。
    （1.58 实测 ctx.main_script_path 在 multipage 直开 pages 页时返回入口 app.py，
    故实现以 _active_page 优先、ctx 仅兜底——本用例清空 _active_page 单测 ctx 路径。）"""
    import streamlit
    from modules import widgets

    class _Ctx:
        main_script_path = "E:/proj/pages/43_实盘交易.py"
        session = None

    monkeypatch.setattr(
        "streamlit.runtime.scriptrunner.get_script_run_ctx", lambda suppress_warning=False: _Ctx())
    monkeypatch.setattr(streamlit, "session_state", {})
    assert widgets._current_page_basename() == "43_实盘交易.py"


def test_current_page_basename_session_fallback(monkeypatch):
    """权威源：st.session_state['_active_page']（render_standard_page/app.py 帧首写入）优先于 ctx。"""
    import streamlit
    from modules import widgets

    monkeypatch.setattr(
        "streamlit.runtime.scriptrunner.get_script_run_ctx", lambda suppress_warning=False: None)
    monkeypatch.setattr(streamlit, "session_state",
                        {"_active_page": "E:/proj/pages/43_实盘交易.py"})
    assert widgets._current_page_basename() == "43_实盘交易.py"

    monkeypatch.setattr(streamlit, "session_state", {})
    assert widgets._current_page_basename() == ""


def test_topnav_css_carries_crumb():
    assert ".ss-crumb" in top_nav.TOPNAV_CSS
    assert "font-style:normal" in top_nav.TOPNAV_CSS  # <i> 斜体矫正
