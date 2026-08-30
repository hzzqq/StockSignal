"""modules/_widgets_ai.py
星辰 · 多市场智能股票分析师：AI 顾问对话组件（从 widgets.py 拆出）。
"""
from __future__ import annotations
from __future__ import annotations
from typing import Any, Dict
from datetime import datetime
import html
import time
import requests
import streamlit as st
import streamlit.components.v1 as components
from modules.session import API_BASE, get_token, safe_switch_page, persist_prefs, is_admin, _rel_time
import json
import logging
from modules.ui_kit import xc_handle_error
logger = logging.getLogger(__name__)
import re
from modules._widgets_base import STAR_AI_LOGO

def _slim_context() -> Dict[str, Any]:
    """把当前页面上下文精简，只传 AI 需要的汇总字段，避免序列化 DataFrame。"""
    rows = st.session_state.get('_cmp_rows')
    slim_rows = None
    if rows:
        slim_rows = []
        for r in rows:
            slim_rows.append({'code': r.get('code'), 'name': r.get('name'), 'signal': r.get('signal'), 'scores': r.get('scores'), 'industry': r.get('industry'), 'market_cap': r.get('market_cap'), 'pe_ttm': r.get('pe_ttm'), 'elasticity': r.get('elasticity'), 'business_corr': r.get('business_corr')})
    analysis = st.session_state.get('analysis_result')
    slim_analysis = None
    if analysis and isinstance(analysis, dict):
        slim_analysis = {k: v for k, v in analysis.items() if k != 'df'}
    return {'_cmp_rows': slim_rows, 'analysis_result': slim_analysis}

def _current_stock_context():
    """从个股分析页的 session 结果中提取当前股票上下文。"""
    ar = st.session_state.get('analysis_result')
    if isinstance(ar, dict):
        name = ar.get('name') or ar.get('stock_name') or ar.get('code')
        verdict = ar.get('verdict') or ar.get('signal')
        score = ar.get('score') or ar.get('composite') or ar.get('score_composite')
        if name:
            return (str(name), verdict, score)
    return (None, None, None)

def _ai_popover_theme_css() -> str:
    """Popover 内部主题适配：强制暗色下输入框/按钮/气泡可读。

    关键：Streamlit 中 st.markdown 包裹的 div 与后续 widget 是「兄弟节点」而非嵌套，
    故交互控件（textarea / button）的样式必须作用到 [data-testid="stPopoverBody"]
    才能命中（弹层内所有控件都是它的后代）；而对话气泡由单个 st.markdown 一次性输出、
    内部已正确嵌套，故 .ai-chat-box .ai-msg 可命中。
    """
    from modules.ui_theme import _theme_is_dark
    if _theme_is_dark():
        return '\n        <style>\n        /* Popover 弹层本体：暗夜深底 */\n        [data-testid="stPopoverBody"] { background:#1a1a2e !important; border-color:#2d2d44 !important; }\n        .ai-consult-wrap { color:#e2e8f0; }\n        .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#e2e8f0 !important; }\n        /* 输入框：常态/hover/focus/active 强制黑底（作用到弹层 body 才命中） */\n        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea,\n        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:hover,\n        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:focus,\n        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:active,\n        [data-testid="stPopoverBody"] textarea {\n            background:#15152a !important; color:#e2e8f0 !important;\n            border:1px solid #2d2d44 !important; box-shadow:none !important;\n            caret-color:#e2e8f0 !important;\n        }\n        [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea::placeholder { color:#64748b !important; }\n        [data-testid="stPopoverBody"] [data-testid="stTextArea"] > div { background:transparent !important; border:none !important; }\n        [data-testid="stPopoverBody"] [data-testid="stTextArea"] { background:#15152a !important; border:1px solid #2d2d44 !important; border-radius:10px !important; }\n        /* 发送/清空按钮：常态/hover/focus/active 深紫底+深字 */\n        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button,\n        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:hover,\n        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:focus,\n        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:active,\n        [data-testid="stPopoverBody"] .stButton button,\n        [data-testid="stPopoverBody"] .stButton button:hover,\n        [data-testid="stPopoverBody"] .stButton button:focus,\n        [data-testid="stPopoverBody"] .stButton button:active {\n            background:linear-gradient(180deg,#667eea,#764ba2) !important; color:#0f0f23 !important;\n            border:none !important; box-shadow:none !important; font-weight:600 !important;\n        }\n        [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:disabled,\n        [data-testid="stPopoverBody"] .stButton button:disabled { opacity:.55 !important; }\n        /* 对话气泡（单个 st.markdown 块内已正确嵌套，.ai-chat-box .ai-msg 可命中） */\n        .ai-chat-box { max-height:360px; overflow-y:auto; padding:8px 2px; display:flex; flex-direction:column; gap:10px; }\n        .ai-chat-box .ai-msg { max-width:92%; padding:8px 12px; border-radius:14px; font-size:13px; line-height:1.6; word-break:break-word; box-shadow:0 1px 4px rgba(0,0,0,.25); }\n        .ai-chat-box .ai-msg p { color:inherit !important; margin:4px 0; }\n        .ai-chat-box .ai-msg ul, .ai-chat-box .ai-msg ol { margin:4px 0; padding-left:18px; }\n        .ai-chat-box .ai-msg li { margin:2px 0; }\n        /* 用户消息：右侧带边框方框，深灰底（明确区分用户问题 / AI 回答） */\n        .ai-chat-box .ai-msg.user { align-self:flex-end; background:#252542; color:#e2e8f0; border:1px solid #4b4b7a; border-bottom-right-radius:4px; }\n        .ai-chat-box .ai-msg.assistant { align-self:flex-start; background:#15152a; color:#e2e8f0; border:1px solid #2d2d44; border-bottom-left-radius:4px; }\n        .ai-chat-box .ai-role { font-size:10px; opacity:.65; margin-bottom:2px; }\n        .ai-chat-box .ai-msg.user .ai-role { text-align:right; color:#94a3b8; }\n        .ai-typing { align-self:flex-start; font-size:12px; color:#94a3b8; padding:4px 2px; }\n        /* 回到底部按钮改为弹层内嵌 .sf-scroll-bottom-inline（见 modules/scroll_nav.py） */\n        </style>\n        '
    return '\n    <style>\n    [data-testid="stPopoverBody"] { background:#ffffff !important; border-color:#e2e8f0 !important; }\n    .ai-consult-wrap { color:#111827; }\n    .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#111827 !important; }\n    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea,\n    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:hover,\n    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:focus,\n    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea:active,\n    [data-testid="stPopoverBody"] textarea {\n        background:#ffffff !important; color:#111827 !important;\n        border:1px solid #d1d5db !important; box-shadow:none !important;\n        caret-color:#111827 !important;\n    }\n    [data-testid="stPopoverBody"] [data-testid="stTextArea"] textarea::placeholder { color:#9ca3af !important; }\n    [data-testid="stPopoverBody"] [data-testid="stTextArea"] > div { background:transparent !important; border:none !important; }\n    [data-testid="stPopoverBody"] [data-testid="stTextArea"] { background:#ffffff !important; border:1px solid #d1d5db !important; border-radius:10px !important; }\n    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button,\n    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:hover,\n    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:focus,\n    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:active,\n    [data-testid="stPopoverBody"] .stButton button,\n    [data-testid="stPopoverBody"] .stButton button:hover,\n    [data-testid="stPopoverBody"] .stButton button:focus,\n    [data-testid="stPopoverBody"] .stButton button:active {\n        background:linear-gradient(180deg,#D4A02A,#B8860B) !important; color:#111827 !important;\n        border:none !important; box-shadow:none !important; font-weight:600 !important;\n    }\n    [data-testid="stPopoverBody"] [data-testid="stFormSubmitButton"] button:disabled,\n    [data-testid="stPopoverBody"] .stButton button:disabled { opacity:.55 !important; }\n    .ai-chat-box { max-height:360px; overflow-y:auto; padding:8px 2px; display:flex; flex-direction:column; gap:10px; }\n    .ai-chat-box .ai-msg { max-width:92%; padding:8px 12px; border-radius:14px; font-size:13px; line-height:1.6; word-break:break-word; box-shadow:0 1px 3px rgba(0,0,0,.06); }\n    .ai-chat-box .ai-msg p { color:inherit !important; margin:4px 0; }\n    .ai-chat-box .ai-msg ul, .ai-chat-box .ai-msg ol { margin:4px 0; padding-left:18px; }\n    .ai-chat-box .ai-msg li { margin:2px 0; }\n    .ai-chat-box .ai-msg.user { align-self:flex-end; background:#fff7e6; color:#111827; border:1px solid #ffd591; border-bottom-right-radius:4px; }\n    .ai-chat-box .ai-msg.assistant { align-self:flex-start; background:#f4f6fb; color:#111827; border:1px solid #e2e8f0; border-bottom-left-radius:4px; }\n    .ai-chat-box .ai-role { font-size:10px; opacity:.55; margin-bottom:2px; }\n    .ai-chat-box .ai-msg.user .ai-role { text-align:right; color:#6b7280; }\n    .ai-typing { align-self:flex-start; font-size:12px; color:#6b7280; padding:4px 2px; }\n    /* 回到底部按钮改为弹层内嵌 .sf-scroll-bottom-inline（见 modules/scroll_nav.py） */\n    </style>\n    '

def _chat_history_for_context(max_turns: int=6) -> list:
    """取最近若干轮对话，给 AI 引擎做「可持续追问」的上下文。"""
    chat = st.session_state.get('ai_chat') or []
    return chat[-max_turns:]

def _ai_md(text: str) -> str:
    """极简 markdown → HTML：转义后支持 **粗体** / *斜体* / 换行 / 无序列表。"""
    import html as _h
    import re as _re
    t = _h.escape(str(text), quote=False)
    t = _re.sub('\\*\\*(.+?)\\*\\*', '<b>\\1</b>', t)
    t = _re.sub('\\*(.+?)\\*', '<i>\\1</i>', t)
    t = _re.sub('(?m)^- (.*?)(?=<br>|$)', '• \\1', t)
    t = t.replace('\n', '<br>')
    return t

def _render_ai_chat() -> None:
    """渲染对话气泡（用户右、助手左），一次性输出保证 .ai-chat-box .ai-msg 正确嵌套命中。"""
    chat = st.session_state.get('ai_chat') or []
    parts = ['<div class="ai-chat-box">']
    for msg in chat:
        role = msg.get('role')
        content = msg.get('content', '')
        if role == 'user':
            parts.append(f'<div class="ai-msg user"><div class="ai-role">你</div>{_ai_md(content)}</div>')
        else:
            parts.append(f'<div class="ai-msg assistant"><div class="ai-role">★ 星辰 AI</div>{_ai_md(content)}</div>')
    if st.session_state.get('ai_task_id'):
        parts.append('<div class="ai-typing">🤔 AI 正在思考…</div>')
    parts.append('</div>')
    st.markdown('\n'.join(parts), unsafe_allow_html=True)

def _ai_scroll_to_bottom_component(dark: bool) -> None:
    """在 popover 内渲染一个「滚动到底部」按钮，并自动把对话区域滚到底。"""
    bg = '#667eea' if dark else '#D4A02A'
    color = '#ffffff' if dark else '#111827'
    hover_bg = '#764ba2' if dark else '#B8860B'
    js = f"""\n    <div id="ai-scroll-bottom-btn" style="width:100%;display:flex;justify-content:center;padding:6px 0;cursor:pointer;"\n         onclick="scrollAIChatToBottom()">\n      <div style="width:34px;height:34px;border-radius:50%;background:{bg};color:{color};display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 6px rgba(0,0,0,.25);" onmouseover="this.style.background='{hover_bg}'" onmouseout="this.style.background='{bg}'">▼</div>\n    </div>\n    <script>\n      function scrollAIChatToBottom() {{\n        var doc = window.parent.document;\n        var box = doc.querySelector('.ai-chat-box');\n        if (box) box.scrollTop = box.scrollHeight;\n      }}\n      setTimeout(scrollAIChatToBottom, 60);\n      setTimeout(scrollAIChatToBottom, 300);\n    </script>\n    """
    st.markdown(js, unsafe_allow_html=True)

@st.fragment
def _poll_ai_consult_task() -> None:
    """轮询全局 AI 咨询后台任务（#405）。

    只让本片段随 st_autorefresh 每 5s 局部重跑；任务终态（成功/失败/超时）才用
    st.rerun(scope="app") 升级为一次整页重跑，以在页面级重渲染聊天历史。
    这是 fragment 铁律允许的唯一整页重跑时机——等待期间绝不整页刷新。
    """
    task_id = st.session_state.get('ai_task_id')
    if not task_id:
        return
    task = poll_task(task_id, max_wait=0.4)
    if task and task.get('status') == 'success':
        result = task.get('result') or {}
        answer = result.get('answer') or 'AI 暂未给出回答'
        st.session_state['ai_chat'].append({'role': 'assistant', 'content': answer})
        st.session_state['ai_task_id'] = None
        st.session_state['ai_task_started_at'] = None
        st.rerun(scope='app')
        return
    if task and task.get('status') == 'error':
        err = task.get('error') or '未知错误'
        st.session_state['ai_chat'].append({'role': 'assistant', 'content': f'❌ AI 分析失败：{err}'})
        st.session_state['ai_task_id'] = None
        st.session_state['ai_task_started_at'] = None
        st.rerun(scope='app')
        return
    started = st.session_state.get('ai_task_started_at') or time.time()
    if time.time() - started > 240:
        st.session_state['ai_chat'].append({'role': 'assistant', 'content': '❌ AI 响应超时，请重新提问。'})
        st.session_state['ai_task_id'] = None
        st.session_state['ai_task_started_at'] = None
        st.rerun(scope='app')
        return
    try:
        from modules.autorefresh import st_autorefresh
        st_autorefresh(interval=5000, limit=150, key='ai_chat_autorefresh')
    except Exception as e:
        logger.warning(f"[_widgets_ai] 处理异常: {e}")
        pass

def render_ai_consultant() -> None:
    """全局 AI 咨询模块（右上角弹层内）：任意页面可用，后台异步运行，对话可持续。

    设计目标（用户反馈）：
      - 结果必须「真正返回」，不再卡在后台不显示 → 用 streamlit_autorefresh 轮询，
        后台任务完成后自动把 AI 回复追加进对话流。
      - 对话做成「可持续」的，像聊天一样保留历史、可连续追问 → 历史存
        session_state["ai_chat"]，提交时把上下文 + 历史一起交给 AI 引擎。
      - 加载只在 AI 小框内感知，不污染页面主体 → 错误/状态全部放在 popover 内；
        autorefresh 只在任务运行且未超时前触发，并降低频率。
      - 聊天界面清晰区分用户/AI，清空按钮在标题右侧，可一键滚到底部输入框。

    防重入：同一脚本 run 内若被多次调用（如 except 误捕 fallback），跳过后续渲染，
    避免 st.form("ai_consult_global") 重复创建导致 StreamlitAPIException。
    用函数属性（每次脚本 run 模块重新加载，自动重置）。
    """
    if getattr(render_ai_consultant, '_called_this_run', False):
        return
    render_ai_consultant._called_this_run = True
    from modules.ui_theme import _theme_is_dark
    from modules.scroll_nav import scroll_bottom_inline_html
    dark = _theme_is_dark()
    st.markdown(_ai_popover_theme_css(), unsafe_allow_html=True)
    st.markdown('<div class="ai-consult-wrap">', unsafe_allow_html=True)
    if 'ai_chat' not in st.session_state:
        st.session_state['ai_chat'] = []
    if 'ai_task_id' not in st.session_state:
        st.session_state['ai_task_id'] = None
    if 'ai_task_started_at' not in st.session_state:
        st.session_state['ai_task_started_at'] = None
    head_col1, head_col2 = st.columns([5, 1])
    with head_col1:
        st.markdown(f'#### {STAR_AI_LOGO(20)} 星辰 · 多市场智能股票分析师', unsafe_allow_html=True)
    with head_col2:
        if st.session_state['ai_chat']:
            if st.button('🗑️', key='ai_clear_chat', help='清空对话'):
                st.session_state['ai_chat'] = []
                st.session_state['ai_task_id'] = None
                st.session_state['ai_task_started_at'] = None
                st.rerun()
    rows = st.session_state.get('_cmp_rows')
    name, verdict, score = _current_stock_context()
    if rows:
        st.caption(f'📊 当前对比 {len(rows)} 只标的，AI 会优先回答你提到的股票。')
    elif name:
        st.caption(f'🎯 当前个股：{name}，你直接问其他股票我也会独立分析。')
    else:
        st.caption('输入股票代码或名称，AI 会独立拉取数据并给出研判。')
    _render_ai_chat()
    st.markdown(scroll_bottom_inline_html(dark=dark), unsafe_allow_html=True)
    busy = bool(st.session_state.get('ai_task_id'))
    with st.form('ai_consult_global', clear_on_submit=True):
        q = st.text_area('AI 咨询', placeholder='例如：深科技怎么样？ / 这组合里谁最值得买？风险在哪？', height=80, label_visibility='collapsed', key='ai_consult_q', disabled=busy)
        submitted = st.form_submit_button('🚀 发送' if not busy else '⏳ AI 思考中…', use_container_width=True, disabled=busy)
    if submitted and q and (not busy):
        st.session_state['ai_chat'].append({'role': 'user', 'content': q})
        ctx = _slim_context()
        ctx['history'] = _chat_history_for_context()
        task_id, err = submit_task_with_error('ai_consult', {'question': q, 'context': ctx})
        if task_id:
            st.session_state['ai_task_id'] = task_id
            st.session_state['ai_task_started_at'] = time.time()
            st.rerun()
        else:
            st.session_state['ai_chat'].pop()
            err = err or '未知错误'
            if '登录' in err or '过期' in err or '凭证' in err:
                xc_handle_error(err)
                if st.button('重新登录', key='ai_relogin', use_container_width=True):
                    st.session_state.clear()
                    st.switch_page('pages/90_登录.py')
            else:
                xc_handle_error("后台任务提交失败", err, hint="请刷新后重试")
            st.session_state['ai_task_id'] = None
    if st.session_state.get('ai_task_id'):
        _poll_ai_consult_task()
    st.markdown('</div>', unsafe_allow_html=True)