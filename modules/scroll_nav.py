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

# ===========================================================================
# CSS -- 双按钮悬浮导航（精准对齐 WorkBuddy 截图 v2）
# ===========================================================================
SCROLL_NAV_CSS = """
<style>
/* ====== 回到顶部 —— 页面右侧中部悬浮（▲，紫蓝渐变） ====== */
.sf-scroll-top{
  position:fixed;right:24px;top:50%;transform:translateY(-50%);z-index:999;
  width:36px;height:36px;border-radius:50%;
  background:linear-gradient(135deg,#667eea,#764ba2);
  color:#fff;border:none;cursor:pointer;display:none;
  align-items:center;justify-content:center;font-size:16px;
  box-shadow:0 4px 14px rgba(102,126,234,.4),0 2px 6px rgba(0,0,0,.25);
  transition:all .25s ease;opacity:.88;line-height:1;
}
.sf-scroll-top:hover{opacity:1;transform:translateY(-50%) translateX(-3px);
  box-shadow:0 6px 20px rgba(102,126,234,.55)}
.sf-scroll-top.visible{display:flex;animation:sf-slideDown .28s ease}
@keyframes sf-slideDown{from{opacity:0;transform:translateY(-45%)}to{opacity:1}}

/* ====== 回到底部（WorkBuddy 原版）—— 消息流右下角、输入栏上方 ====== */
.sf-scroll-bottom-float{
  position:fixed;right:24px;bottom:110px;z-index:999;
  width:34px;height:34px;border-radius:50%;
  background:#f0f0f5;color:#6b7280;border:none;cursor:pointer;
  display:none;align-items:center;justify-content:center;font-size:15px;
  box-shadow:0 3px 12px rgba(0,0,0,.12),0 1px 4px rgba(0,0,0,.08);
  transition:all .22s ease;line-height:1;
}
.sf-scroll-bottom-float.dark{
  background:#1e1e32;color:#94a3b8;
  box-shadow:0 3px 12px rgba(0,0,0,.3),0 1px 4px rgba(0,0,0,.2)
}
.sf-scroll-bottom-float:hover{
  background:#e0e0e8;color:#374151;transform:translateY(-2px);
  box-shadow:0 5px 18px rgba(0,0,0,.16)}
.sf-scroll-bottom-float.dark:hover{background:#2a2a45;color:#e2e8f0}
.sf-scroll-bottom-float.visible{display:flex;animation:sf-slideUp .26s ease}
@keyframes sf-slideUp{from{opacity:0;transform:translateY(10px)}to{opacity:1}}

/* ====== 弹层内嵌版 ▼（星辰 AI 右上角 popover 用，居中于输入栏上方）===== */
.sf-scroll-bottom-inline{
  width:34px;height:34px;border-radius:50%;cursor:pointer;
  background:#f0f0f5;color:#6b7280;border:none;
  display:inline-flex;align-items:center;justify-content:center;font-size:15px;
  box-shadow:0 3px 12px rgba(0,0,0,.12),0 1px 4px rgba(0,0,0,.08);
  transition:all .22s ease;line-height:1;
}
.sf-scroll-bottom-inline.dark{background:#1e1e32;color:#94a3b8;
  box-shadow:0 3px 12px rgba(0,0,0,.3),0 1px 4px rgba(0,0,0,.2)}
.sf-scroll-bottom-inline:hover{background:#e0e0e8;color:#374151;transform:translateY(-2px)}
.sf-scroll-bottom-inline.dark:hover{background:#2a2a45;color:#e2e8f0}

@media(max-width:768px){
  .sf-scroll-top{right:14px;width:33px;height:33px;font-size:14px}
  .sf-scroll-bottom-float{right:14px;bottom:90px;width:31px;height:31px;font-size:13px}
}
</style>"""


def _nav_script(dark, threshold_px, bottom_threshold, show_top, show_bottom, bottom_marker=""):
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
    cls = "sf-scroll-bottom-float" + (" dark" if dark else "")
    show_top_js = "true" if show_top else "false"
    show_bottom_js = "true" if show_bottom else "false"
    body = """
<script>
(function(){
  var P = window.parent || window;
  if (!P || !P.document) return;
  try {
    // ▲ 回到顶部
    if (__SHOW_TOP__) {
      if (!P.document.getElementById('sfScrollTopBtn')) {
        var tbtn = P.document.createElement('button');
        tbtn.id = 'sfScrollTopBtn';
        tbtn.className = 'sf-scroll-top';
        tbtn.innerHTML = '\\u25b2';
        tbtn.title = '\\u56de\\u5230\\u9876\\u90e8';
        tbtn.onclick = function(){ P.scrollTo({top:0, behavior:'smooth'}); };
        P.document.body.appendChild(tbtn);
        function tupdate(){
          if ((P.scrollY || P.pageYOffset || 0) > __THRESH__) tbtn.classList.add('visible');
          else tbtn.classList.remove('visible');
        }
        P.addEventListener('scroll', tupdate, {passive:true});
        setTimeout(tupdate, 200);
        new MutationObserver(function(){ setTimeout(tupdate, 100); }).observe(P.document.body, {childList:true, subtree:true});
      }
    }
    // ▼ 回到底部（由页面标记元素 __BOTTOM_MARKER__ 的存在性驱动）
    // 说明：Streamlit 1.58 为客户端路由，window.location.pathname 恒为 "/"，
    // 无法用 URL 区分页面；故由星辰 AI 对话页用 st.markdown 渲染一个隐藏标记元素，
    // 本脚本监听该标记出现即创建 ▼、消失即移除，确保 ▼ 仅在该页出现。
    // （本脚本位于每页唯一可靠执行的首次 components.html 注入中，无需二次调用。）
    if ('__BOTTOM_MARKER__' !== '') {
      var bbtn = null;
      function createBottomBtn(){
        var broot = P.document.getElementById('sfChatBottomRoot');
        if (broot) { bbtn = P.document.getElementById('sfChatBottomBtn'); if (bbtn) bbtn.className = '__CLS__'; }
        else {
          broot = P.document.createElement('div'); broot.id = 'sfChatBottomRoot';
          bbtn = P.document.createElement('button'); bbtn.id = 'sfChatBottomBtn'; bbtn.className = '__CLS__'; bbtn.__xcAuto = true;
          bbtn.innerHTML = '\\u25bc'; bbtn.title = '\\u56de\\u5230\\u5e95\\u90e8';
          bbtn.onclick = function(){ P.scrollTo({top: P.document.body.scrollHeight, behavior:'smooth'}); };
          broot.appendChild(bbtn); P.document.body.appendChild(broot);
        }
      }
      function bupdate(){
        if (!bbtn) return;
        var sy=P.scrollY||P.pageYOffset||0, dh=P.document.documentElement.scrollHeight, wh=P.innerHeight;
        var distBottom = dh-(sy+wh);
        if (distBottom > __BTH__) bbtn.classList.add('visible'); else bbtn.classList.remove('visible');
      }
      function syncBottom(){
        var m = P.document.querySelector('[data-testid="__BOTTOM_MARKER__"]');
        var cur = P.document.getElementById('sfChatBottomBtn');
        if (m && !cur) { createBottomBtn(); bupdate(); }
        else if (!m && cur && cur.__xcAuto) { if (cur.parentElement) cur.parentElement.remove(); }
      }
      syncBottom();
      P.addEventListener('scroll', bupdate, {passive:true});
      setTimeout(bupdate, 200);
      new MutationObserver(function(){ syncBottom(); }).observe(P.document.body, {childList:true, subtree:true});
    }
    // C 键清缓存拦截 + 安全网（合并进同一脚本，确保可靠执行）
    function isEditingTarget(e){ var tag=(e.target&&e.target.tagName)||''; var ed=e.target&&(e.target.isContentEditable||e.target.contentEditable==='true'); return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||ed; }
    function isPlainC(e){ var k=e.key||''; var ic=(k==='c'||k==='C'||e.keyCode===67||e.which===67); if(!ic)return false; if(e.ctrlKey||e.metaKey||e.altKey)return false; return true; }
    function ch(e){ if(!isPlainC(e))return; if(isEditingTarget(e))return; e.preventDefault(); e.stopPropagation(); if(e.stopImmediatePropagation)e.stopImmediatePropagation(); }
    if(!P.__stocksignal_cache_handler_added){
      P.__stocksignal_cache_handler_added=true;
      ['keydown','keyup','keypress'].forEach(function(ev){ P.addEventListener(ev, ch, true); if(P.document)P.document.addEventListener(ev, ch, true); });
    }
    function dismissClearCache(){
      try {
        var d=P.document.querySelector('[role="dialog"]'); if(!d)return;
        var t=(d.innerText||'').toLowerCase();
        if(t.indexOf('clear cache')>=0 || t.indexOf('清除')>=0){
          var bs=d.querySelectorAll('button');
          for(var i=0;i<bs.length;i++){ var bt=(bs[i].innerText||'').toLowerCase(); if(bt.indexOf('cancel')>=0||bt.indexOf('取消')>=0){ bs[i].click(); return; } }
        }
      } catch(e){}
    }
    if(P.__xc_dismiss_interval){ try{clearInterval(P.__xc_dismiss_interval);}catch(e){} }
    P.__xc_dismiss_interval=setInterval(dismissClearCache,150);
    if(P.__xc_dismiss_observer){ try{P.__xc_dismiss_observer.disconnect();}catch(e){} }
    P.__xc_dismiss_observer=new MutationObserver(function(){dismissClearCache();});
    P.__xc_dismiss_observer.observe(P.document.body,{childList:true,subtree:true});
  } catch(e) {}
})();
</script>
"""
    body = (body.replace("__SHOW_TOP__", show_top_js)
                 .replace("__SHOW_BOTTOM__", show_bottom_js)
                 .replace("__THRESH__", str(threshold_px))
                 .replace("__BTH__", str(bottom_threshold))
                 .replace("__CLS__", cls)
                 .replace("__BOTTOM_MARKER__", bottom_marker))
    return body


def inject_scroll_nav(
    show_top: bool = True,
    show_bottom: bool = False,
    threshold_px: int = 300,
    bottom_threshold: int = 150,
    dark: bool = False,
    bottom_marker: str = "",
):
    """注入 CSS + 悬浮导航按钮 JS + C 键清缓存拦截。每个页面顶部调一次（幂等）。

    参数：
      show_top         -- 启用 ▲ 回到顶部（默认全局启用）
      show_bottom      -- 显式启用 ▼ 回到底部
      threshold_px     -- ▲ 显隐阈值：向下滚超此值显现
      bottom_threshold -- ▼ 显隐阈值：距底大于此值才显现
      dark             -- 是否暗色（影响 ▼ 配色）
      bottom_marker    -- 非空时，顶层文档存在该 id 标记元素即启用 ▼（用于星辰 AI 对话页）
    """
    st.markdown(SCROLL_NAV_CSS, unsafe_allow_html=True)
    components.html(
        _nav_script(dark, threshold_px, bottom_threshold, show_top, show_bottom, bottom_marker),
        height=0,
    )


def scroll_bottom_inline_html(dark: bool = False) -> str:
    """弹层（星辰 AI popover）内嵌 ▼ 按钮 HTML（居中于输入栏上方，点击滚动聊天框到底）。"""
    cls = "sf-scroll-bottom-inline" + (" dark" if dark else "")
    return (
        '<div style="display:flex;justify-content:center;margin:10px 0 6px">'
        f'<button class="{cls}" '
        'onclick="(function(){var b=window.parent.document.querySelector(\'.ai-chat-box\');'
        'if(b){b.scrollTop=b.scrollHeight;}})()"'
        ' title="回到底部">&#9660;</button></div>'
    )


def scroll_inline_button(direction="down", label=None):
    """内嵌行内按钮 HTML（用于 header/工具栏）。"""
    arrow = "&#9650;" if direction == "up" else "&#9660;"
    txt = label or arrow
    title = "\u56de\u5230\u9876\u90e8" if direction == "up" else "\u56de\u5230\u5e95\u90e8"
    target = "0" if direction == "up" else "document.body.scrollHeight"
    return (
        '<button class="sf-scroll-inline"'
        ' onclick="event.preventDefault();window.scrollTo({top:'
        + target + ',behavior:\\"smooth\\"})"'
        ' title="' + title + '">' + txt + "</button>"
    )


def chat_bottom_anchor():
    """消息流底部锚点元素（辅助定位）。"""
    return '<div id="sf-chat-end" style="height:1px"></div>'


if __name__ == "__main__":
    print("scroll_nav v2 OK")
