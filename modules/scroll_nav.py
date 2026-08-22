"""
回到顶部 / 回到底部 · Streamlit 导航组件库 v2
================================================
精准复刻 WorkBuddy 对话界面的 ▼ 回到底部按钮 + 反向 ▲ 回到顶部。

【WorkBuddy 原版 ▼ 解析】（来自用户截图）
  位置：消息流区域右下角、输入栏上方（fixed 悬浮，right:24px; bottom:110px）
  触发：用户向上滚动（离开底部）时自动浮现
  样式：圆形 ~34px · 浅白/灰底(#f0f0f5) · 灰蓝 ▼ 箭头(#6b7280) · 轻投影
  行为：window.scrollTo({top:scrollHeight, behavior:'smooth'})
  消失：已在底部(距底≤150px)时自动隐藏
  暗色：自动切换 .dark 样式（深底 #1e1e32 + 浅字 #94a3b8）

【反向功能 ▲ 回到顶部】
  位置：页面右侧中部悬浮(top:50%)
  样式：圆形 · 紫蓝渐变底 · 白色 ▲ 箭头（星辰 accent 一致）
  触发：向下滚动超过 300px 时浮现

【Streamlit 适配要点】
  components.html 运行在 sandbox iframe 内，故按钮须创建在 window.parent.document
  才能成为「视口级」悬浮元素；滚动监听也挂在 window.parent 上。
  幂等：以根节点 id 存在性判定，rerun 不会重复创建。

【关键约束 / 踩坑】
  Streamlit 的 components.html 对「同一 payload 内的第二段 <script>」以及
  「额外的 components.html 调用」并不可靠——实测单独注入的脚本在部分 iframe 中
  虽存在于 DOM 却【从不执行】。因此：▲ / ▼ / C 键清缓存拦截 必须合并进
  **同一个 <script> IIFE**，由 inject_scroll_nav 经一次 components.html 注入。
  （st.markdown("<script>") 也会被 Streamlit 过滤掉，不可用。）

依赖：无第三方依赖。纯 CSS + JS + Streamlit components.html。
设计依据：星辰暗色金融风 Token（复用 starfield_theme.py :root）。
"""
import streamlit as st
import streamlit.components.v1 as components
import json
import logging
logger = logging.getLogger(__name__)
SCROLL_NAV_CSS = '\n<style>\n/* ====== 回到顶部 —— 页面右侧中部悬浮（▲，紫蓝渐变） ====== */\n.sf-scroll-top{\n  position:fixed;right:24px;top:50%;transform:translateY(-50%);z-index:999;\n  width:36px;height:36px;border-radius:50%;\n  background:linear-gradient(135deg,#667eea,#764ba2);\n  color:#fff;border:none;cursor:pointer;display:none;\n  align-items:center;justify-content:center;font-size:16px;\n  box-shadow:0 4px 14px rgba(102,126,234,.4),0 2px 6px rgba(0,0,0,.25);\n  transition:all .25s ease;opacity:.88;line-height:1;\n}\n.sf-scroll-top:hover{opacity:1;transform:translateY(-50%) translateX(-3px);\n  box-shadow:0 6px 20px rgba(102,126,234,.55)}\n.sf-scroll-top.visible{display:flex;animation:sf-slideDown .28s ease}\n@keyframes sf-slideDown{from{opacity:0;transform:translateY(-45%)}to{opacity:1}}\n\n/* ====== 回到底部（WorkBuddy 原版）—— 消息流右下角、输入栏上方 ====== */\n.sf-scroll-bottom-float{\n  position:fixed;right:24px;bottom:110px;z-index:999;\n  width:34px;height:34px;border-radius:50%;\n  background:#f0f0f5;color:#6b7280;border:none;cursor:pointer;\n  display:none;align-items:center;justify-content:center;font-size:15px;\n  box-shadow:0 3px 12px rgba(0,0,0,.12),0 1px 4px rgba(0,0,0,.08);\n  transition:all .22s ease;line-height:1;\n}\n.sf-scroll-bottom-float.dark{\n  background:#1e1e32;color:#94a3b8;\n  box-shadow:0 3px 12px rgba(0,0,0,.3),0 1px 4px rgba(0,0,0,.2)\n}\n.sf-scroll-bottom-float:hover{\n  background:#e0e0e8;color:#374151;transform:translateY(-2px);\n  box-shadow:0 5px 18px rgba(0,0,0,.16)}\n.sf-scroll-bottom-float.dark:hover{background:#2a2a45;color:#e2e8f0}\n.sf-scroll-bottom-float.visible{display:flex;animation:sf-slideUp .26s ease}\n@keyframes sf-slideUp{from{opacity:0;transform:translateY(10px)}to{opacity:1}}\n\n/* ====== 弹层内嵌版 ▼（星辰 AI 右上角 popover 用，居中于输入栏上方）===== */\n.sf-scroll-bottom-inline{\n  width:34px;height:34px;border-radius:50%;cursor:pointer;\n  background:#f0f0f5;color:#6b7280;border:none;\n  display:inline-flex;align-items:center;justify-content:center;font-size:15px;\n  box-shadow:0 3px 12px rgba(0,0,0,.12),0 1px 4px rgba(0,0,0,.08);\n  transition:all .22s ease;line-height:1;\n}\n.sf-scroll-bottom-inline.dark{background:#1e1e32;color:#94a3b8;\n  box-shadow:0 3px 12px rgba(0,0,0,.3),0 1px 4px rgba(0,0,0,.2)}\n.sf-scroll-bottom-inline:hover{background:#e0e0e8;color:#374151;transform:translateY(-2px)}\n.sf-scroll-bottom-inline.dark:hover{background:#2a2a45;color:#e2e8f0}\n\n@media(max-width:768px){\n  .sf-scroll-top{right:14px;width:33px;height:33px;font-size:14px}\n  .sf-scroll-bottom-float{right:14px;bottom:90px;width:31px;height:31px;font-size:13px}\n}\n</style>'

def _nav_script(dark, threshold_px, bottom_threshold, show_top, show_bottom, bottom_marker=''):
    """构建【单一 <script> 块】的导航 + C 键清缓存拦截脚本。

    关键：所有逻辑（▲回到顶部 / ▼回到底部 / C键拦截+安全网）合并进**同一个**
    IIFE，经 components.html 一次性注入。避免多段 <script> 或多次 components.html
    调用时部分脚本不执行的问题（实测：同一页面多次调用 components.html 时，
    仅【第一次】调用的脚本可靠执行；后续调用被 Streamlit 视为同一 singleton 组件而失效）。

    bottom_marker：若非空，则顶层文档中出现 [data-testid="<bottom_marker>"] 元素时启用
    ▼ 回到底部（用于星辰 AI 对话页：该页使用 st.chat_input，testid 为 stChatInput，
    全站唯一；本脚本监听其出现即创建 ▼、消失即移除）。
    因 Streamlit 1.58 为客户端路由（pathname 恒为 "/"）且 st.markdown 会剥除 id，
    URL / 自定义 id 均不可靠，故改以 Streamlit 原生组件的 testid 作为页面标记。
    """
    cls = 'sf-scroll-bottom-float' + (' dark' if dark else '')
    show_top_js = 'true' if show_top else 'false'
    show_bottom_js = 'true' if show_bottom else 'false'
    body = '\n<script>\n(function(){\n  var P = window.parent || window;\n  if (!P || !P.document) return;\n  try {\n    // ▲ 回到顶部\n    if (__SHOW_TOP__) {\n      if (!P.document.getElementById(\'sfScrollTopBtn\')) {\n        var tbtn = P.document.createElement(\'button\');\n        tbtn.id = \'sfScrollTopBtn\';\n        tbtn.className = \'sf-scroll-top\';\n        tbtn.innerHTML = \'\\u25b2\';\n        tbtn.title = \'\\u56de\\u5230\\u9876\\u90e8\';\n        tbtn.onclick = function(){ P.scrollTo({top:0, behavior:\'smooth\'}); };\n        P.document.body.appendChild(tbtn);\n        function tupdate(){\n          if ((P.scrollY || P.pageYOffset || 0) > __THRESH__) tbtn.classList.add(\'visible\');\n          else tbtn.classList.remove(\'visible\');\n        }\n        P.addEventListener(\'scroll\', tupdate, {passive:true});\n        setTimeout(tupdate, 200);\n        new MutationObserver(function(){ setTimeout(tupdate, 100); }).observe(P.document.body, {childList:true, subtree:true});\n      }\n    }\n    // ▼ 回到底部（由页面标记元素 __BOTTOM_MARKER_SEL__ 的存在性驱动）\n    // 说明：Streamlit 1.58 为客户端路由，window.location.pathname 恒为 "/"，\n    // 无法用 URL 区分页面；故由星辰 AI 对话页用 st.markdown 渲染一个隐藏标记元素，\n    // 本脚本监听该标记出现即创建 ▼、消失即移除，确保 ▼ 仅在该页出现。\n    // （本脚本位于每页唯一可靠执行的首次 components.html 注入中，无需二次调用。）\n    if (__SHOW_BOTTOM__ && __BOTTOM_MARKER_JS__ !== \'\') {\n      var bbtn = null;\n      function createBottomBtn(){\n        var broot = P.document.getElementById(\'sfChatBottomRoot\');\n        if (broot) { bbtn = P.document.getElementById(\'sfChatBottomBtn\'); if (bbtn) bbtn.className = \'__CLS__\'; }\n        else {\n          broot = P.document.createElement(\'div\'); broot.id = \'sfChatBottomRoot\';\n          bbtn = P.document.createElement(\'button\'); bbtn.id = \'sfChatBottomBtn\'; bbtn.className = \'__CLS__\'; bbtn.__xcAuto = true;\n          bbtn.innerHTML = \'\\u25bc\'; bbtn.title = \'\\u56de\\u5230\\u5e95\\u90e8\';\n          bbtn.onclick = function(){ P.scrollTo({top: P.document.body.scrollHeight, behavior:\'smooth\'}); };\n          broot.appendChild(bbtn); P.document.body.appendChild(broot);\n        }\n      }\n      function bupdate(){\n        if (!bbtn) return;\n        var sy=P.scrollY||P.pageYOffset||0, dh=P.document.documentElement.scrollHeight, wh=P.innerHeight;\n        var distBottom = dh-(sy+wh);\n        if (distBottom > __BTH__) bbtn.classList.add(\'visible\'); else bbtn.classList.remove(\'visible\');\n      }\n      function syncBottom(){\n        var m = P.document.querySelector(\'[data-testid="__BOTTOM_MARKER_SEL__"]\');\n        var cur = P.document.getElementById(\'sfChatBottomBtn\');\n        if (m && !cur) { createBottomBtn(); bupdate(); }\n        else if (!m && cur && cur.__xcAuto) { if (cur.parentElement) cur.parentElement.remove(); }\n      }\n      syncBottom();\n      P.addEventListener(\'scroll\', bupdate, {passive:true});\n      setTimeout(bupdate, 200);\n      new MutationObserver(function(){ syncBottom(); }).observe(P.document.body, {childList:true, subtree:true});\n    }\n    // C 键清缓存拦截 + 安全网（合并进同一脚本，确保可靠执行）\n    function isEditingTarget(e){ var tag=(e.target&&e.target.tagName)||\'\'; var ed=e.target&&(e.target.isContentEditable||e.target.contentEditable===\'true\'); return tag===\'INPUT\'||tag===\'TEXTAREA\'||tag===\'SELECT\'||ed; }\n    function isPlainC(e){ var k=e.key||\'\'; var ic=(k===\'c\'||k===\'C\'||e.keyCode===67||e.which===67); if(!ic)return false; if(e.ctrlKey||e.metaKey||e.altKey)return false; return true; }\n    function ch(e){ if(!isPlainC(e))return; if(isEditingTarget(e))return; e.preventDefault(); e.stopPropagation(); if(e.stopImmediatePropagation)e.stopImmediatePropagation(); }\n    if(!P.__stocksignal_cache_handler_added){\n      P.__stocksignal_cache_handler_added=true;\n      [\'keydown\',\'keyup\',\'keypress\'].forEach(function(ev){ P.addEventListener(ev, ch, true); if(P.document)P.document.addEventListener(ev, ch, true); });\n    }\n    function dismissClearCache(){\n      try {\n        var d=P.document.querySelector(\'[role="dialog"]\'); if(!d)return;\n        var t=(d.innerText||\'\').toLowerCase();\n        if(t.indexOf(\'clear cache\')>=0 || t.indexOf(\'清除\')>=0){\n          var bs=d.querySelectorAll(\'button\');\n          for(var i=0;i<bs.length;i++){ var bt=(bs[i].innerText||\'\').toLowerCase(); if(bt.indexOf(\'cancel\')>=0||bt.indexOf(\'取消\')>=0){ bs[i].click(); return; } }\n        }\n      } catch(e){}\n    }\n    if(P.__xc_dismiss_interval){ try{clearInterval(P.__xc_dismiss_interval);}catch(e){} }\n    P.__xc_dismiss_interval=setInterval(dismissClearCache,150);\n    if(P.__xc_dismiss_observer){ try{P.__xc_dismiss_observer.disconnect();}catch(e){} }\n    P.__xc_dismiss_observer=new MutationObserver(function(){dismissClearCache();});\n    P.__xc_dismiss_observer.observe(P.document.body,{childList:true,subtree:true});\n  } catch(e) {}\n})();\n</script>\n'
    marker_js = json.dumps(bottom_marker or '')
    marker_sel = (bottom_marker or '').replace('"', '\\"')
    body = body.replace('__SHOW_TOP__', show_top_js).replace('__SHOW_BOTTOM__', show_bottom_js).replace('__THRESH__', str(threshold_px)).replace('__BTH__', str(bottom_threshold)).replace('__CLS__', cls).replace('__BOTTOM_MARKER_JS__', marker_js).replace('__BOTTOM_MARKER_SEL__', marker_sel)
    return body

def inject_scroll_nav(show_top: bool=True, show_bottom: bool=False, threshold_px: int=300, bottom_threshold: int=150, dark: bool=False, bottom_marker: str=''):
    """注入 CSS + 悬浮导航按钮 JS + C 键清缓存拦截。每个页面顶部调一次（幂等）。

    参数：
      show_top         -- 启用 ▲ 回到顶部（默认全局启用）
      show_bottom      -- 显式启用 ▼ 回到底部（须配合 bottom_marker 指定页面标记；两者皆满足才创建）
      threshold_px     -- ▲ 显隐阈值：向下滚超此值显现
      bottom_threshold -- ▼ 显隐阈值：距底大于此值才显现
      dark             -- 是否暗色（影响 ▼ 配色）
      bottom_marker    -- 非空时，顶层文档存在该 id 标记元素即启用 ▼（用于星辰 AI 对话页）
    """
    st.markdown(SCROLL_NAV_CSS, unsafe_allow_html=True)
    st.markdown(_nav_script(dark, threshold_px, bottom_threshold, show_top, show_bottom, bottom_marker), unsafe_allow_html=True)

def scroll_bottom_inline_html(dark: bool=False) -> str:
    """弹层（星辰 AI popover）内嵌 ▼ 按钮 HTML（居中于输入栏上方，点击滚动聊天框到底）。"""
    cls = 'sf-scroll-bottom-inline' + (' dark' if dark else '')
    return f'''<div style="display:flex;justify-content:center;margin:10px 0 6px"><button class="{cls}" onclick="(function(){{var b=window.parent.document.querySelector('.ai-chat-box');if(b){{b.scrollTop=b.scrollHeight;}}}})()" title="回到底部">&#9660;</button></div>'''

def scroll_inline_button(direction='down', label=None):
    """内嵌行内按钮 HTML（用于 header/工具栏）。"""
    arrow = '&#9650;' if direction == 'up' else '&#9660;'
    txt = label or arrow
    title = '回到顶部' if direction == 'up' else '回到底部'
    target = '0' if direction == 'up' else 'document.body.scrollHeight'
    return '<button class="sf-scroll-inline" onclick="event.preventDefault();window.scrollTo({top:' + target + ',behavior:\\"smooth\\"})" title="' + title + '">' + txt + '</button>'

def chat_bottom_anchor():
    """消息流底部锚点元素（辅助定位）。"""
    return '<div id="sf-chat-end" style="height:1px"></div>'
if __name__ == '__main__':
    logger.info('scroll_nav v2 OK')