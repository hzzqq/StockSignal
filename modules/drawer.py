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
  · 业务侧调用：window.parent.__ssDrawer.show(title, html, meta)。
  · **触发方式（T-315 修复）**：按钮不再用内联 onclick —— Streamlit 的 markdown
    渲染器会剥离该属性（实测 DOM 里 onclick 消失，React 报 #231「onClick 收到
    string」），导致 show() 从未被调用、抽屉始终不弹出。改为 data 承载 + 事件委托：
    preview_button 输出隐藏 <textarea class="ss-preview-src">（标题/正文/元信息，
    用 textarea 而非 data-* 属性是因为 HTML 属性会把换行规范化成空格），
    drawer_js 在父文档注册一次 click 委托（__ssDrawerBound 防重复绑定）。
  · 颜色全走 CSS 变量，六套风格自动适配。
"""
from __future__ import annotations

import html
import logging

logger = logging.getLogger(__name__)


def js_escape(text: str) -> str:
    """JS 字符串字面量转义（反斜杠/引号/换行/回车/尖括号），防注入与语法破坏。"""
    t = str(text)
    t = t.replace("\\", "\\\\")
    t = t.replace("'", "\\'")
    t = t.replace('"', '\\"')
    t = t.replace("\n", "\\n")
    t = t.replace("\r", "\\r")
    t = t.replace("<", "&lt;").replace(">", "&gt;")
    return t


def drawer_js() -> str:
    """抽屉组件 JS（由 widgets 经 extra_js 通道并入 scroll_nav 单次注入）。

    T-315 缺陷修复（阻塞级）：本段 JS 运行在 components.html 的**组件 iframe** 内，
    历史版本直接使用裸 ``window`` / ``document`` —— 抽屉 DOM 被建在 iframe 里（用户
    看不到，功能实际失效），且 iframe 内 ``document.body`` 在时序上可能为 null，
    appendChild 抛 TypeError 后被 _nav_script 外层 try 吞掉，**导致拼接在其后的
    全部 extra_js（自动滚底、复制回答）永不执行**。
    现统一改用 _nav_script 注入点提供的 ``P``（= window.parent），与 topnav 一致；
    并自包 try，避免本段异常再次阻断后续脚本。
    """
    return """
/* ── T-198 全局右侧滑出详情抽屉（T-315：P 作用域修复 + 自隔离）── */
try {
if (!P.__ssDrawer) {
  var ssd = P.document.createElement('div');
  ssd.id = 'ssDrawerRoot';
  ssd.innerHTML = '<div class="ss-drawer-backdrop"></div>'
    + '<div class="ss-drawer-panel"><div class="ss-drawer-head">'
    + '<b class="ss-drawer-title"></b><button class="ss-drawer-close" title="关闭">✕</button></div>'
    + '<div class="ss-drawer-meta"></div><div class="ss-drawer-body"></div></div>';
  P.document.body.appendChild(ssd);
  var root = P.document.getElementById('ssDrawerRoot');
  var pTitle = root.querySelector('.ss-drawer-title');
  var pMeta = root.querySelector('.ss-drawer-meta');
  var pBody = root.querySelector('.ss-drawer-body');
  function ssDrawerHide(){ root.classList.remove('open'); }
  root.querySelector('.ss-drawer-close').addEventListener('click', ssDrawerHide);
  root.querySelector('.ss-drawer-backdrop').addEventListener('click', ssDrawerHide);
  P.__ssDrawer = {
    show: function(title, html, meta){
      pTitle.textContent = title || '';
      pMeta.innerHTML = meta || '';
      pBody.innerHTML = html || '';
      root.classList.add('open');
    },
    hide: ssDrawerHide
  };
}
} catch (eD) {}

/* ── T-315 触发层：预览按钮事件委托（替代被 Streamlit 剥离的内联 onclick）── */
try {
if (!P.__ssDrawerBound) {
  P.__ssDrawerBound = true;
  P.document.addEventListener('click', function(ev){
    var t = ev.target, btn = null;
    while (t && t !== P.document) {
      if (t.classList && t.classList.contains('ss-preview-btn')) { btn = t; break; }
      t = t.parentElement;
    }
    if (!btn) return;
    ev.preventDefault();
    var wrap = btn.parentElement;
    function pick(kind){
      if (!wrap) return '';
      var ns = wrap.querySelectorAll('.ss-preview-src');
      for (var i = 0; i < ns.length; i++) {
        if (ns[i].getAttribute('data-k') === kind) return ns[i].value || '';
      }
      return '';
    }
    if (P.__ssDrawer && P.__ssDrawer.show) {
      P.__ssDrawer.show(pick('title'), pick('body'), pick('meta'));
    }
  }, true);
}
} catch (eB) {}
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
.ss-preview-wrap{display:inline-block}
.ss-preview-btn{border:1px solid var(--border,#e2e8f0);background:transparent;
  color:var(--txt2,#6b7280);border-radius:6px;padding:2px 8px;font-size:11.5px;cursor:pointer;
  transition:all .15s ease;margin-left:6px}
.ss-preview-btn:hover{color:var(--acc1,#4f46e5);border-color:var(--acc1,#4f46e5)}
</style>
"""


def preview_button(title: str, body_html: str, meta_html: str = "",
                   label: str = "👁 预览") -> str:
    """生成「👁 预览」按钮 HTML（st.markdown unsafe 渲染，点击触发全局抽屉）。

    T-315：**不再使用内联 onclick**——Streamlit 的 markdown 渲染器会剥离该属性
    （实测按钮 DOM 里没有 onclick，React 报 #231「onClick 收到 string」），导致
    抽屉永不弹出。改为三个隐藏 textarea 承载标题/正文/元信息，由 drawer_js 的
    父文档 click 委托读取并调用 __ssDrawer.show。

    为什么用 textarea 而不是 data-*：HTML 属性会把换行规范化成空格，多行正文
    复制/展示会粘连；textarea 的值保留原始换行。
    安全：三个字段均经 html.escape（textarea 内的 HTML 源码必须转义，浏览器解析
    后会还原为原文本/原 HTML 片段，与旧 js_escape + innerHTML 行为等价）。

    :param title: 抽屉标题
    :param body_html: 抽屉正文（调用方负责转义用户内容；允许安全 HTML）
    :param meta_html: 元信息行（作者/时间/数据等）
    """
    def _ta(kind: str, val: str) -> str:
        return (f'<textarea class="ss-preview-src" data-k="{kind}" readonly hidden>'
                f'{html.escape(str(val), quote=False)}</textarea>')

    return ('<div class="ss-preview-wrap">'
            + _ta("title", title) + _ta("body", body_html) + _ta("meta", meta_html)
            + '<button class="ss-preview-btn" type="button">' + label + "</button>"
            + "</div>")
