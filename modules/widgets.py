"""
modules/widgets.py
------------------
跨页面复用的 Streamlit 小组件：
  - render_global_search  侧边栏全局股票搜索
  - render_theme_toggle   侧边栏深色/浅色快速切换
  - render_notifications  侧边栏通知中心
  - render_breadcrumb     页面面包屑
  - password_strength      密码强度评估（注册用）
"""

from __future__ import annotations

from typing import Any, Dict
import time
import requests
import streamlit as st
import streamlit.components.v1 as components

from modules.session import API_BASE, get_token, safe_switch_page


# ──────────────────────────────────────────────────────────────
# 全局股票搜索
# ──────────────────────────────────────────────────────────────
def render_global_search() -> None:
    """侧边栏全局搜索框：输入关键词实时搜索股票，回车/点击结果进入行情看板。"""
    st.markdown("### 🔍 股票搜索")
    q = st.text_input(
        "股票代码 / 名称 / 拼音",
        key="global_search_q",
        placeholder="如 600519 / 茅台 / mt",
        label_visibility="collapsed",
    )
    if q:
        try:
            resp = requests.get(
                f"{API_BASE}/api/stocks/search",
                params={"q": q, "limit": 8},
                headers={"Authorization": f"Bearer {get_token()}"},
                timeout=5,
            )
            if resp.status_code == 200:
                body = resp.json()
                results = body.get("data") or []
                if results:
                    for item in results:
                        label = f"{item.get('code', '')} {item.get('name', '')}"
                        if st.button(label, key=f"search_{item.get('code')}", use_container_width=True):
                            # 记录到「最近浏览」
                            _push_recent(item.get("code"), item.get("name"))
                            safe_switch_page("pages/1_行情看板.py")
                else:
                    st.caption("无匹配结果")
            else:
                st.caption("搜索失败")
        except Exception:
            st.caption("搜索服务不可用")


# ──────────────────────────────────────────────────────────────
# 主题快速切换
# ──────────────────────────────────────────────────────────────
def render_theme_toggle() -> None:
    """侧边栏深色 / 浅色快速切换（读/写 session_state['theme_mode']）。"""
    from modules.ui_theme import get_current_mode, apply_theme

    mode = st.session_state.get("theme_mode", get_current_mode())
    col_dark, col_light = st.columns(2)
    with col_dark:
        if st.button(
            "🌙 暗夜",
            use_container_width=True,
            type="primary" if mode == "dark" else "secondary",
            key="theme_toggle_dark",
        ):
            st.session_state["theme_mode"] = "dark"
            apply_theme()
            st.rerun()
    with col_light:
        if st.button(
            "☀️ 白天",
            use_container_width=True,
            type="primary" if mode == "light" else "secondary",
            key="theme_toggle_light",
        ):
            st.session_state["theme_mode"] = "light"
            apply_theme()
            st.rerun()


# ──────────────────────────────────────────────────────────────
# 右上角通用栏：★ 星辰 AI 弹层 + 主题切换（所有页面通用）
# ──────────────────────────────────────────────────────────────
def render_topright_bar() -> None:
    """主区右上角通用栏：[★ 星辰 AI 弹层] [🌙 暗夜] [☀️ 白天]。

    由 require_auth() 在每个业务页面顶部注入，保证「不管用户在哪个界面」
    都能唤起 AI 咨询与切换主题。AI 咨询收进 popover 弹层，不占侧栏空间。
    """
    from modules.ui_theme import get_current_mode, apply_theme

    mode = st.session_state.get("theme_mode", get_current_mode())
    left, right = st.columns([0.62, 0.38])
    with right:
        c_ai, c_d, c_l = st.columns([0.56, 0.22, 0.22])
        with c_ai:
            # st.popover 原生弹层：任意页面右上角唤起 AI 咨询
            try:
                with st.popover("★ 星辰 AI", use_container_width=True):
                    render_ai_consultant()
            except Exception:
                # 极老版本 Streamlit 无 popover 时兜底：退回侧边栏
                with st.sidebar:
                    render_ai_consultant()
        with c_d:
            if st.button(
                "🌙", key="top_theme_dark", use_container_width=True,
                type="primary" if mode == "dark" else "secondary",
                help="暗夜模式",
            ):
                st.session_state["theme_mode"] = "dark"
                apply_theme()
                st.rerun()
        with c_l:
            if st.button(
                "☀️", key="top_theme_light", use_container_width=True,
                type="primary" if mode == "light" else "secondary",
                help="白天模式",
            ):
                st.session_state["theme_mode"] = "light"
                apply_theme()
                st.rerun()


# 向后兼容别名（旧调用点仍可用）
def render_theme_toggle_topright() -> None:
    render_topright_bar()


# ──────────────────────────────────────────────────────────────
# 全局 AI 咨询（★ 星辰 · 多市场智能股票分析师）
# ──────────────────────────────────────────────────────────────
from modules.background_tasks import submit_task, poll_task


def _slim_context() -> Dict[str, Any]:
    """把当前页面上下文精简，只传 AI 需要的汇总字段，避免序列化 DataFrame。"""
    rows = st.session_state.get("_cmp_rows")
    slim_rows = None
    if rows:
        slim_rows = []
        for r in rows:
            slim_rows.append({
                "code": r.get("code"),
                "name": r.get("name"),
                "signal": r.get("signal"),
                "scores": r.get("scores"),
                "industry": r.get("industry"),
                "market_cap": r.get("market_cap"),
                "pe_ttm": r.get("pe_ttm"),
                "elasticity": r.get("elasticity"),
                "business_corr": r.get("business_corr"),
            })
    analysis = st.session_state.get("analysis_result")
    slim_analysis = None
    if analysis and isinstance(analysis, dict):
        slim_analysis = {k: v for k, v in analysis.items() if k != "df"}
    return {"_cmp_rows": slim_rows, "analysis_result": slim_analysis}


def _current_stock_context():
    """从个股分析页的 session 结果中提取当前股票上下文。"""
    ar = st.session_state.get("analysis_result")
    if isinstance(ar, dict):
        name = ar.get("name") or ar.get("stock_name") or ar.get("code")
        verdict = ar.get("verdict") or ar.get("signal")
        score = ar.get("score") or ar.get("composite") or ar.get("score_composite")
        if name:
            return str(name), verdict, score
    return None, None, None


def _ai_popover_theme_css() -> str:
    """Popover 内部额外主题适配，确保暗色下文字/背景/按钮可读。"""
    from modules.ui_theme import _theme_is_dark
    if _theme_is_dark():
        return """
        <style>
        .ai-consult-wrap { background:#1a1a2e; color:#e2e8f0; padding:2px; border-radius:10px; }
        .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#e2e8f0 !important; }
        /* 输入框：常态/hover/focus/active 强制黑底，避免白底闪动 */
        .ai-consult-wrap [data-testid="stTextArea"] textarea,
        .ai-consult-wrap [data-testid="stTextArea"] textarea:hover,
        .ai-consult-wrap [data-testid="stTextArea"] textarea:focus,
        .ai-consult-wrap [data-testid="stTextArea"] textarea:active {
            background:#15152a !important; color:#e2e8f0 !important;
            border:1px solid #2d2d44 !important; box-shadow:none !important;
        }
        .ai-consult-wrap [data-testid="stTextArea"] textarea::placeholder { color:#64748b !important; }
        .ai-consult-wrap [data-testid="stTextArea"] > div { background:transparent !important; border:none !important; }
        /* 发送/清空按钮：常态/hover/focus/active 深紫底+深字 */
        .ai-consult-wrap [data-testid="stFormSubmitButton"] button,
        .ai-consult-wrap [data-testid="stFormSubmitButton"] button:hover,
        .ai-consult-wrap [data-testid="stFormSubmitButton"] button:focus,
        .ai-consult-wrap [data-testid="stFormSubmitButton"] button:active,
        .ai-consult-wrap .stButton button,
        .ai-consult-wrap .stButton button:hover,
        .ai-consult-wrap .stButton button:focus,
        .ai-consult-wrap .stButton button:active {
            background:linear-gradient(180deg,#667eea,#764ba2) !important; color:#0f0f23 !important;
            border:none !important; box-shadow:none !important; font-weight:600 !important;
        }
        .ai-consult-wrap [data-testid="stFormSubmitButton"] button:disabled,
        .ai-consult-wrap .stButton button:disabled { opacity:.55 !important; }
        /* 对话气泡 */
        .ai-chat-box { max-height:380px; overflow-y:auto; padding:8px 2px; display:flex; flex-direction:column; gap:10px; }
        .ai-chat-box .ai-msg { max-width:92%; padding:8px 12px; border-radius:14px; font-size:13px; line-height:1.6; word-break:break-word; box-shadow:0 1px 4px rgba(0,0,0,.25); }
        .ai-chat-box .ai-msg p { color:inherit !important; }
        /* 用户消息：带边框方框，深灰底 */
        .ai-chat-box .ai-msg.user { align-self:flex-end; background:#252542; color:#e2e8f0; border:1px solid #3b3b5c; border-bottom-right-radius:4px; }
        .ai-chat-box .ai-msg.assistant { align-self:flex-start; background:#15152a; color:#e2e8f0; border:1px solid #2d2d44; border-bottom-left-radius:4px; }
        .ai-chat-box .ai-role { font-size:10px; opacity:.65; margin-bottom:2px; }
        .ai-chat-box .ai-msg.user .ai-role { text-align:right; color:#94a3b8; }
        .ai-typing { align-self:flex-start; font-size:12px; color:#94a3b8; padding:4px 2px; }
        </style>
        """
    return """
    <style>
    .ai-consult-wrap { background:#ffffff; color:#111827; padding:2px; border-radius:10px; }
    .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#111827 !important; }
    .ai-consult-wrap [data-testid="stTextArea"] textarea,
    .ai-consult-wrap [data-testid="stTextArea"] textarea:hover,
    .ai-consult-wrap [data-testid="stTextArea"] textarea:focus,
    .ai-consult-wrap [data-testid="stTextArea"] textarea:active {
        background:#ffffff !important; color:#111827 !important;
        border:1px solid #d1d5db !important; box-shadow:none !important;
    }
    .ai-consult-wrap [data-testid="stTextArea"] textarea::placeholder { color:#9ca3af !important; }
    .ai-consult-wrap [data-testid="stTextArea"] > div { background:transparent !important; border:none !important; }
    .ai-consult-wrap [data-testid="stFormSubmitButton"] button,
    .ai-consult-wrap [data-testid="stFormSubmitButton"] button:hover,
    .ai-consult-wrap [data-testid="stFormSubmitButton"] button:focus,
    .ai-consult-wrap [data-testid="stFormSubmitButton"] button:active,
    .ai-consult-wrap .stButton button,
    .ai-consult-wrap .stButton button:hover,
    .ai-consult-wrap .stButton button:focus,
    .ai-consult-wrap .stButton button:active {
        background:linear-gradient(180deg,#D4A02A,#B8860B) !important; color:#111827 !important;
        border:none !important; box-shadow:none !important; font-weight:600 !important;
    }
    .ai-consult-wrap [data-testid="stFormSubmitButton"] button:disabled,
    .ai-consult-wrap .stButton button:disabled { opacity:.55 !important; }
    /* 对话气泡 */
    .ai-chat-box { max-height:380px; overflow-y:auto; padding:8px 2px; display:flex; flex-direction:column; gap:10px; }
    .ai-chat-box .ai-msg { max-width:92%; padding:8px 12px; border-radius:14px; font-size:13px; line-height:1.6; word-break:break-word; box-shadow:0 1px 3px rgba(0,0,0,.06); }
    .ai-chat-box .ai-msg p { color:inherit !important; }
    .ai-chat-box .ai-msg.user { align-self:flex-end; background:#fff7e6; color:#111827; border:1px solid #ffd591; border-bottom-right-radius:4px; }
    .ai-chat-box .ai-msg.assistant { align-self:flex-start; background:#f4f6fb; color:#111827; border:1px solid #e2e8f0; border-bottom-left-radius:4px; }
    .ai-chat-box .ai-role { font-size:10px; opacity:.55; margin-bottom:2px; }
    .ai-chat-box .ai-msg.user .ai-role { text-align:right; color:#6b7280; }
    .ai-typing { align-self:flex-start; font-size:12px; color:#6b7280; padding:4px 2px; }
    </style>
    """


def _chat_history_for_context(max_turns: int = 6) -> list:
    """取最近若干轮对话，给 AI 引擎做「可持续追问」的上下文。"""
    chat = st.session_state.get("ai_chat") or []
    return chat[-max_turns:]


def _render_ai_chat() -> None:
    """渲染对话气泡（用户右、助手左），可滚动。"""
    chat = st.session_state.get("ai_chat") or []
    st.markdown('<div class="ai-chat-box">', unsafe_allow_html=True)
    for msg in chat:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            st.markdown(
                f'<div class="ai-msg user"><div class="ai-role">你</div>{content}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="ai-msg assistant"><div class="ai-role">★ 星辰 AI</div>{content}</div>',
                unsafe_allow_html=True,
            )
    # 正在思考的占位
    if st.session_state.get("ai_task_id"):
        st.markdown('<div class="ai-typing">🤔 AI 正在思考…</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _ai_scroll_to_bottom_component(dark: bool) -> None:
    """在 popover 内渲染一个「滚动到底部」按钮，并自动把对话区域滚到底。"""
    bg = "#667eea" if dark else "#D4A02A"
    color = "#ffffff" if dark else "#111827"
    hover_bg = "#764ba2" if dark else "#B8860B"
    js = f"""
    <div id="ai-scroll-bottom-btn" style="width:100%;display:flex;justify-content:center;padding:6px 0;cursor:pointer;"
         onclick="scrollAIChatToBottom()">
      <div style="width:34px;height:34px;border-radius:50%;background:{bg};color:{color};display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 6px rgba(0,0,0,.25);" onmouseover="this.style.background='{hover_bg}'" onmouseout="this.style.background='{bg}'">▼</div>
    </div>
    <script>
      function scrollAIChatToBottom() {{
        var doc = window.parent.document;
        var box = doc.querySelector('.ai-chat-box');
        if (box) box.scrollTop = box.scrollHeight;
      }}
      setTimeout(scrollAIChatToBottom, 60);
      setTimeout(scrollAIChatToBottom, 300);
    </script>
    """
    components.html(js, height=48)


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
    """
    from modules.ui_theme import _theme_is_dark

    st.markdown(_ai_popover_theme_css(), unsafe_allow_html=True)
    st.markdown('<div class="ai-consult-wrap">', unsafe_allow_html=True)

    # 初始化持久化对话状态
    if "ai_chat" not in st.session_state:
        st.session_state["ai_chat"] = []  # [{"role":"user"/"assistant", "content": str}]
    if "ai_task_id" not in st.session_state:
        st.session_state["ai_task_id"] = None
    if "ai_task_started_at" not in st.session_state:
        st.session_state["ai_task_started_at"] = None

    # 标题 + 清空对话按钮 同一行
    head_col1, head_col2 = st.columns([5, 1])
    with head_col1:
        st.markdown("#### ★ 星辰 · 多市场智能股票分析师")
    with head_col2:
        if st.session_state["ai_chat"]:
            if st.button("🗑️", key="ai_clear_chat", help="清空对话"):
                st.session_state["ai_chat"] = []
                st.session_state["ai_task_id"] = None
                st.session_state["ai_task_started_at"] = None
                st.rerun()

    rows = st.session_state.get("_cmp_rows")
    name, verdict, score = _current_stock_context()
    if rows:
        st.caption(f"📊 当前对比 {len(rows)} 只标的，AI 会优先回答你提到的股票。")
    elif name:
        st.caption(f"🎯 当前个股：{name}，你直接问其他股票我也会独立分析。")
    else:
        st.caption("输入股票代码或名称，AI 会独立拉取数据并给出研判。")

    # 渲染历史对话
    _render_ai_chat()

    # 滚动到底部按钮 + 自动滚底
    _ai_scroll_to_bottom_component(dark=_theme_is_dark())

    # 输入框 + 发送（只在没有任务进行时允许输入，避免并发）
    busy = bool(st.session_state.get("ai_task_id"))
    with st.form("ai_consult_global", clear_on_submit=True):
        q = st.text_area(
            "AI 咨询",
            placeholder="例如：深科技怎么样？ / 这组合里谁最值得买？风险在哪？",
            height=80,
            label_visibility="collapsed",
            key="ai_consult_q",
            disabled=busy,
        )
        submitted = st.form_submit_button(
            "🚀 发送" if not busy else "⏳ AI 思考中…",
            use_container_width=True,
            disabled=busy,
        )

    if submitted and q and not busy:
        # 追加用户消息
        st.session_state["ai_chat"].append({"role": "user", "content": q})
        # 提交后台任务（带上历史，让 AI 可持续追问）
        ctx = _slim_context()
        ctx["history"] = _chat_history_for_context()
        try:
            task_id = submit_task("ai_consult", {"question": q, "context": ctx})
        except Exception as e:
            task_id = None
            st.error(f"❌ 提交失败：{e}")
        if task_id:
            st.session_state["ai_task_id"] = task_id
            st.session_state["ai_task_started_at"] = time.time()
            st.rerun()
        else:
            # 提交失败，回滚用户消息，避免只显示问题没有回答
            st.session_state["ai_chat"].pop()
            st.error("❌ 后台任务提交失败，请刷新后重试。")
            st.session_state["ai_task_id"] = None

    # 轮询后台任务状态
    task_id = st.session_state.get("ai_task_id")
    if task_id:
        task = poll_task(task_id, max_wait=0.4)
        if task and task.get("status") == "success":
            result = task.get("result") or {}
            answer = result.get("answer") or "AI 暂未给出回答"
            st.session_state["ai_chat"].append({"role": "assistant", "content": answer})
            st.session_state["ai_task_id"] = None
            st.session_state["ai_task_started_at"] = None
            st.rerun()
        elif task and task.get("status") == "error":
            err = task.get("error") or "未知错误"
            st.session_state["ai_chat"].append(
                {"role": "assistant", "content": f"❌ AI 分析失败：{err}"}
            )
            st.session_state["ai_task_id"] = None
            st.session_state["ai_task_started_at"] = None
            st.rerun()

    # 只在任务运行且未超时时低频刷新，避免持续影响整个页面
    if st.session_state.get("ai_task_id"):
        started = st.session_state.get("ai_task_started_at") or time.time()
        elapsed = time.time() - started
        if elapsed > 90:
            # 超时：自动结束，避免永远刷新
            st.session_state["ai_chat"].append(
                {"role": "assistant", "content": "❌ AI 响应超时，请重新提问。"}
            )
            st.session_state["ai_task_id"] = None
            st.session_state["ai_task_started_at"] = None
            st.rerun()
        try:
            from streamlit_autorefresh import st_autorefresh

            st_autorefresh(interval=4000, limit=120, key="ai_chat_autorefresh")
        except Exception:
            pass

    st.markdown("</div>", unsafe_allow_html=True)


# 保留旧函数签名的占位（已被后台异步方案替代）
def _ai_summary_compare(rows: list, question: str) -> str:
    """旧版同步简报函数，保留仅做兼容。"""
    return ""


def _ai_answer(rows, question, name=None, verdict=None, score=None) -> str:
    """旧版同步回答函数，保留仅做兼容。"""
    return ""


def inject_global_widgets() -> None:
    """require_auth() 之后注入所有页面通用组件：右上角「★ 星辰 AI 弹层 + 主题开关」。

    AI 咨询收进右上角 popover，任意页面唤起；不再占用左侧栏空间。
    """
    render_topright_bar()


# ──────────────────────────────────────────────────────────────
# 通知中心
# ──────────────────────────────────────────────────────────────
def render_notifications() -> None:
    """侧边栏通知中心：展示自选股数量、最近登录时间、使用提示。"""
    st.markdown("### 🔔 通知中心")
    try:
        resp = requests.get(
            f"{API_BASE}/api/watchlist",
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=5,
        )
        wl_count = 0
        if resp.status_code == 200:
            body = resp.json()
            wl_count = len(body.get("data") or [])
        st.info(f"⭐ 自选股：**{wl_count}** 只")
    except Exception:
        st.info("⭐ 自选股：—")

    # 最近登录记录
    try:
        resp = requests.get(
            f"{API_BASE}/api/auth/logins",
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=5,
        )
        if resp.status_code == 200:
            logs = resp.json().get("data") or []
            if logs:
                last = logs[0].get("created_at", "")[:19].replace("T", " ")
                st.caption(f"🕒 上次登录：{last}")
    except Exception:
        pass

    with st.expander("📌 使用提示", expanded=False):
        st.markdown("""
        - 行情看板支持 **日K / 周K / 月K** 切换
        - 个股分析提供趋势、情绪、事件与作战计划
        - 事件追踪综合三类信号评分
        """)


# ──────────────────────────────────────────────────────────────
# 面包屑
# ──────────────────────────────────────────────────────────────
def render_breadcrumb(items: list[str]) -> None:
    """页面顶部面包屑。items 形如 ['首页', '行情看板']。"""
    st.markdown(" › ".join(f"**{i}**" for i in items), help="当前位置")


# ──────────────────────────────────────────────────────────────
# 最近浏览（session_state 维护）
# ──────────────────────────────────────────────────────────────
def _push_recent(code: str, name: str) -> None:
    if "recent_stocks" not in st.session_state:
        st.session_state["recent_stocks"] = []
    recents = st.session_state["recent_stocks"]
    recents = [r for r in recents if r.get("code") != code]
    recents.insert(0, {"code": code, "name": name})
    st.session_state["recent_stocks"] = recents[:8]


def get_recent_stocks() -> list:
    return st.session_state.get("recent_stocks", [])


# ──────────────────────────────────────────────────────────────
# 密码强度
# ──────────────────────────────────────────────────────────────
def password_strength(pwd: str) -> tuple[int, str]:
    """返回 (分数 0-4, 等级文本)。"""
    if not pwd:
        return 0, "空"
    score = 0
    if len(pwd) >= 8:
        score += 1
    if len(pwd) >= 12:
        score += 1
    if any(c.isupper() for c in pwd) and any(c.islower() for c in pwd):
        score += 1
    if any(c.isdigit() for c in pwd) and any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/" for c in pwd):
        score += 1
    levels = ["弱", "弱", "中", "强", "很强"]
    return score, levels[score]


# ──────────────────────────────────────────────────────────────
# 会话剩余时间（自动登出倒计时）
# ──────────────────────────────────────────────────────────────
def get_session_remaining() -> int | None:
    """解码当前 JWT 的 exp，返回剩余秒数；无法解析时返回 None。"""
    import time as _time
    import jwt as _jwt
    token = get_token()
    if not token:
        return None
    try:
        payload = _jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        if not exp:
            return None
        return max(0, int(exp - _time.time()))
    except Exception:
        return None


def render_session_countdown() -> None:
    """显示当前登录会话剩余时间（自动登出倒计时）。"""
    remain = get_session_remaining()
    if remain is None:
        st.caption("⏱️ 会话状态：未知")
        return
    minutes = remain // 60
    seconds = remain % 60
    st.caption(f"⏱️ 会话剩余：{minutes}分{seconds}秒（超时将自动登出）")
