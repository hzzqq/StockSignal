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


def _entry_html(path: str, label: str, icon: str, cur_base: str, q: str = "") -> str:
    """mega 面板单个条目（名称 + 图标 + NEW/HOT 标签）。"""
    base = path.replace("\\", "/").split("/")[-1]
    active = " ss-entry-active" if base == cur_base else ""
    badge = ""
    if base in _ENTRY_BADGES:
        txt, cls = _ENTRY_BADGES[base]
        badge = f'<i class="ss-tag {cls}">{txt}</i>'
    href = _slug(path) + q
    return (f'<a class="ss-entry{active}" href="{href}" title="{label}">'
            f'<b>{icon} {label}</b>{badge}</a>')


def render_topnav(nav_groups: list, nav_hero: list, nav_admin: list,
                  favorites: list, recents: list, current_style: str = "classic",
                  is_admin_user: bool = False, cur_base: str = "",
                  nav_qs: str = "") -> None:
    """渲染阿里云风格顶部 Mega 导航 + 侧栏退役 CSS + 字号层级。

    :param nav_groups: widgets._NAV_GROUPS（[(类目名, [(子类, [(path,label,icon[,sub])])])]）
    :param nav_hero: 决策中枢 Hero 条目
    :param nav_admin: 管理员条目
    :param favorites: ⭐ 常用 Top5
    :param recents: 最近浏览股票 [{code,name}]
    :param current_style: 当前界面风格（锚点选中态标记）
    :param is_admin_user: 是否管理员（显示管理入口）
    :param cur_base: 当前页 basename（高亮）
    :param nav_qs: 导航查询串（token+u+prefs，session.nav_query_string 生成）——
        T-201：<a href> 整页跳转必须携带，落页由 query_params 快速路径原位恢复
        登录态与界面状态（component iframe 发起的父页导航被 sandbox 拦截，
        localStorage 兜底脚本被 Streamlit 剥离，均不可靠）。
    """
    import streamlit as st

    q = ("?" + nav_qs) if nav_qs else ""
    qa = ("&" + nav_qs) if nav_qs else ""

    # ── 组装类目菜单 ──
    menus = []
    # 首页（直链，无面板）
    home_active = ' ss-menu-active' if cur_base == "app.py" else ""
    menus.append(f'<a class="ss-menu ss-menu-link{home_active}" href="/{q}">🏠 首页</a>')
    # 决策中枢（Hero 常驻第一面板）
    hero_entries = "".join(
        _entry_html(p, l, i, cur_base, q) + (
            '<i class="ss-tag ss-tag-hot">HOT</i>' if "54_" in p else "")
        for p, l, i in nav_hero)
    intro_hero = _GROUP_INTROS.get("🎯 决策中枢", "")
    menus.append(
        '<div class="ss-menu has-mega">🎯 决策中枢'
        '<div class="ss-mega"><div class="ss-mega-intro"><h4>决策中枢 ></h4>'
        f'<p>{intro_hero}</p></div>'
        f'<div class="ss-mega-grid">{hero_entries}'
        + "".join(_entry_html(p, l, i, cur_base, q) for p, l, i in favorites)
        + "</div></div></div>")
    # 六大类目
    for top_label, clusters in nav_groups:
        intro = _GROUP_INTROS.get(top_label, "")
        rows = []
        for sub, items in clusters:
            if sub:
                rows.append(f'<div class="ss-mega-sub">{sub}</div>')
            rows.append("".join(_entry_html(p, l, i, cur_base, q) for p, l, i in items))
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
            recents_html += (f'<a class="ss-user-item" href="/个股分析?pick_stock={rc}{qa}">'
                             f'🕘 {rn} {rc}</a>')
    if recents_html:
        recents_html = '<div class="ss-user-sec">🕘 最近浏览</div>' + recents_html

    # 风格切换（T-201：JS select → 纯锚点导航。用户手势导航不受 iframe sandbox
    # 限制；相对 ?href 保留当前路径，携带 token/u/prefs 落页原位恢复）
    style_labels = {
        "classic": "经典星辰（默认）", "terminal": "A · 彭博终端风",
        "swiss": "B · 瑞士极简白", "aurora": "C · 极光玻璃 2.0",
        "ink": "D · 东方墨韵", "cyber": "E · 赛博朋克 2077",
    }
    import json as _json
    from urllib.parse import urlencode as _urlencode, parse_qs as _parse_qs
    _base = {k: v[0] for k, v in _parse_qs(nav_qs).items()} if nav_qs else {}
    _prefs = {}
    if _base.get("prefs"):
        try:
            _prefs = _json.loads(_base["prefs"])
        except Exception:
            _prefs = {}
    style_links = []
    for k, v in style_labels.items():
        _p = dict(_base)
        _pk = dict(_prefs)
        _pk["ui_style"] = k
        _p["prefs"] = _json.dumps(_pk, ensure_ascii=False)
        cur = ' ss-style-cur' if k == current_style else ""
        mark = "✓ " if k == current_style else ""
        style_links.append(
            f'<a class="ss-user-item ss-style-opt{cur}" href="?{_urlencode(_p)}">{mark}{v}</a>')
    style_html = "".join(style_links)

    admin_html = ""
    if is_admin_user:
        admin_html = '<div class="ss-user-sec">🛡 管理</div>' + "".join(
            f'<a class="ss-user-item" href="{_slug(p)}{q}">{i} {l}</a>'
            for p, l, i in nav_admin)

    html = f"""
<div class="ss-topnav">
  <a class="ss-brand" href="/{q}">📈 <b>StockSignal</b></a>
  <nav class="ss-topnav-menus">{''.join(menus)}</nav>
  <div class="ss-topnav-right">
    <div class="ss-search" onclick="ssFocusSearch()" title="搜索（⌘K / Ctrl+K）">
      🔍 搜索 <kbd>⌘K</kbd>
    </div>
    <a class="ss-ico" href="/星辰AI{q}" title="星辰 AI">✦</a>
    <a class="ss-ico" href="/我的{q}" title="设置与偏好">⚙️</a>
    <div class="ss-user has-mega">
      <div class="ss-avatar">👤</div>
      <div class="ss-mega ss-user-menu">
        <div class="ss-user-sec">🎨 界面风格（点击即切换）</div>
        {style_html}
        <div class="ss-user-sec">👤 账户</div>
        <a class="ss-user-item" href="/我的{q}">👤 个人中心</a>
        <a class="ss-user-item" href="/新手教程{q}">📘 新手教程</a>{admin_html}{recents_html}
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
/* T-199/T-201：menus 容器不裁剪（overflow:hidden 曾裁掉 mega 面板）；.ss-menu 去
   position:relative（面板锚 .ss-topnav 全宽）并满栏高——菜单项曾只有内容高（约 37px），
   项底与面板顶（52px 栏底）之间存在约 8px hover 死区，鼠标移入面板即穿过死区导致展开即收 */
.ss-topnav-menus{display:flex;align-items:stretch;gap:2px;flex:1;min-width:0;overflow:visible;align-self:stretch}
.ss-menu{display:flex;align-items:center;height:100%;padding:0 13px;cursor:pointer;font-weight:600;font-size:14px;
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
/* T-201 点击钉住：hover 可展开；点击类目固定展开（鼠标在面板内自由移动不再收起），
   点击面板外其他区域或再点一次类目才收起 */
.ss-menu.ss-menu-pinned .ss-mega{display:block}
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
/* T-201 风格切换=锚点导航（用户手势导航不受 iframe sandbox 限制；JS select 路径废除） */
.ss-style-opt{display:flex;align-items:center;gap:6px}
.ss-style-cur{color:var(--acc1)!important;font-weight:700}
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
                    favorites: list, nav_qs: str = "") -> list[dict]:
    """扁平化导航索引（命令面板数据源）：[{label, icon, href, group}]。

    T-201：href 携带导航查询串（token+u+prefs）——面板跳转为整页加载，
    必须自带登录态（localStorage 兜底脚本被 Streamlit 剥离，不可靠）。
    """
    q = ("?" + nav_qs) if nav_qs else ""

    def _h(path: str) -> str:
        return _slug(path) + q

    idx: list[dict] = []
    for p, l, i in nav_hero:
        idx.append({"label": l, "icon": i, "href": _h(p), "group": "决策中枢"})
    for top_label, clusters in nav_groups:
        for _sub, items in clusters:
            for p, l, i in items:
                idx.append({"label": l, "icon": i, "href": _h(p), "group": top_label})
    for p, l, i in favorites:
        idx.append({"label": l, "icon": i, "href": _h(p), "group": "常用"})
    for p, l, i in nav_admin:
        idx.append({"label": l, "icon": i, "href": _h(p), "group": "管理"})
    return idx


def topnav_extra_js() -> str:
    """顶栏专属 JS（经 scroll_nav extra_js 通道并入单次 components.html 注入；
    脚本运行于组件 iframe，P = window.parent 即应用主文档窗口）。

    T-201 作用域修复：顶栏 HTML 的内联 onclick 在【父文档】解析标识符——历史版本
    把函数定义在 iframe 作用域且函数体使用 iframe 的 window.location，导致皮肤
    切换/搜索点击失效（父文档 ReferenceError 或导航错打 iframe）。现统一挂载到 P；
    风格切换改为纯锚点导航（用户手势不受 sandbox 限制），ssSetStyle 随之废除。
    """
    return """
/* ── T-201 顶栏搜索：P 作用域暴露（内联 onclick 兜底）+ 事件委托（时序免疫）── */
P.ssFocusSearch = function(){
  try { if (P.__ssOpenPalette) { P.__ssOpenPalette(); return; } } catch (e) {}
  try {
    var sb = P.document.querySelector('[data-testid="stSidebar"]');
    if (sb) { var inp = sb.querySelector('input'); if (inp) { inp.focus(); return; } }
  } catch (e) {}
};
try {
  if (!P.__ssSearchBound) {
    P.__ssSearchBound = true;
    P.document.addEventListener('mousedown', function(ev){
      var t = ev.target;
      if (t && t.closest && t.closest('.ss-search')) {
        ev.preventDefault();
        if (P.__ssOpenPalette) P.__ssOpenPalette();
      }
    }, true);
  }
} catch (eS) {}
/* ── T-201 mega 面板钉住：点击类目固定展开，点击面板外/再点一次收起（hover 展开保留）── */
try {
  if (!P.__ssMegaBound) {
    P.__ssMegaBound = true;
    P.document.addEventListener('click', function(ev){
      var t = ev.target;
      if (!t || !t.closest) return;
      if (t.closest('.ss-mega')) return;  /* 面板内点击=条目导航，不干预 */
      var m = t.closest('.ss-menu.has-mega');
      var wasPinned = m && m.classList.contains('ss-menu-pinned');
      var all = P.document.querySelectorAll('.ss-menu.ss-menu-pinned');
      for (var i = 0; i < all.length; i++) all[i].classList.remove('ss-menu-pinned');
      if (m && !wasPinned) {
        m.classList.add('ss-menu-pinned');
        ev.preventDefault();
        ev.stopPropagation();
      }
    }, true);
  }
} catch (eM) {}
"""
