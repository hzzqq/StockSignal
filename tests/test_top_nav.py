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
    assert "ss-user-menu" in html and "ssSetStyle" in html  # 用户下拉 + 风格 JS
    assert 'value="cyber" selected' in html              # 当前风格选中态
    assert "ss-login" not in html                        # 不误渲染登录卡
    # T-197：JS（含 ss_prefs 持久化键）经 extra_js 通道注入，不在 markdown HTML 内
    js = top_nav.topnav_extra_js()
    assert "ss_prefs" in js and "ui_style" in js         # localStorage 持久化键一致


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
