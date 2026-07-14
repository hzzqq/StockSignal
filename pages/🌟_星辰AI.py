"""
页面：🌟 星辰 AI（侧边栏入口 · 对话 + 分析一体）
================================================
按交付包「星辰 AI 交付包」设计重写：金融风对话界面（user 右 / assistant 左，
带边框气泡区分），接入 StockSignal 真实后端 ai_consult 任务，独立拉取数据并给出
「多市场智能股票分析师」式研判。同时保留右上角原有 ★ 星辰 AI 弹层（require_auth 注入）。

v3 修正：
- 跟随全局主题（白天/暗夜）自动切换，不再强制暗色；
- 聊天输入框原生样式通过 CSS 强制匹配主题；
- 用户消息展示真实用户名，头像置于右侧；
- 对话历史通过后端按用户持久化（GET/POST /api/chat/history），刷新不丢失；
- 输入框上方提供居中「回到底部」按钮；
- 修复 WELCOME 未定义错误。
"""

import os
import json
import html
import re
import time
import streamlit as st

st.set_page_config(page_title="🌟 星辰 AI", page_icon="🌟", layout="wide")
st.session_state["_active_page"] = __file__

from modules.session import require_auth, get_user
from modules.ui_theme import _theme_is_dark
from modules.starfield_theme import inject_plotly_dark, UP_COLOR, DOWN_COLOR
from modules.background_tasks import submit_task_with_error, poll_task, get_chat_history, save_chat_history
from modules.widgets import _slim_context


# ══════════════════════════════════════════════════════
# 常量：欢迎语（必须在主流程开始处定义，避免清空按钮引用时 NameError）
# ══════════════════════════════════════════════════════
WELCOME = {
    "role": "assistant",
    "content": (
        "你好，我是 **🌟 星辰 AI** —— 你的 A股分析搭档。\n\n"
        "可以问我：\n"
        "- 个股诊断：*太极实业 600667 怎么样？*\n"
        "- 横向对比：*对比贵州茅台和五粮液谁更值得买*\n"
        "- 事件解读：*最近半导体有哪些重要事件？*\n"
        "- 持仓建议：*当前市场环境下适合建仓吗？*\n\n"
        "我会独立拉取最新数据并给出结构化研判。"
    ),
    "chips": [
        {"label": "🔍 个股诊断", "prompt": "太极实业 600667 怎么样？"},
        {"label": "📊 横向对比", "prompt": "对比 贵州茅台 和 五粮液 谁更值得买"},
        {"label": "📰 事件解读", "prompt": "最近半导体有哪些重要事件？"},
        {"label": "💡 操作建议", "prompt": "当前市场环境下适合建仓吗？"},
    ],
}

# 历史持久化键已迁移到后端（按用户维度），不再使用浏览器 localStorage


# ══════════════════════════════════════════════════════
# 主题 CSS
# ══════════════════════════════════════════════════════
def _theme_css(dark: bool) -> str:
    """根据当前全局主题返回对应的 CSS 变量与聊天样式。"""
    if dark:
        root = """
  --bg:#0f0f23; --card:#1a1a2e; --card2:#15152a; --buy:#ff4d4f; --sell:#00d486;
  --hold:#ffa502; --acc1:#667eea; --acc2:#764ba2;
  --txt:#e2e8f0; --txt2:#94a3b8; --border:#2d2d44; --grid:#23233c;
  --user-bubble-bg:rgba(102,126,234,.18); --user-bubble-border:rgba(102,126,234,.35);
  --input-bg:#15152a; --input-txt:#e2e8f0; --input-border:#2d2d44; --input-placeholder:#64748b;
  --send-btn-bg:linear-gradient(135deg,#667eea,#764ba2); --send-btn-txt:#0f0f23;
"""
        app_bg = "#0f0f23"
    else:
        root = """
  --bg:#ffffff; --card:#ffffff; --card2:#f4f6fb; --buy:#ff4d4f; --sell:#00d486;
  --hold:#d97706; --acc1:#4f46e5; --acc2:#7c3aed;
  --txt:#1e293b; --txt2:#64748b; --border:#e2e8f0; --grid:#f1f5f9;
  --user-bubble-bg:#eef2ff; --user-bubble-border:#c7d2fe;
  --input-bg:#ffffff; --input-txt:#1e293b; --input-border:#e2e8f0; --input-placeholder:#9ca3af;
  --send-btn-bg:linear-gradient(135deg,#4f46e5,#7c3aed); --send-btn-txt:#ffffff;
"""
        app_bg = "#ffffff"

    return f"""
<style>
:root{{{root}}}
/* 让本页背景跟随全局主题，而不是强制暗色 */
.stApp{{background:{app_bg}!important}}
.block-container{{padding-top:1.1rem;max-width:1180px;padding-left:1.4rem;padding-right:1.4rem}}

.xc-msg{{display:flex;gap:12px;align-items:flex-start;margin:18px 0}}
.xc-av{{width:34px;height:34px;border-radius:50%;flex-shrink:0;display:grid;place-items:center;
  font-size:16px;background:linear-gradient(135deg,var(--acc1),var(--acc2));
  box-shadow:0 0 0 1px rgba(102,126,234,.4); color:#fff}}
.xc-user-av{{background:linear-gradient(135deg,#60a5fa,#3b82f6)}}
.xc-col{{flex:1;min-width:0}}
.xc-who{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.xc-name{{font-size:13px;font-weight:650;color:var(--txt)}}
.xc-role{{font-size:11px;color:var(--acc1);background:rgba(102,126,234,.16);
  padding:1px 8px;border-radius:999px;font-weight:600}}
.xc-bubble{{background:var(--card);border:1px solid var(--border);
  border-radius:4px 14px 14px 14px;padding:13px 16px;font-size:14.5px;color:var(--txt);
  box-shadow:0 6px 20px rgba(0,0,0,.28);line-height:1.75;word-break:break-word}}
.xc-bubble p{{margin:6px 0}}
.xc-bubble p:first-child{{margin-top:0}}
.xc-bubble p:last-child{{margin-bottom:0}}
.xc-bubble ul,.xc-bubble ol{{margin:6px 0;padding-left:22px}}
.xc-bubble li{{margin:3px 0}}
.xc-bubble .xc-h{{font-weight:700;color:var(--acc1);margin:12px 0 4px;font-size:14px;
  border-left:3px solid var(--acc1);padding-left:8px}}
.xc-bubble blockquote.xc-quote{{margin:8px 0;padding:6px 12px;border-left:3px solid var(--hold);
  background:rgba(255,165,2,.08);color:var(--txt2)}}
.xc-bubble pre.xc-pre{{background:#0c0c1a;color:#e2e8f0;padding:10px 12px;border-radius:8px;
  overflow-x:auto;font-size:12.5px;white-space:pre}}
.xc-bubble a{{color:var(--acc1)}}
.xc-bubble b{{color:var(--txt)}}

/* 用户消息：头像在右侧，气泡靠右 */
.xc-user{{justify-content:flex-end}}
.xc-user .xc-col{{display:flex;flex-direction:column;align-items:flex-end}}
.xc-user .xc-who{{justify-content:flex-end}}
.xc-user .xc-bubble{{background:var(--user-bubble-bg);border-color:var(--user-bubble-border);
  border-radius:14px 4px 14px 14px;max-width:80%;color:var(--txt)}}
.xc-user .xc-name{{font-weight:700}}

.xc-chips{{display:flex;gap:9px;flex-wrap:wrap;margin:12px 0 4px}}
.xc-chip{{border:1px solid var(--border);background:var(--card);border-radius:999px;
  padding:7px 15px;font-size:13px;color:var(--txt)}}
.xc-divider{{display:flex;align-items:center;gap:12px;color:var(--txt2);font-size:12px;margin:14px 0}}
.xc-divider::before,.xc-divider::after{{content:"";flex:1;height:1px;background:var(--border)}}
.xc-banner{{font-size:12px;color:var(--txt2);background:rgba(102,126,234,.10);
  border:1px solid rgba(102,126,234,.30);border-radius:10px;padding:8px 12px;margin-bottom:14px}}
.xc-typing{{display:flex;align-items:center;gap:10px;margin:14px 0;color:var(--txt2);font-size:13px}}
.xc-typing .dot{{width:8px;height:8px;border-radius:50%;background:var(--acc1);
  animation:xcblink 1.2s infinite both}}
.xc-typing .dot:nth-child(2){{animation-delay:.2s}}
.xc-typing .dot:nth-child(3){{animation-delay:.4s}}
@keyframes xcblink{{0%,80%,100%{{opacity:.25}}40%{{opacity:1}}}}

/* 聊天输入框（st.chat_input）主题适配：干掉白底/黑底错乱 */
/* 外层容器及所有 div/span 强制背景色，避免 Streamlit 某层 wrapper 白底 */
[data-testid="stChatInput"],
[data-testid="stChatInputContainer"],
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] form > div,
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div,
[data-testid="stChatInput"] > div > div > div,
[data-testid="stChatInput"] div,
[data-testid="stChatInput"] span:not([data-testid*="Icon"]) {{
  background: var(--input-bg) !important;
  border-color: var(--input-border) !important;
}}
[data-testid="stChatInput"] {{
  border: 1px solid var(--input-border) !important;
  border-radius: 14px !important;
  box-shadow: 0 4px 16px rgba(0,0,0,.12) !important;
  padding: 0 !important;
}}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] input,
[data-testid="stChatInputTextArea"] textarea {{
  background: var(--input-bg) !important;
  color: var(--input-txt) !important;
  border: none !important;
  box-shadow: none !important;
  caret-color: var(--input-txt) !important;
}}
[data-testid="stChatInput"] textarea::placeholder,
[data-testid="stChatInput"] input::placeholder,
[data-testid="stChatInputTextArea"] textarea::placeholder {{
  color: var(--input-placeholder) !important;
}}
[data-testid="stChatInput"] button,
[data-testid="stChatInput"] button:hover,
[data-testid="stChatInput"] button:focus,
[data-testid="stChatInput"] button:active {{
  background: var(--send-btn-bg) !important;
  color: var(--send-btn-txt) !important;
  border: none !important;
  box-shadow: none !important;
}}
[data-testid="stChatInput"] button svg,
[data-testid="stChatInput"] button path {{
  fill: var(--send-btn-txt) !important;
  stroke: var(--send-btn-txt) !important;
}}
/* 将默认发送/停止图标替换为纸飞机 */
[data-testid="stChatInput"] button {{
  position: relative;
}}
[data-testid="stChatInput"] button svg {{
  opacity: 0 !important;
}}
[data-testid="stChatInput"] button::after {{
  content: "";
  position: absolute;
  top: 50%; left: 50%;
  width: 20px; height: 20px;
  transform: translate(-50%, -50%);
  background-color: var(--send-btn-txt);
  -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M2.01 21L23 12 2.01 3 2 10l15 2-15 2z'/%3E%3C/svg%3E");
  mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M2.01 21L23 12 2.01 3 2 10l15 2-15 2z'/%3E%3C/svg%3E");
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  -webkit-mask-position: center;
  mask-position: center;
  -webkit-mask-size: contain;
  mask-size: contain;
  pointer-events: none;
}}

/* 回到底部按钮已改为视口级浮动 ▼（见 modules/scroll_nav.py），此处不再内联 */
</style>
"""


esc = lambda s: html.escape(str(s), quote=False)


# ══════════════════════════════════════════════════════
# markdown → HTML
# ══════════════════════════════════════════════════════
def _inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    return t


def _md_to_html(md: str) -> str:
    lines = (md or "").split("\n")
    out = []
    list_type = [None]

    def close_list():
        if list_type[0]:
            out.append(f"</{list_type[0]}>")
            list_type[0] = None

    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("```"):
            close_list()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            out.append("<pre class='xc-pre'>" + html.escape("\n".join(buf), quote=False) + "</pre>")
            i += 1
            continue
        if not s:
            close_list()
            i += 1
            continue
        m = re.match(r"^(\d+)\.\s+(.*)", s)
        if m:
            if list_type[0] != "ol":
                close_list()
                out.append("<ol>")
                list_type[0] = "ol"
            out.append("<li>" + _inline(m.group(2)) + "</li>")
            i += 1
            continue
        if s.startswith("- ") or s.startswith("* "):
            if list_type[0] != "ul":
                close_list()
                out.append("<ul>")
                list_type[0] = "ul"
            out.append("<li>" + _inline(s[2:]) + "</li>")
            i += 1
            continue
        if s.startswith(">"):
            close_list()
            out.append("<blockquote class='xc-quote'>" + _inline(s[1:].strip()) + "</blockquote>")
            i += 1
            continue
        if re.match(r"^【.+】$", s):
            close_list()
            out.append("<div class='xc-h'>" + _inline(s) + "</div>")
            i += 1
            continue
        close_list()
        out.append("<p>" + _inline(s) + "</p>")
        i += 1
    close_list()
    return "\n".join(out)


# ══════════════════════════════════════════════════════
# 消息渲染
# ══════════════════════════════════════════════════════
def _avatar_text(username: str) -> str:
    """取用户名前 1-2 个字符作为头像文字（中文取 1 字，英文取 2 字母）。"""
    if not username:
        return "👤"
    if any("\u4e00" <= c <= "\u9fff" for c in username):
        return username[0]
    return username[:2].upper()


def render_message(m: dict, idx: int, username: str) -> None:
    if m.get("role") == "user":
        st.markdown(
            f'<div class="xc-msg xc-user">'
            f'<div class="xc-col"><div class="xc-who"><span class="xc-name">{esc(username)}</span></div>'
            f'<div class="xc-bubble xc-user-bubble">{esc(m.get("content", ""))}</div>'
            f'</div><div class="xc-av xc-user-av">{_avatar_text(username)}</div></div>',
            unsafe_allow_html=True,
        )
        return

    # assistant
    st.markdown(
        '<div class="xc-msg"><div class="xc-av">🌟</div>'
        '<div class="xc-col"><div class="xc-who">'
        '<span class="xc-name">星辰 AI</span><span class="xc-role">助手</span>'
        '</div>'
        f'<div class="xc-bubble">{_md_to_html(m.get("content", ""))}</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    # 快捷追问 chips（仅欢迎语且尚无用户发言时展示）
    chips = m.get("chips") or []
    if chips and len(st.session_state.get("xc_messages", [])) <= 1:
        _render_chips(chips)


def _render_chips(options):
    cols = st.columns(len(options))
    for i, o in enumerate(options):
        if cols[i].button(o["label"], key=f"xc_chip_{i}", use_container_width=True):
            st.session_state["_xc_pending"] = o["prompt"]
            st.rerun()


# ══════════════════════════════════════════════════════
# 持久化：后端对话历史（按用户维度）↔ session_state
# ══════════════════════════════════════════════════════
def _restore_messages_from_storage():
    """若 session_state 还没有消息，从后端拉取当前用户的对话历史并恢复。

    对话历史持久化已改为后端存储，不再依赖浏览器 localStorage：
    components.html 运行在 srcdoc sandbox iframe 中（origin 为 null），
    既无法回读父窗口 localStorage，组件返回值路径在本 Streamlit 构建下也死掉
    （components.html 返回 DeltaGenerator 而非组件值，且不支持 key= 参数）。
    故每次会话首次加载时向后端 GET /api/chat/history 拉取，由 Python 写入
    session_state。刷新后再次进入本页即重新拉取，实现「刷新不丢失」。
    """
    if "xc_messages" in st.session_state:
        return
    try:
        msgs = get_chat_history()
    except Exception:
        msgs = []
    if msgs:
        st.session_state["xc_messages"] = msgs


def _save_messages_to_storage(messages: list):
    """将当前消息保存到后端（按用户维度）。

    带签名去重：仅当消息内容相对上次保存发生变化时才打网络请求，
    避免每次 rerun（含 AI 等待期的 5s 自动刷新）都重复 POST。
    """
    try:
        sig = (len(messages), hash(json.dumps(messages, ensure_ascii=False)[:4000]))
    except Exception:
        sig = (len(messages), 0)
    if st.session_state.get("xc_messages_sig") == sig:
        return
    st.session_state["xc_messages_sig"] = sig
    save_chat_history(messages)


# ══════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════
require_auth()  # 注入右上角原有 ★ 星辰 AI 弹层 + 主题开关（保留现有功能）

# 本页跟随全局主题，而不是强制暗色；根据当前主题注入对应 CSS
dark = _theme_is_dark()
inject_plotly_dark()
st.markdown(_theme_css(dark), unsafe_allow_html=True)

username = (get_user() or {}).get("username", "你")

# 尝试从后端拉取历史
_restore_messages_from_storage()

# 初始化会话状态
if "xc_messages" not in st.session_state:
    st.session_state["xc_messages"] = [dict(WELCOME)]
if "xc_task_id" not in st.session_state:
    st.session_state["xc_task_id"] = None
if "xc_task_started_at" not in st.session_state:
    st.session_state["xc_task_started_at"] = None

# 保存当前消息到后端（签名去重，仅变化时才提交）
_save_messages_to_storage(st.session_state.get("xc_messages", []))

# ▲ 回到顶部 + ▼ 回到底部 + C 键清缓存拦截 已由 apply_theme() 的【首次】
# components.html 注入一并完成。▼ 由本页的 st.chat_input（testid=stChatInput，全站唯一）
# 驱动出现/消失：脚本监听该原生组件存在即创建视口级浮动 ▼，离页即移除。
# 注意：同页再次调用 components.html 的脚本不会可靠执行，故 ▼ 由首次注入统一创建。

# ── 标题栏 + 清空 ──
h_left, h_right = st.columns([6, 1])
with h_left:
    st.markdown(
        '<div style="display:flex;align-items:baseline;gap:10px">'
        '<span style="font-size:22px;font-weight:800;color:var(--txt)">🌟 星辰 AI</span>'
        '<span style="font-size:13px;color:var(--txt2)">对话 + 分析一体 · A股分析搭档</span>'
        '</div>',
        unsafe_allow_html=True,
    )
with h_right:
    if st.button("🗑️ 清空", key="xc_clear", use_container_width=True, help="清空对话"):
        st.session_state["xc_messages"] = [dict(WELCOME)]
        st.session_state["xc_task_id"] = None
        st.session_state["xc_task_started_at"] = None
        st.rerun()

st.markdown(
    '<div class="xc-banner">💡 我可独立拉取行情 / 基本面 / 事件数据并给出研判；'
    '当前页面的对比组合或个股会自动作为上下文。回复为模型推演，不构成投资建议。</div>',
    unsafe_allow_html=True,
)

# ── 渲染历史 ──
for idx, m in enumerate(st.session_state["xc_messages"]):
    render_message(m, idx, username)

# ── 思考中占位 ──
if st.session_state.get("xc_task_id"):
    st.markdown(
        '<div class="xc-typing"><span class="dot"></span><span class="dot"></span>'
        '<span class="dot"></span><span>星辰 AI 正在思考…</span></div>',
        unsafe_allow_html=True,
    )

# ── 回到底部按钮：由 apply_theme() 注入的 inject_scroll_nav 在首次
#    components.html 中创建视口级浮动 ▼（right:24px;bottom:110px），
#    以本页 st.chat_input 的 testid=stChatInput 存在性驱动出现/消失 ──

# ── 收集输入 ──
prompt = None
if "_xc_pending" in st.session_state:
    prompt = st.session_state.pop("_xc_pending")
user_text = st.chat_input("问星辰 AI…（Enter 发送 / Shift+Enter 换行）")
if user_text:
    prompt = user_text

# ── 提交后台任务 ──
if prompt:
    st.session_state["xc_messages"].append({"role": "user", "content": prompt})
    history = [
        {"role": mm.get("role"), "content": mm.get("content", "")}
        for mm in st.session_state["xc_messages"][:-1]
        if mm.get("role") in ("user", "assistant")
    ]
    ctx = _slim_context()
    ctx["history"] = history[-6:]
    task_id, err = submit_task_with_error("ai_consult", {"question": prompt, "context": ctx})
    if task_id:
        st.session_state["xc_task_id"] = task_id
        st.session_state["xc_task_started_at"] = time.time()
        st.rerun()
    else:
        st.session_state["xc_messages"].append(
            {"role": "assistant", "content": f"❌ 后台任务提交失败：{err or '未知错误'}，请刷新后重试。"}
        )
        st.session_state["xc_task_id"] = None
        st.rerun()

# ── 轮询后台任务 ──
task_id = st.session_state.get("xc_task_id")
if task_id:
    task = poll_task(task_id, max_wait=0.4)
    if task and task.get("status") == "success":
        result = task.get("result") or {}
        answer = result.get("answer") or "AI 暂未给出回答"
        st.session_state["xc_messages"].append({"role": "assistant", "content": answer})
        st.session_state["xc_task_id"] = None
        st.session_state["xc_task_started_at"] = None
        st.rerun()
    elif task and task.get("status") == "error":
        st.session_state["xc_messages"].append(
            {"role": "assistant", "content": f"❌ AI 分析失败：{task.get('error') or '未知错误'}"}
        )
        st.session_state["xc_task_id"] = None
        st.session_state["xc_task_started_at"] = None
        st.rerun()
    else:
        started = st.session_state.get("xc_task_started_at") or time.time()
        if time.time() - started > 240:
            st.session_state["xc_messages"].append(
                {"role": "assistant", "content": "❌ AI 响应超时，请重新提问。"}
            )
            st.session_state["xc_task_id"] = None
            st.session_state["xc_task_started_at"] = None
            st.rerun()
        try:
            from streamlit_autorefresh import st_autorefresh

            st_autorefresh(interval=5000, limit=150, key="xc_autorefresh")
        except Exception:
            pass
