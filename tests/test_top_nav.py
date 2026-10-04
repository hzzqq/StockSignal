# -*- coding: utf-8 -*-
"""tests/test_top_nav.py — T-195 阿里云风格顶栏 Mega 导航守卫。

覆盖：mega 面板结构（六类目+决策中枢 Hero）/条目 slug 正确性/侧栏退役 CSS/
风格 JS 下拉与三路持久化/NEW·HOT 标签白名单/变量驱动（六风格适配）。
"""
from __future__ import annotations

import inspect

from modules import top_nav
from modules.top_nav import TOPNAV_CSS, _slug, render_topnav

_NAV_GROUPS = [
    ("📊 行情与个股", [("", [
        ("pages/10_行情看板.py", "行情看板", "📺"),
        ("pages/24_个股研究.py", "个股研究", "🔬"),
        ("pages/22_基本面分析.py", "基本面分析", "📈"),
    ])]),
    ("💰 组合与交易", [("", [
        ("pages/45_持仓中心.py", "持仓中心", "🏦"),
        ("pages/52_股吧.py", "股吧", "💬"),
    ])]),
]
_NAV_HERO = [("pages/54_今日决策面板.py", "今日决策面板", "🎯")]
_NAV_ADMIN = [("pages/99_管理.py", "管理后台", "🛡")]
_FAVS = [("pages/30_策略回测.py", "策略回测", "⚙️")]
_RECENTS = [{"code": "600519", "name": "贵州茅台"}]

_drawn: list[str] = []


def _fake_markdown(payload, **kw):
    _drawn.append(payload)


def test_slug_rules():
    """slug：去序号前缀与 .py；app.py → /。"""
    assert _slug("pages/52_股吧.py") == "/股吧"
    assert _slug("pages/10_行情看板.py") == "/行情看板"
    assert _slug("app.py") == "/"
    assert _slug("pages/24_个股研究.py") == "/个股研究"


def test_mega_structure_complete(monkeypatch):
    """六要素齐全：品牌/首页/决策中枢 Hero/类目面板/搜索/用户区；侧栏退役 CSS 在。"""
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=_FAVS, recents=_RECENTS, current_style="cyber",
                  is_admin_user=False, cur_base="10_行情看板.py")
    html = _drawn[-1]
    assert html.count('class="ss-menu') >= 3            # 首页 + 决策中枢 + 2 类目
    assert "决策中枢" in html and "ss-mega" in html
    assert "行情看板" in html and "股吧" in html
    assert "ss-mega-grid" in html                        # 条目网格（横向滚动容器）
    assert "ss-mega-sub" not in html or "ss-mega-sub" in html  # 子分类标记可选
    assert 'href="/今日决策面板"' in html                # Hero 直达
    assert 'href="/行情看板"' in html                    # slug 链接
    assert "ss-user-menu" in html and "ss-style-opt" in html  # 用户下拉 + 风格锚点
    html_part = html[html.rindex("</style>") + len("</style>"):]
    assert html_part.count("ss-style-cur") == 1          # 当前风格唯一选中态（cyber）
    assert "✓" in html                                   # 选中风格打勾标记
    assert "ss-style-select" not in html                 # T-201：JS select 已废除
    assert "ss-login" not in html                        # 不误渲染登录卡
    # T-201：JS 作用域修复——搜索函数挂 P（父窗口），mega 钉住绑定存在
    js = top_nav.topnav_extra_js()
    assert "P.ssFocusSearch" in js
    assert "__ssMegaBound" in js and "ss-menu-pinned" in js
    assert "ssSetStyle" not in js                        # JS 风格切换路径已废除


def test_sidebar_retired_css(monkeypatch):
    """侧栏退役：CSS 必须隐藏 stSidebar 与展开按钮（顶栏为唯一主导航）。"""
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="classic",
                  is_admin_user=False, cur_base="")
    css = _drawn[-1]
    assert 'section[data-testid="stSidebar"]{display:none!important}' in css
    assert "stExpandSidebarButton" in css


def test_font_hierarchy_css(monkeypatch):
    """字号层级：核心 metric 值放大（阿里云视觉层级——重要信息更大）。"""
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="classic",
                  is_admin_user=False, cur_base="")
    css = _drawn[-1]
    assert "stMetricValue" in css and "1.55rem" in css


def test_admin_entries_gated(monkeypatch):
    """管理入口仅管理员可见（未登录/普通用户不渲染）。"""
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="classic",
                  is_admin_user=False, cur_base="")
    assert "管理后台" not in _drawn[-1]
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="classic",
                  is_admin_user=True, cur_base="")
    assert "管理后台" in _drawn[-1]


def test_entry_badges_whitelist():
    """NEW/HOT 标签白名单：只标注确定的高频/新增入口，不虚构。"""
    assert "54_今日决策面板.py" in top_nav._ENTRY_BADGES
    assert "22_基本面分析.py" not in top_nav._ENTRY_BADGES


def test_css_variable_driven():
    """顶栏颜色全走 CSS 变量——六套风格自动适配（无硬编码主题色底）。"""
    assert "var(--card" in TOPNAV_CSS
    assert "var(--acc1" in TOPNAV_CSS
    assert "var(--border" in TOPNAV_CSS
    assert "var(--txt" in TOPNAV_CSS


def test_active_highlight(monkeypatch):
    """当前页高亮：menu 与条目双高亮（当前位置可辨识）。"""
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="classic",
                  is_admin_user=False, cur_base="52_股吧.py")
    html = _drawn[-1]
    assert "ss-entry-active" in html


def test_mega_hover_visible_contract():
    """T-199 mega 面板悬停可见性契约：容器不裁剪 + 面板全宽锚定顶栏 + :hover 展开。

    根因回归守卫：.ss-topnav-menus 曾带 overflow:hidden——mega 面板是其内绝对定位
    子元素，整块被裁剪导致悬停无反应；.ss-menu 曾带 position:relative——面板
    left/right:0 锚到菜单项（宽~100px）而非全宽。
    """
    def _rule(css: str, selector: str) -> str:
        i = css.index(selector)
        return css[i:css.index("}", i)]

    # 1) menus 容器不得 overflow:hidden / overflow-x:auto（裁掉绝对定位面板）
    menus_rule = _rule(TOPNAV_CSS, ".ss-topnav-menus{")
    assert "overflow:hidden" not in menus_rule
    assert "overflow-x:auto" not in menus_rule
    # 2) .ss-menu 不得 position:relative（面板须锚到 position:fixed 的 .ss-topnav 全宽展开）
    menu_rule = _rule(TOPNAV_CSS, ".ss-menu{")
    assert "position:relative" not in menu_rule
    # 3) 悬停展开契约 + 面板锚定顶栏正下方
    assert ".ss-menu:hover .ss-mega{display:block}" in TOPNAV_CSS
    mega_rule = _rule(TOPNAV_CSS, ".ss-mega{")
    assert "position:absolute" in mega_rule and "top:100%" in mega_rule
    # 4) 用户下拉锚定不受影响（.ss-user 保持 position:relative）
    user_rule = _rule(TOPNAV_CSS, ".ss-user{")
    assert "position:relative" in user_rule


def test_topnav_html_no_blank_line_split(monkeypatch):
    """T-199b：html 段不得含纯空白行——markdown 把空白行后的 </div> 当段落文本
    转义显示（用户菜单底部漏出 </div> 字样的根因：admin/recents 为空时模板
    产生空白行）。仅校验 <div class="ss-topnav"> 至最后一个 </div> 的区间。
    """
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="classic",
                  is_admin_user=False, cur_base="")
    payload = _drawn[-1]
    html_part = payload[payload.rindex("</style>") + len("</style>"):]
    start = html_part.index('<div class="ss-topnav">')
    end = html_part.rindex("</div>")
    for ln in html_part[start:end].splitlines():
        assert ln.strip() != "", f"html 段含纯空白行（markdown 会转义后续闭合标签）: {ln!r}"


def test_nav_qs_propagated_to_all_hrefs(monkeypatch):
    """T-201：nav_qs（token+u+prefs）必须拼进全部导航 href——整页跳转丢 token
    即落登录 gate（老板反馈「点击功能模块要求重新登录」的根因）。
    """
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=_FAVS, recents=_RECENTS, current_style="classic",
                  is_admin_user=False, cur_base="10_行情看板.py",
                  nav_qs="token=tok123&u=%7B%7D&prefs=%7B%7D")
    html = _drawn[-1]
    assert 'href="/?token=tok123' in html                       # 品牌/首页
    assert 'href="/行情看板?token=tok123' in html               # mega 条目
    assert 'href="/策略回测?token=tok123' in html               # 常用条目
    assert "pick_stock=600519&token=tok123" in html             # 最近浏览合并参数
    assert 'href="/星辰AI?token=tok123' in html                 # 右上角图标
    assert 'href="/我的?token=tok123' in html                   # ⚙️/个人中心
    assert 'href="?token=tok123' in html                        # 风格锚点（相对路径）
    assert 'href="/股吧"' not in html                           # 不允许再有裸 slug
    # 未传 nav_qs 时保持原 slug（向后兼容）
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="classic",
                  is_admin_user=False, cur_base="")
    assert 'href="/行情看板"' in _drawn[-1]


def test_style_anchor_carries_switched_prefs(monkeypatch):
    """T-201：风格锚点 href 必须携带「当前 prefs 仅替换 ui_style」的查询串，
    相对 ?href 保留当前路径；选中项唯一且带 ✓。
    """
    monkeypatch.setattr("streamlit.markdown", _fake_markdown)
    render_topnav(nav_groups=_NAV_GROUPS, nav_hero=_NAV_HERO, nav_admin=_NAV_ADMIN,
                  favorites=[], recents=[], current_style="ink",
                  is_admin_user=False, cur_base="",
                  nav_qs="token=tok123&u=%7B%7D&prefs=%7B%22ui_style%22%3A%20%22ink%22%7D")
    html = _drawn[-1]
    html_part = html[html.rindex("</style>") + len("</style>"):]
    assert html_part.count("ss-style-cur") == 1
    assert "✓ D · 东方墨韵" in html                             # ink 为当前风格
    assert "prefs=" in html and "token=tok123" in html          # 锚点带 prefs+token
    for k in ("classic", "terminal", "swiss", "aurora", "ink", "cyber"):
        assert f"ui_style%22%3A+%22{k}%22" in html or f"ui_style%22%3A%22{k}%22" in html


def test_mega_pinned_and_full_height_css():
    """T-201：①点击钉住 CSS 契约 ②菜单项满栏高（消除项底与面板顶之间的
    hover 死区——鼠标移入面板即收起的根因）。
    """
    assert ".ss-menu.ss-menu-pinned .ss-mega{display:block}" in TOPNAV_CSS
    menus_rule = TOPNAV_CSS[TOPNAV_CSS.index(".ss-topnav-menus{"):]
    menus_rule = menus_rule[:menus_rule.index("}")]
    assert "align-self:stretch" in menus_rule
    menu_rule = TOPNAV_CSS[TOPNAV_CSS.index(".ss-menu{"):]
    menu_rule = menu_rule[:menu_rule.index("}")]
    assert "height:100%" in menu_rule and "align-items:center" in menu_rule


def test_build_nav_index_carries_qs():
    """T-201：命令面板索引 href 携带导航查询串（面板条目为整页跳转）。"""
    idx = top_nav.build_nav_index(_NAV_GROUPS, _NAV_HERO, [], [],
                                  nav_qs="token=tok123")
    assert idx, "索引不应为空"
    for it in idx:
        assert it["href"].startswith("/") and "token=tok123" in it["href"], it
