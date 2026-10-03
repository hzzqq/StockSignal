# -*- coding: utf-8 -*-
"""
modules/top_nav.py — 阿里云风格顶部 Mega 导航（T-195，侧栏退役配套）
=====================================================================

定位：替代原左侧垂直侧边栏，成为全站唯一主导航。
参考：阿里云官网 mega 面板（一级类目悬停 → 全宽白面板：左侧类目描述 + 右侧
4 列条目网格横向滚动 + NEW/HOT 标签）+ 力扣顶栏密度。

设计铁律：
  · 纯视觉/导航，不改任何业务逻辑（additive-only）
  · 颜色全部走 CSS 变量（--acc1/--acc2/--card/--txt/--txt2/--border），六套风格自动适配
  · 页面跳转用 <a href="/{slug}">（Streamlit 页面 slug），整页刷新由
    auth_persist（localStorage token）+ prefs 管道（URL/localStorage/后端）
    双保险恢复登录态与界面风格——已有机制，零新增风险
  · 悬停展开纯 CSS（:hover），无 JS 依赖，可靠执行
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 精选标签（视觉设计元素）：仅标注确实高频/新增的入口，不虚构数据
_ENTRY_BADGES = {
    "54_今日决策面板.py": ("HOT", "ss-tag-hot"),
    "10_行情看板.py": ("HOT", "ss-tag-hot"),
    "30_策略回测.py": ("NEW", "ss-tag-new"),
    "52_股吧.py": ("NEW", "ss-tag-new"),
}

# 类目描述（mega 面板左侧 intro 文案，对应 _NAV_GROUPS 六类目）
_GROUP_INTROS = {
    "🏠 首页": "应用第一落点：全局看板与快速入口。",
    "🎯 决策中枢": "事件因子 + 市场情绪的决策闭环核心：仓位推导、归因、健康度一目了然。",
    "🌐 市场广度·温度": "自建 2007 年起全市场广度真值库：温度、情绪周期与历史回放。",
    "📊 行情与个股": "行情看板、个股研究与基本面深钻。",
    "💰 组合与交易": "持仓、模拟交易、实盘、条件单与价格预警。",
    "⚙️ 策略与工具": "策略回测、智能选股与量化工具链。",
}


def _slug(path: str) -> str:
    """pages/52_股吧.py → /股吧（Streamlit 1.58 页面 slug：去序号前缀与 .py）。"""
    name = path.replace("\\", "/").split("/")[-1]
    if name == "app.py":
        return "/"
    name = name[:-3] if name.endswith(".py") else name
    name = re.sub(r"^\d+_", "", name)  # 剥「数字_」序号前缀（52_股吧 → 股吧）
    return "/" + name


def _entry_html(path: str, label: str, icon: str, cur_base: str) -> str:
    """mega 面板单个条目（名称 + 图标 + NEW/HOT 标签）。"""
    base = path.replace("\\", "/").split("/")[-1]
    active = " ss-entry-active" if base == cur_base else ""
    badge = ""
    if base in _ENTRY_BADGES:
        txt, cls = _ENTRY_BADGES[base]
        badge = f'<i class="ss-tag {cls}">{txt}</i>'
    href = _slug(path)
    return (f'<a class="ss-entry{active}" href="{href}" title="{label}">'
            f'<b>{icon} {label}</b>{badge}</a>')


def render_topnav(nav_groups: list, nav_hero: list, nav_admin: list,
                  favorites: list, recents: list, current_style: str = "classic",
                  is_admin_user: bool = False, cur_base: str = "") -> None:
    """渲染阿里云风格顶部 Mega 导航 + 侧栏退役 CSS + 字号层级。

    :param nav_groups: widgets._NAV_GROUPS（[(类目名, [(子类, [(path,label,icon[,sub])])])]）
    :param nav_hero: 决策中枢 Hero 条目
    :param nav_admin: 管理员条目
    :param favorites: ⭐ 常用 Top5
    :param recents: 最近浏览股票 [{code,name}]
    :param current_style: 当前界面风格（供 JS 下拉选中态）
    :param is_admin_user: 是否管理员（显示管理入口）
    :param cur_base: 当前页 basename（高亮）
    """
    import streamlit as st

    # ── 组装类目菜单 ──
    menus = []
    # 首页（直链，无面板）
    home_active = ' ss-menu-active' if cur_base == "app.py" else ""
    menus.append(f'<a class="ss-menu ss-menu-link{home_active}" href="/">🏠 首页</a>')
    # 决策中枢（Hero 常驻第一面板）
    hero_entries = "".join(
        _entry_html(p, l, i, cur_base) + (
            '<i class="ss-tag ss-tag-hot">HOT</i>' if "54_" in p else "")
        for p, l, i in nav_hero)
    intro_hero = _GROUP_INTROS.get("🎯 决策中枢", "")
    menus.append(
        '<div class="ss-menu has-mega">🎯 决策中枢'
        '<div class="ss-mega"><div class="ss-mega-intro"><h4>决策中枢 ></h4>'
        f'<p>{intro_hero}</p></div>'
        f'<div class="ss-mega-grid">{hero_entries}'
        + "".join(_entry_html(p, l, i, cur_base) for p, l, i in favorites)
        + "</div></div></div>")
    # 六大类目
    for top_label, clusters in nav_groups:
        intro = _GROUP_INTROS.get(top_label, "")
        rows = []
        for sub, items in clusters:
            if sub:
                rows.append(f'<div class="ss-mega-sub">{sub}</div>')
            rows.append("".join(_entry_html(p, l, i, cur_base) for p, l, i in items))
        grid = "".join(rows)
        menus.append(
            f'<div class="ss-menu has-mega">{top_label}'
            f'<div class="ss-mega"><div class="ss-mega-intro"><h4>{top_label} &gt;</h4>'
            f'<p>{intro}</p></div>'
            f'<div class="ss-mega-grid">{grid}</div></div></div>')

    # 最近浏览（用户下拉内）
    recents_html = ""
    for r in (recents or [])[:5]:
        rc = r.get("code", "")
        rn = r.get("name", "")
        if rc:
            recents_html += (f'<a class="ss-user-item" href="/个股分析?pick_stock={rc}">'
                             f'🕘 {rn} {rc}</a>')
    if recents_html:
        recents_html = '<div class="ss-user-sec">🕘 最近浏览</div>' + recents_html

    # 风格下拉选项
    style_labels = {
        "classic": "经典星辰（默认）", "terminal": "A · 彭博终端风",
        "swiss": "B · 瑞士极简白", "aurora": "C · 极光玻璃 2.0",
        "ink": "D · 东方墨韵", "cyber": "E · 赛博朋克 2077",
    }
    opts = "".join(
        f'<option value="{k}"{" selected" if k == current_style else ""}>{v}</option>'
        for k, v in style_labels.items())

    admin_html = ""
    if is_admin_user:
        admin_html = '<div class="ss-user-sec">🛡 管理</div>' + "".join(
            f'<a class="ss-user-item" href="{_slug(p)}">{i} {l}</a>'
            for p, l, i in nav_admin)

    html = f"""
<div class="ss-topnav">
  <a class="ss-brand" href="/">📈 <b>StockSignal</b></a>
  <nav class="ss-topnav-menus">{''.join(menus)}</nav>
  <div class="ss-topnav-right">
    <div class="ss-search" onclick="ssFocusSearch()" title="搜索（⌘K / Ctrl+K）">
      🔍 搜索 <kbd>⌘K</kbd>
    </div>
    <a class="ss-ico" href="/星辰AI" title="星辰 AI">✦</a>
    <a class="ss-ico" href="/我的" title="设置与偏好">⚙️</a>
    <div class="ss-user has-mega">
      <div class="ss-avatar">👤</div>
      <div class="ss-mega ss-user-menu">
        <div class="ss-user-sec">🎨 界面风格（即时生效）</div>
        <select class="ss-style-select" onchange="ssSetStyle(this.value)">{opts}</select>
        <div class="ss-user-sec">👤 账户</div>
        <a class="ss-user-item" href="/我的">👤 个人中心</a>
        <a class="ss-user-item" href="/新手教程">📘 新手教程</a>{admin_html}{recents_html}
      </div>
    </div>
  </div>
</div>

"""
    from modules.drawer import drawer_css
    st.markdown(
        TOPNAV_CSS + drawer_css()
        + "<style>"
        # 内容区下移让出固定顶栏；侧栏退役；字号层级（核心大/次要小）
        ".block-container,[data-testid=\"stMainBlockContainer\"]{padding-top:66px!important}"
        "section[data-testid=\"stSidebar\"]{display:none!important}"
        "button[data-testid=\"stExpandSidebarButton\"]{display:none!important}"
        ".stMetric [data-testid=\"stMetricValue\"]{font-size:1.55rem!important}"
        "</style>"
        + html,
        unsafe_allow_html=True,
    )


TOPNAV_CSS = """
<style>
/* ════════ T-195 阿里云风格顶部 Mega 导航 ════════ */
.ss-topnav{position:fixed;top:0;left:0;right:0;height:52px;z-index:99999;
  background:var(--card,#fff);border-bottom:1px solid var(--border,#e2e8f0);
  display:flex;align-items:center;padding:0 18px;gap:2px;
  font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif}
.ss-brand{text-decoration:none;font-size:15px;color:var(--txt);margin-right:14px;white-space:nowrap}
.ss-brand b{color:var(--acc1)}
/* T-199 修复：menus 容器不得 overflow:hidden——mega 面板是容器内绝对定位子元素，
   hidden 会整块裁掉面板（悬停无反应的根因）；同时 .ss-menu 去掉 position:relative，
   让 .ss-mega 的 left/right:0 锚到 position:fixed 的 .ss-topnav → 面板全宽展开于顶栏正下方 */
.ss-topnav-menus{display:flex;align-items:center;gap:2px;flex:1;min-width:0;overflow:visible}
.ss-menu{padding:8px 13px;cursor:pointer;font-weight:600;font-size:14px;
  color:var(--txt);white-space:nowrap;border-radius:6px;user-select:none}
.ss-menu:hover{color:var(--acc1);background:color-mix(in srgb,var(--acc1) 8%,transparent)}
.ss-menu-link{text-decoration:none}
.ss-menu-active{color:var(--acc1)!important;background:color-mix(in srgb,var(--acc1) 10%,transparent)}
/* ── Mega 面板：全宽白面板，悬停展开 ── */
.ss-mega{display:none;position:absolute;top:100%;left:0;right:0;
  background:var(--card,#fff);border-bottom:1px solid var(--border,#e2e8f0);
  box-shadow:0 16px 40px rgba(8,12,30,.16);padding:18px 28px 22px;
  cursor:default;z-index:100000}
.ss-menu:hover .ss-mega{display:block}
.ss-mega-intro{max-width:520px;margin-bottom:12px}
.ss-mega-intro h4{margin:0 0 4px;font-size:15px;color:var(--acc1)}
.ss-mega-intro p{margin:0;font-size:12.5px;color:var(--txt2);line-height:1.5}
.ss-mega-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:4px 18px;
  max-height:56vh;overflow-y:auto;overflow-x:auto;padding-right:6px}
.ss-mega-sub{grid-column:1 / -1;font-size:11.5px;color:var(--acc1);font-weight:700;
  margin:8px 0 2px;letter-spacing:.5px}
.ss-entry{display:flex;align-items:center;gap:6px;padding:7px 10px;border-radius:6px;
  text-decoration:none;white-space:nowrap}
.ss-entry:hover{background:color-mix(in srgb,var(--acc1) 8%,transparent)}
.ss-entry b{font-size:13.5px;font-weight:600;color:var(--txt)}
.ss-entry-active b{color:var(--acc1)}
.ss-entry-active{background:color-mix(in srgb,var(--acc1) 8%,transparent)}
.ss-tag{font-size:10px;padding:1px 6px;border-radius:3px;font-style:normal;font-weight:700;flex-shrink:0}
.ss-tag-hot{background:rgba(255,42,109,.12);color:#ff2a6d}
.ss-tag-new{background:rgba(0,168,204,.14);color:#0090b8}
/* ── 右侧：搜索 / 小图标 / 用户下拉（图标缩小——阿里云密度） ── */
.ss-topnav-right{display:flex;align-items:center;gap:8px;margin-left:auto}
.ss-search{padding:5px 14px;border:1px solid var(--border,#e2e8f0);border-radius:6px;
  color:var(--txt2);font-size:12.5px;cursor:pointer;white-space:nowrap;user-select:none}
.ss-search:hover{border-color:var(--acc1);color:var(--acc1)}
.ss-search kbd{font-size:10px;border:1px solid var(--border);border-radius:3px;padding:0 4px;margin-left:4px}
.ss-ico{width:28px;height:28px;display:flex;align-items:center;justify-content:center;
  font-size:13px;border-radius:5px;text-decoration:none;color:var(--txt2)}
.ss-ico:hover{background:color-mix(in srgb,var(--acc1) 10%,transparent);color:var(--acc1)}
.ss-user{position:relative;cursor:pointer}
.ss-avatar{width:30px;height:30px;border-radius:50%;background:color-mix(in srgb,var(--acc1) 14%,transparent);
  display:flex;align-items:center;justify-content:center;font-size:14px}
.ss-user-menu{right:0;left:auto!important;width:250px;padding:14px}
.ss-user:hover .ss-mega{display:block}
.ss-style-select{width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;
  background:var(--card);color:var(--txt);font-size:13px;margin-bottom:10px}
.ss-user-sec{font-size:11px;color:var(--acc1);font-weight:700;margin:8px 0 4px;letter-spacing:.5px}
.ss-user-item{display:block;padding:6px 8px;border-radius:5px;text-decoration:none;
  color:var(--txt);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ss-user-item:hover{background:color-mix(in srgb,var(--acc1) 8%,transparent);color:var(--acc1)}
/* ── 字号层级：核心突出 / 次要收敛（阿里云简洁层级） ── */
.stMarkdown p{line-height:1.55}
[data-testid="stMetricLabel"]{font-size:.78rem!important}
/* ── 响应式 ── */
@media(max-width:1100px){.ss-menu{padding:8px 9px;font-size:13px}}
@media(max-width:860px){.ss-search{display:none}}
</style>
"""


def build_nav_index(nav_groups: list, nav_hero: list, nav_admin: list,
                    favorites: list) -> list[dict]:
    """扁平化导航索引（命令面板数据源）：[{label, icon, href, group}]。"""
    idx: list[dict] = []
    for p, l, i in nav_hero:
        idx.append({"label": l, "icon": i, "href": _slug(p), "group": "决策中枢"})
    for top_label, clusters in nav_groups:
        for _sub, items in clusters:
            for p, l, i in items:
                idx.append({"label": l, "icon": i, "href": _slug(p), "group": top_label})
    for p, l, i in favorites:
        idx.append({"label": l, "icon": i, "href": _slug(p), "group": "常用"})
    for p, l, i in nav_admin:
        idx.append({"label": l, "icon": i, "href": _slug(p), "group": "管理"})
    return idx


def topnav_extra_js() -> str:
    """顶栏专属 JS（T-197 经 scroll_nav extra_js 通道并入单次 components.html 注入）。

    修复历史：T-195 曾把本段 JS 放在 st.markdown 的 <script> 中——Streamlit 会
    剥离 markdown 内 script，导致风格切换下拉实际不生效。现经 extra_js 通道可靠注入。
    """
    return """
/* ── T-195/T-197 顶栏 JS（风格切换 + 搜索聚焦命令面板）── */
function ssSetStyle(v){
  try {
    var raw = localStorage.getItem('ss_prefs');
    var p = raw ? JSON.parse(raw) : {};
    p.ui_style = v;
    localStorage.setItem('ss_prefs', JSON.stringify(p));
    var params = new URLSearchParams(window.location.search);
    params.set('prefs', JSON.stringify(p));
    window.location.href = window.location.pathname + '?' + params.toString();
  } catch (e) { window.location.reload(); }
}
function ssFocusSearch(){
  try {
    if (window.__ssOpenPalette) { window.__ssOpenPalette(); return; }
  } catch (e) {}
  try {
    var sb = window.document.querySelector('[data-testid="stSidebar"]');
    if (sb) { var inp = sb.querySelector('input'); if (inp) { inp.focus(); return; } }
  } catch (e) {}
}
"""
