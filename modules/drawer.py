# -*- coding: utf-8 -*-
"""
modules/drawer.py — 全局右侧滑出详情抽屉（T-198，交互方案 D）
==============================================================

用途：列表点击「👁 预览」不跳页，右侧滑出抽屉快速预览内容（标题/摘要/元信息），
需要完整功能时再点击列表标题进入同页详情视图——减少页面跳转的臃肿感。

架构（与 scroll_nav 同模式的关键约束）：
  · Streamlit 同页多次 components.html 仅【首次】脚本可靠执行，故本组件 JS 不单独
    注入，而以 drawer_js() 字符串由 widgets.inject_global_widgets 经
    inject_scroll_nav(extra_js=...) 并入 scroll_nav 单次注入。
  · 业务侧调用：window.parent.__ssDrawer.show(title, html, meta)——st.markdown
    内联 onclick 即可触发（无 <script> 标签、不被 Streamlit 剥离）。
  · 颜色全走 CSS 变量，六套风格自动适配。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def js_escape(text: str) -> str:
    """JS 字符串字面量转义（反斜杠/引号/换行/回车/尖括号），防注入与语法破坏。"""
    t = str(text)
    t = t.replace("\\\\", "\\\\\\\\")
    t = t.replace("'", "\\\\'")
    t = t.replace('"', '\\\\"')
    t = t.replace("\\r", "\\\\r")
    t = t.replace("\\n", "\\\\n")
    t = t.replace("<", "&lt;").replace(">", "&gt;")
    return t


def drawer_js() -> str:
    """抽屉组件 JS（由 widgets 经 extra_js 通道并入 scroll_nav 单次注入）。"""
    return """
/* ── T-198 全局右侧滑出详情抽屉 ── */
if (!window.__ssDrawer) {
  var ssd = document.createElement('div');
  ssd.id = 'ssDrawerRoot';
  ssd.innerHTML = '<div class="ss-drawer-backdrop"></div>'
    + '<div class="ss-drawer-panel"><div class="ss-drawer-head">'
    + '<b class="ss-drawer-title"></b><button class="ss-drawer-close" title="关闭">✕</button></div>'
    + '<div class="ss-drawer-meta"></div><div class="ss-drawer-body"></div></div>';
  document.body.appendChild(ssd);
  var root = document.getElementById('ssDrawerRoot');
  var pTitle = root.querySelector('.ss-drawer-title');
  var pMeta = root.querySelector('.ss-drawer-meta');
  var pBody = root.querySelector('.ss-drawer-body');
  function ssDrawerHide(){ root.classList.remove('open'); }
  root.querySelector('.ss-drawer-close').addEventListener('click', ssDrawerHide);
  root.querySelector('.ss-drawer-backdrop').addEventListener('click', ssDrawerHide);
  window.__ssDrawer = {
    show: function(title, html, meta){
      pTitle.textContent = title || '';
      pMeta.innerHTML = meta || '';
      pBody.innerHTML = html || '';
      root.classList.add('open');
    },
    hide: ssDrawerHide
  };
}
"""


def drawer_css() -> str:
    """抽屉 CSS（随 render_topnav 的 markdown 注入，变量驱动六风格适配）。"""
    return """
<style>
/* ════════ T-198 全局右侧滑出详情抽屉 ════════ */
#ssDrawerRoot{font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif}
#ssDrawerRoot .ss-drawer-backdrop{position:fixed;inset:0;background:rgba(8,10,24,.45);
  opacity:0;pointer-events:none;transition:opacity .25s ease;z-index:100003}
#ssDrawerRoot .ss-drawer-panel{position:fixed;top:0;right:-460px;width:min(440px,92vw);height:100vh;
  background:var(--card,#fff);border-left:1px solid var(--border,#e2e8f0);
  box-shadow:-18px 0 50px rgba(8,12,30,.28);z-index:100004;
  transition:right .28s cubic-bezier(.4,0,.2,1);
  display:flex;flex-direction:column;padding:18px 20px;box-sizing:border-box}
#ssDrawerRoot.open .ss-drawer-backdrop{opacity:1;pointer-events:auto}
#ssDrawerRoot.open .ss-drawer-panel{right:0}
#ssDrawerRoot .ss-drawer-head{display:flex;align-items:center;justify-content:space-between;
  gap:10px;border-bottom:1px solid var(--border,#e2e8f0);padding-bottom:10px;margin-bottom:10px}
#ssDrawerRoot .ss-drawer-title{font-size:15.5px;font-weight:800;color:var(--txt,#1f2937);
  line-height:1.4;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical}
#ssDrawerRoot .ss-drawer-close{border:none;background:transparent;color:var(--txt2,#6b7280);
  font-size:16px;cursor:pointer;padding:4px 8px;border-radius:6px;flex-shrink:0}
#ssDrawerRoot .ss-drawer-close:hover{background:color-mix(in srgb,var(--acc1,#4f46e5) 10%,transparent);
  color:var(--acc1,#4f46e5)}
#ssDrawerRoot .ss-drawer-meta{font-size:12px;color:var(--txt2,#6b7280);margin-bottom:10px;line-height:1.6}
#ssDrawerRoot .ss-drawer-body{flex:1;overflow-y:auto;font-size:13.5px;color:var(--txt,#1f2937);
  line-height:1.65;white-space:pre-wrap;word-break:break-word}
.ss-preview-btn{border:1px solid var(--border,#e2e8f0);background:transparent;
  color:var(--txt2,#6b7280);border-radius:6px;padding:2px 8px;font-size:11.5px;cursor:pointer;
  transition:all .15s ease;margin-left:6px}
.ss-preview-btn:hover{color:var(--acc1,#4f46e5);border-color:var(--acc1,#4f46e5)}
</style>
"""


def preview_button(title: str, body_html: str, meta_html: str = "",
                   label: str = "👁 预览") -> str:
    """生成「👁 预览」按钮 HTML（st.markdown unsafe 渲染，onclick 调全局抽屉）。

    :param title: 抽屉标题（自动 JS 转义）
    :param body_html: 抽屉正文（允许内嵌安全 HTML；调用方负责转义用户内容）
    :param meta_html: 元信息行（作者/时间/数据等）
    """
    t = js_escape(title)
    b = js_escape(body_html)
    m = js_escape(meta_html)
    onclick = ("(window.parent.__ssDrawer||{show:function(){}}).show('"
               + t + "','" + b + "','" + m + "')")
    onclick_attr = onclick.replace('"', "&quot;")
    return ('<button class="ss-preview-btn" type="button" onclick="'
            + onclick_attr + '">' + label + "</button>")
