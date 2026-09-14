"""
回到顶部 / 回到底部 · Streamlit 导航组件库 v3
================================================
精准复刻 WorkBuddy 对话界面的 ▼ 回到底部按钮 + 站内统一 ▲ 回到顶部悬浮按钮。

【v3 重设计 · ▲ 回到顶部】（2026-09-13）
  需求：①不能放在页面底部；②用户第一次下滑即出现在**页面右下角**（之前不出现）；
       ③出现后位置固定不变；④任何滚动位置点击都能真正回到顶部；⑤圆形按钮。

  实现要点：
  · 位置：`right:24px; bottom:28px`（右下角，固定不动）。v2 曾用 `top:50%`（右侧中部），已废弃。
  · 触发：滚动容器 scrollTop > threshold（默认 120px，约「第一次下滑」）即 fade-in；
         回滚到阈值以下自动隐藏；出现后位置恒定，不随内容高度变化。
  · 圆形：`border-radius:50%` + 36px 正方形 + 居中 flex。
  · 主题：亮色=白底+边框+深色箭头；暗色=深底+浅箭头（由 inject_scroll_nav(dark=) 决定）。

【★ 关键缺陷修复：滚动目标容器】
  v2 的 onclick 执行 `window.parent.scrollTo({top:0})` —— 但 **Streamlit 的主内容区
  并不是 window 的滚动**，而是内部可滚动元素（`[data-testid="stAppViewContainer"]`
  / `.stMain` / `.block-container` 等，随版本漂移）。故 window.scrollTo 无任何效果，
  用户看到「按钮形态变化但页面不动」。
  修复：`_scroll_container_js()` 生成「按优先级探测多个候选容器 → 取实际可滚动者 →
  scrollTo({top:0})」的 JS，并对 window 兜底。滚动监听同样挂在探测到的容器上。

【Streamlit 适配要点】
  components.html 运行在 sandbox iframe 内，故按钮须创建在 window.parent.document
  才能成为「视口级」悬浮元素；滚动监听也挂在父窗口的滚动容器上。
  幂等：以根节点 id 存在性判定，rerun 不会重复创建；容器引用每帧重新探测（懒绑定），
  以容忍 Streamlit rerun 后 DOM 被替换。

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

# ── v3 回到顶部按钮默认显隐阈值（px）────────────────────────────────────────
# 用户要求「第一次下滑就出现」：取 120px（约一次滚动/半屏内）而非 v2 的 300px。
DEFAULT_TOP_THRESHOLD = 120

# 主内容区滚动容器的候选选择器（按优先级）。Streamlit 版本间会漂移，
# 故提供多候选 + 运行期探测「实际可滚动」的那个；找不到时兜底 window。
_SCROLL_SELECTORS = (
    '[data-testid="stAppViewContainer"]',
    '[data-testid="stMain"]',
    '.stMain',
    'section.main',
    '.main',
    '.block-container',
    '[data-testid="stMainBlockContainer"]',
)

SCROLL_NAV_CSS = """
<style>
/* ══════════ ▲ 回到顶部 —— 页面右下角固定圆形悬浮按钮 ══════════
   位置：right:24px / bottom:28px（右下角，与侧栏「市场异动」铃铛错开）
   v2 曾把按钮固定在页面右侧中部（垂直居中）→ 已于 v3 改为右下角，且出现后位置恒定。 */
.sf-scroll-top{
  position:fixed;right:24px;bottom:28px;top:auto;transform:none;z-index:900;
  width:40px;height:40px;border-radius:50%;
  display:none;align-items:center;justify-content:center;
  padding:0;margin:0;line-height:1;
  font-size:16px;font-weight:600;
  background:#ffffff;color:#374151;
  border:1px solid #e2e8f0;cursor:pointer;
  box-shadow:0 4px 14px rgba(15,23,42,.14),0 1px 3px rgba(15,23,42,.08);
  transition:opacity .22s ease,transform .22s ease,box-shadow .22s ease,background .18s ease;
  opacity:0;pointer-events:none;
}
.sf-scroll-top svg{width:20px;height:20px;display:block}
.sf-scroll-top:hover{
  background:#f8fafc;color:#111827;transform:translateY(-2px);
  box-shadow:0 8px 22px rgba(15,23,42,.2),0 2px 6px rgba(15,23,42,.1);
}
.sf-scroll-top:active{transform:translateY(0) scale(.96)}
.sf-scroll-top:focus-visible{outline:2px solid var(--acc1,#4f46e5);outline-offset:2px}

/* 暗色主题：深底 + 浅箭头 */
.sf-scroll-top.dark{
  background:#1e1e32;color:#cbd5e1;border-color:#2d2d44;
  box-shadow:0 4px 16px rgba(0,0,0,.45),0 1px 3px rgba(0,0,0,.3);
}
.sf-scroll-top.dark:hover{
  background:#2a2a45;color:#f1f5f9;
  box-shadow:0 8px 24px rgba(0,0,0,.55),0 2px 6px rgba(0,0,0,.35);
}

/* 显示态：fade-in + 轻微上浮，出现后不再位移（位置恒定） */
.sf-scroll-top.visible{display:flex;opacity:1;pointer-events:auto;animation:sfFadeInUp .26s ease}
@keyframes sfFadeInUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* ══════════ ▼ 回到底部（WorkBuddy 原版）—— 消息流右下角、输入栏上方 ══════════ */
.sf-scroll-bottom-float{
  position:fixed;right:24px;bottom:110px;z-index:900;
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

/* ══════════ 弹层内嵌版 ▼（星辰 AI 右上角 popover 用，居中于输入栏上方）══════════ */
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

/* ══════════ 页内行内按钮（历史 API 兼容）══════════ */
.sf-scroll-inline{
  display:inline-flex;align-items:center;gap:6px;
  padding:.35rem .8rem;border-radius:999px;cursor:pointer;
  background:#f0f0f5;color:#374151;border:1px solid #e2e8f0;
  font-size:.85rem;transition:all .18s ease;
}
.sf-scroll-inline:hover{background:#e0e0e8}

/* ══════════ 响应式：窄屏收窄边距与尺寸 ══════════ */
@media(max-width:768px){
  .sf-scroll-top{right:14px;bottom:20px;width:38px;height:38px}
  .sf-scroll-top svg{width:18px;height:18px}
  .sf-scroll-bottom-float{right:14px;bottom:90px;width:31px;height:31px;font-size:13px}
}
</style>
"""

# ▲ 图标：内联 SVG（无外部依赖、随 currentColor 变色）
_TOP_ICON_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M12 19V6"/><path d="M6 12l6-6 6 6"/></svg>'
)


def _scroll_container_js(var_name: str = "C") -> str:
    """生成「探测 Streamlit 真实滚动容器」的 JS 片段（返回一段声明语句）。

    关键修复：v2 直接 `window.scrollTo` 无效——Streamlit 主内容区滚动发生在内部
    可滚动元素上。本片段按优先级遍历候选选择器，取「scrollHeight 明显大于
    clientHeight」的第一个元素作为滚动容器；全部落空时兜底 window。

    运行期每帧重新探测（调用方以闭包持有 getter），以容忍 rerun 后 DOM 被替换。
    """
    sels = json.dumps(list(_SCROLL_SELECTORS))
    return (
        f"var {var_name}_sels = {sels};\n"
        f"function {var_name}_get(){{\n"
        f"  try{{\n"
        f"    for (var i=0;i<{var_name}_sels.length;i++){{\n"
        f"      var el = P.document.querySelector({var_name}_sels[i]);\n"
        f"      if (el && el.scrollHeight > el.clientHeight + 4) return el;\n"
        f"    }}\n"
        f"    for (var j=0;j<{var_name}_sels.length;j++){{\n"
        f"      var el2 = P.document.querySelector({var_name}_sels[j]);\n"
        f"      if (el2) return el2;\n"
        f"    }}\n"
        f"  }}catch(e){{}}\n"
        f"  return null;\n"
        f"}}\n"
        f"function {var_name}_top(){{\n"
        f"  var el = {var_name}_get();\n"
        f"  try{{ if (el) {{ el.scrollTo({{top:0, behavior:'smooth'}}); return; }} }}catch(e){{}}\n"
        f"  try{{ P.scrollTo({{top:0, behavior:'smooth'}}); }}catch(e){{}}\n"
        f"  try{{ P.document.documentElement.scrollTop = 0; }}catch(e){{}}\n"
        f"}}\n"
        f"function {var_name}_pos(){{\n"
        f"  var el = {var_name}_get();\n"
        f"  try{{ if (el) return el.scrollTop || 0; }}catch(e){{}}\n"
        f"  return (P.scrollY || P.pageYOffset || 0);\n"
        f"}}\n"
    )


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
    top_cls = 'sf-scroll-top' + (' dark' if dark else '')
    show_top_js = 'true' if show_top else 'false'
    show_bottom_js = 'true' if show_bottom else 'false'

    _icon = _TOP_ICON_SVG.replace("\\", "\\\\").replace("'", "\\'")

    body = """
<script>
(function(){
  var P = window.parent || window;
  if (!P || !P.document) return;
  try {
    /* ── 滚动容器探测（v3 修复：Streamlit 主内容区不是 window 的滚动）── */
    __SCROLL_CONTAINER_JS__

    // ▲ 回到顶部（v3：右下角圆形 · 首次下滑即现 · 位置固定 · 真正滚对容器）
    if (__SHOW_TOP__) {
      var tbtn = P.document.getElementById('sfScrollTopBtn');
      if (!tbtn) {
        tbtn = P.document.createElement('button');
        tbtn.id = 'sfScrollTopBtn';
        tbtn.type = 'button';
        tbtn.className = '__TOPCLS__';
        tbtn.innerHTML = '__TOPICON__';
        tbtn.title = '\u56de\u5230\u9876\u90e8';
        tbtn.setAttribute('aria-label', '\u56de\u5230\u9876\u90e8');
        tbtn.onclick = function(ev){ if(ev && ev.preventDefault) ev.preventDefault(); C_top(); };
        P.document.body.appendChild(tbtn);
      } else {
        tbtn.className = '__TOPCLS__';
      }
      var tupdate = function(){
        var y = C_pos();
        if (y > __THRESH__) tbtn.classList.add('visible');
        else tbtn.classList.remove('visible');
      };
      // 绑定：window + 所有候选容器（含懒绑定的实际滚动元素），确保任一滚动都被感知
      var __bound = [];
      function bindScrollTargets(){
        var cands = [];
        try { cands.push(P); } catch(e){}
        try { for (var i=0;i<C_sels.length;i++){ var e=P.document.querySelector(C_sels[i]); if(e) cands.push(e); } } catch(e){}
        for (var k=0;k<cands.length;k++){
          if (!cands[k] || __bound.indexOf(cands[k]) >= 0) continue;
          try { cands[k].addEventListener('scroll', tupdate, {passive:true}); __bound.push(cands[k]); } catch(e){}
        }
      }
      bindScrollTargets();
      setTimeout(function(){ bindScrollTargets(); tupdate(); }, 120);
      setTimeout(function(){ bindScrollTargets(); tupdate(); }, 600);
      if (P.__sfScrollNavObserver) { try { P.__sfScrollNavObserver.disconnect(); } catch(e){} }
      P.__sfScrollNavObserver = new MutationObserver(function(){ bindScrollTargets(); setTimeout(tupdate, 60); });
      P.__sfScrollNavObserver.observe(P.document.body, {childList:true, subtree:true});
    }
    // ▼ 回到底部（由页面标记元素 __BOTTOM_MARKER_SEL__ 的存在性驱动）
    // 说明：Streamlit 1.58 为客户端路由，window.location.pathname 恒为 "/"，
    // 无法用 URL 区分页面；故由星辰 AI 对话页用 st.markdown 渲染一个隐藏标记元素，
    // 本脚本监听该标记出现即创建 ▼、消失即移除，确保 ▼ 仅在该页出现。
    // （本脚本位于每页唯一可靠执行的首次 components.html 注入中，无需二次调用。）
    if (__SHOW_BOTTOM__ && __BOTTOM_MARKER_JS__ !== '') {
      var bbtn = null;
      function createBottomBtn(){
        var broot = P.document.getElementById('sfChatBottomRoot');
        if (broot) { bbtn = P.document.getElementById('sfChatBottomBtn'); if (bbtn) bbtn.className = '__CLS__'; }
        else {
          broot = P.document.createElement('div'); broot.id = 'sfChatBottomRoot';
          bbtn = P.document.createElement('button'); bbtn.id = 'sfChatBottomBtn'; bbtn.className = '__CLS__'; bbtn.__xcAuto = true;
          bbtn.innerHTML = '\u25bc'; bbtn.title = '\u56de\u5230\u5e95\u90e8';
          bbtn.onclick = function(){ var el=C_get(); if(el){ try{el.scrollTo({top:el.scrollHeight,behavior:'smooth'});}catch(e){} } try{ P.scrollTo({top: P.document.body.scrollHeight, behavior:'smooth'}); }catch(e){} };
          broot.appendChild(bbtn); P.document.body.appendChild(broot);
        }
      }
      function bupdate(){
        if (!bbtn) return;
        var el = C_get();
        var sy = el ? (el.scrollTop||0) : (P.scrollY||P.pageYOffset||0);
        var dh = el ? el.scrollHeight : P.document.documentElement.scrollHeight;
        var wh = el ? el.clientHeight : P.innerHeight;
        var distBottom = dh-(sy+wh);
        if (distBottom > __BTH__) bbtn.classList.add('visible'); else bbtn.classList.remove('visible');
      }
      function syncBottom(){
        var m = P.document.querySelector('[data-testid="__BOTTOM_MARKER_SEL__"]');
        var cur = P.document.getElementById('sfChatBottomBtn');
        if (m && !cur) { createBottomBtn(); bupdate(); }
        else if (!m && cur && cur.__xcAuto) { if (cur.parentElement) cur.parentElement.remove(); }
      }
      syncBottom();
      P.addEventListener('scroll', bupdate, {passive:true});
      setTimeout(function(){ syncBottom(); bupdate(); }, 200);
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
    /* ── ⌘K / Ctrl+K 聚焦侧栏搜索（命令面板）── */
    P.document.addEventListener('keydown', function(e){
      var kk = (e.key || '').toLowerCase();
      if ((e.metaKey || e.ctrlKey) && kk === 'k') {
        e.preventDefault();
        try {
          var sb = P.document.querySelector('[data-testid="stSidebar"]');
          if (sb) { var inp = sb.querySelector('input'); if (inp) { inp.focus(); } }
        } catch(_e){}
      }
    }, true);
  } catch(e) {}
})();
</script>
"""
    marker_js = json.dumps(bottom_marker or '')
    marker_sel = (bottom_marker or '').replace('"', '\\"')
    _container_js = _scroll_container_js('C')
    body = (body
            .replace('__SCROLL_CONTAINER_JS__', _container_js)
            .replace('__TOPICON__', _icon)
            .replace('__TOPCLS__', top_cls)
            .replace('__SHOW_TOP__', show_top_js)
            .replace('__SHOW_BOTTOM__', show_bottom_js)
            .replace('__THRESH__', str(threshold_px))
            .replace('__BTH__', str(bottom_threshold))
            .replace('__CLS__', cls)
            .replace('__BOTTOM_MARKER_JS__', marker_js)
            .replace('__BOTTOM_MARKER_SEL__', marker_sel))
    return body


def inject_scroll_nav(show_top: bool = True, show_bottom: bool = False,
                      threshold_px: int = DEFAULT_TOP_THRESHOLD, bottom_threshold: int = 150,
                      dark: bool = False, bottom_marker: str = ''):
    """注入 CSS + 悬浮导航按钮 JS + C 键清缓存拦截。每个页面顶部调一次（幂等）。

    参数：
      show_top         -- 启用 ▲ 回到顶部（默认全局启用）
      show_bottom      -- 显式启用 ▼ 回到底部（须配合 bottom_marker 指定页面标记；两者皆满足才创建）
      threshold_px     -- ▲ 显隐阈值：向下滚超此值显现（v3 默认 120，实现「首次下滑即现」）
      bottom_threshold -- ▼ 显隐阈值：距底大于此值才显现
      dark             -- 是否暗色（影响 ▲/▼ 配色）
      bottom_marker    -- 非空时，顶层文档存在该 testid 标记元素即启用 ▼（用于星辰 AI 对话页）

    实现：CSS + JS 合并为**一次** components.html 注入。
    关键约束（见模块 docstring）：Streamlit 对 st.markdown 内的 <script> 会过滤、
    且多次 components.html 仅首次可靠执行；故必须合并单次注入。
    """
    payload = SCROLL_NAV_CSS + "\n" + _nav_script(
        dark, threshold_px, bottom_threshold, show_top, show_bottom, bottom_marker)
    try:
        components.html(payload, height=0)
    except Exception as e:  # bare mode / 无 ScriptRunContext 时降级为 markdown，避免抛错
        logger.warning(f'[scroll_nav] 注入异常，降级 markdown: {e}')
        st.markdown(payload, unsafe_allow_html=True)


def _back_to_top_inline_js() -> str:
    """生成「页内按钮点击回到顶部」的内联 JS（同样修复为探测真实滚动容器）。

    因为内联 onclick 无法复用 IIFE 内的闭包，这里输出一段自包含的表达式。
    """
    sels = json.dumps(list(_SCROLL_SELECTORS))
    return (
        "(function(){"
        "var P=window.parent||window;var s=" + sels + ";"
        "try{for(var i=0;i<s.length;i++){var el=P.document.querySelector(s[i]);"
        "if(el&&el.scrollHeight>el.clientHeight+4){el.scrollTo({top:0,behavior:'smooth'});return;}}}catch(e){}"
        "try{for(var j=0;j<s.length;j++){var e2=P.document.querySelector(s[j]);"
        "if(e2){e2.scrollTo({top:0,behavior:'smooth'});return;}}}catch(e){}"
        "try{P.scrollTo({top:0,behavior:'smooth'});}catch(e){}"
        "try{P.document.documentElement.scrollTop=0;}catch(e){}"
        "})()"
    )


def scroll_bottom_inline_html(dark: bool = False) -> str:
    """弹层（星辰 AI popover）内嵌 ▼ 按钮 HTML（居中于输入栏上方，点击滚动聊天框到底）。"""
    cls = 'sf-scroll-bottom-inline' + (' dark' if dark else '')
    onclick = ("(function(){var b=window.parent.document.querySelector('.ai-chat-box');"
               "if(b){b.scrollTop=b.scrollHeight;}})()")
    return (f'<div style="display:flex;justify-content:center;margin:10px 0 6px">'
            f'<button class="{cls}" onclick="{onclick}" title="回到底部">&#9660;</button></div>')


def scroll_inline_button(direction='down', label=None):
    """内嵌行内按钮 HTML（用于 header/工具栏）。v3：滚动目标改为真实容器。"""
    arrow = '&#9650;' if direction == 'up' else '&#9660;'
    txt = label or arrow
    title = '回到顶部' if direction == 'up' else '回到底部'
    if direction == 'up':
        onclick = _back_to_top_inline_js()
    else:
        sels = json.dumps(list(_SCROLL_SELECTORS))
        onclick = ("(function(){var P=window.parent||window;var s=" + sels + ";"
                   "try{for(var i=0;i<s.length;i++){var el=P.document.querySelector(s[i]);"
                   "if(el){el.scrollTo({top:el.scrollHeight,behavior:'smooth'});return;}}}catch(e){}"
                   "try{P.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});}catch(e){}})()")
    return (f'<button class="sf-scroll-inline" type="button" '
            f'onclick="event.preventDefault();{onclick}" title="{title}">{txt}</button>')


def chat_bottom_anchor():
    """消息流底部锚点元素（辅助定位）。"""
    return '<div id="sf-chat-end" style="height:1px"></div>'


def back_to_top_button(label: str = "↑ 回到顶部", use_container_width: bool = True) -> None:
    """渲染一个【真实可点击】的「回到顶部」按钮（页内位置，非悬浮）。

    关键：原先各页用 ``st.markdown("<script>window.scrollTo(...)</script>")``，
    Streamlit 会过滤 markdown 内的 <script> 标签，导致按钮【点击无反应】。
    本函数改用 components.html 注入真实 <button>。

    v3 修复（2026-09-13）：滚动目标从 ``window.scrollTo`` 改为「探测 Streamlit 真实
    滚动容器 → 回退 window」，与悬浮 ▲ 走同一套逻辑——否则点击后页面不动。

    ⚠️ 新设计建议：全局悬浮 ▲ 已由 inject_scroll_nav 注入（右下角、首次下滑即现），
    页面底部**无需**再放一个页内按钮。保留本函数仅为兼容既有页面；
    新页面请勿新增调用（避免与悬浮按钮功能重复）。若仍需要，请使用
    ``modules.scroll_nav.embedded_back_to_top()``（渲染为次要样式）。
    """
    width = "width:100%;" if use_container_width else "width:auto;"
    btn = (
        f'<button id="sfBackToTopBtn" type="button" '
        f'onclick="event.preventDefault();{_back_to_top_inline_js()}" '
        f'style="{width}padding:0.45rem 1rem;border:1px solid #e2e8f0;border-radius:999px;cursor:pointer;'
        f'background:transparent;color:#64748b;font-size:0.9rem;'
        f'transition:all .18s ease">'
        f'{label}</button>'
    )
    try:
        components.html(btn, height=44)
    except Exception as e:
        logger.warning(f'[scroll_nav] back_to_top_button 注入异常: {e}')
        st.button(label, on_click=lambda: None, width=("stretch" if use_container_width else "content"))


if __name__ == '__main__':
    logger.info('scroll_nav v3 OK')
