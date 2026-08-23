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

import json
import html
import re
import time
import streamlit as st

from modules.ui_theme import apply_page_config, _theme_is_dark
from modules.session import require_auth, get_user, render_user_badge, fragment_market_alerts_panel
from modules.starfield_theme import inject_plotly_dark
from modules.background_tasks import submit_task_with_error, poll_task, get_chat_history, save_chat_history
from modules.widgets import _slim_context
from modules.widgets import STAR_AI_LOGO
from modules.page_guard import safe_fragment
from mcp_server.gateway import detect_intent, call_tool

apply_page_config(page_title="🌟 星辰 AI", page_icon="🌟", layout="wide")
st.session_state["_active_page"] = __file__


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
.xc-role-user{{font-size:11px;color:#fff;background:linear-gradient(135deg,var(--buy),#ff7a45);
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

/* 工具卡片：数据透视，区别于自然语言气泡 */
.xc-role-tool{{color:#fff;background:linear-gradient(135deg,#0ea5e9,#22d3ee);
  border:1px solid rgba(14,165,233,.5)}}
.xc-tool-card{{border-radius:14px 4px 14px 14px;border:1px solid rgba(14,165,233,.35);
  background:linear-gradient(135deg,rgba(14,165,233,.06),rgba(34,211,238,.04))}}
.xc-tool-card .xc-tool-err{{color:var(--hold);font-size:13px;padding:4px 2px}}
.xc-tool-tbl{{width:100%;border-collapse:collapse;font-size:13px;margin-top:2px}}
.xc-tool-tbl th,.xc-tool-tbl td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--border);
  color:var(--txt);vertical-align:top}}
.xc-tool-tbl th{{color:var(--acc1);font-weight:650;background:rgba(102,126,234,.08)}}
/* 实时盘口 / 市场情绪卡片的 KV 键值网格 */
.xc-kv-grid{{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px;margin-top:6px}}
.xc-kv{{display:flex;justify-content:space-between;align-items:baseline;
  font-size:13px;padding:3px 0;border-bottom:1px dashed rgba(125,140,180,.18)}}
.xc-kv span{{color:var(--txt2)}}
.xc-kv b{{color:var(--txt);font-weight:650}}
.xc-typing{{display:flex;align-items:center;gap:10px;margin:14px 0;color:var(--txt2);font-size:13px}}
.xc-typing .dot{{width:8px;height:8px;border-radius:50%;background:var(--acc1);
  animation:xcblink 1.2s infinite both}}
.xc-typing .dot:nth-child(2){{animation-delay:.2s}}
.xc-typing .dot:nth-child(3){{animation-delay:.4s}}
@keyframes xcblink{{0%,80%,100%{{opacity:.25}}40%{{opacity:1}}}}

/* 聊天输入框（st.chat_input）主题适配：干掉白底/黑底错乱 */
/* 外层容器及所有 div/span 强制背景色，避免 Streamlit 某层 wrapper 白底 */
[data-testid="stChatInput"],
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"] {{
  background: var(--input-bg) !important;
  border-color: var(--input-border) !important;
}}
[data-testid="stBottomBlockContainer"] {{
  border-top: 1px solid var(--border) !important;
}}
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] form > div,
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div,
[data-testid="stChatInput"] > div > div > div,
[data-testid="stChatInput"] div,
[data-testid="stChatInput"] span:not([data-testid*="Icon"]):not([data-baseweb="textarea"]) {{
  background: var(--input-bg) !important;
  border-color: var(--input-border) !important;
}}
[data-testid="stChatInput"] [data-baseweb],
[data-testid="stChatInput"] [data-baseweb] * {{
  background: var(--input-bg) !important;
  color: var(--input-txt) !important;
  border-color: var(--input-border) !important;
}}
[data-testid="stChatInput"] {{
  border: 1px solid var(--input-border) !important;
  border-radius: 14px !important;
  box-shadow: 0 4px 16px rgba(0,0,0,.12) !important;
  padding: 0 !important;
}}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus,
[data-testid="stChatInput"] .stTextArea textarea,
[data-testid="stChatInput"] .stTextArea textarea:focus,
[data-testid="stChatInputTextArea"] textarea,
[data-testid="stChatInputTextArea"] textarea:focus,
[data-testid="stChatInput"] input,
[data-testid="stChatInput"] input:focus {{
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
            f'<div class="xc-col"><div class="xc-who">'
            f'<span class="xc-name">{esc(username)}</span>'
            f'<span class="xc-role xc-role-user">你问</span></div>'
            f'<div class="xc-bubble xc-user-bubble">{esc(m.get("content", ""))}</div>'
            f'</div><div class="xc-av xc-user-av">{_avatar_text(username)}</div></div>',
            unsafe_allow_html=True,
        )
        return

    # tool 卡片（MCP 工具返回的结构化数据透视）
    if m.get("role") == "tool":
        render_tool_card(m.get("tool", ""), m.get("payload") or {})
        return

    # assistant
    # 加法式空态守卫：content 偶发为空（如后端返回了空回答 / 任务中断），
    # 原逻辑会渲染一个空白气泡；这里给一个友好占位，避免用户看到「什么都没有」。
    _content = m.get("content") or ""
    if not str(_content).strip():
        _content = "（星辰 AI 暂未返回内容，请稍后重试或换个问法）"
    st.markdown(
        '<div class="xc-msg"><div class="xc-av">🌟</div>'
        '<div class="xc-col"><div class="xc-who">'
        '<span class="xc-name">星辰 AI</span><span class="xc-role">助手</span>'
        '</div>'
        f'<div class="xc-bubble">{_md_to_html(_content)}</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    # 快捷追问 chips（仅欢迎语且尚无用户发言时展示）
    chips = m.get("chips") or []
    if chips and len(st.session_state.get("xc_messages", [])) <= 1:
        _render_chips(chips)


# ══════════════════════════════════════════════════════
# 工具卡片：把 MCP 工具返回的结构化数据渲染为「数据透视」卡片
# （与 ai_answer 的自然语言回答并存，作为可核验的真实数据补充）
# ══════════════════════════════════════════════════════

_TOOL_TITLE = {
    "smart_pick": "📊 智能选股结果",
    "run_backtest": "📈 策略回测结果",
    "fund_flow": "💰 资金流向",
    "risk_assess": "⚠️ 风险评估",
    "stock_news": "📰 个股新闻",
    "portfolio_query": "💼 持仓查询",
    "conditional_orders": "📋 条件单",
    "analyze_technical": "🔬 技术面分析",
    "get_kline": "📉 行情数据",
    "get_realtime_quote": "⚡ 实时盘口",
    "get_market_sentiment": "🌡️ 市场情绪温度计",
}


def render_tool_card(tool: str, payload: dict) -> None:
    """渲染一个 MCP 工具卡片（左侧 assistant 风格，带工具标识）。"""
    title = _TOOL_TITLE.get(tool, "🔧 工具结果")
    if isinstance(payload, dict) and ("ok" in payload or "error" in payload):
        ok = payload.get("ok")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        err = payload.get("error")
    else:
        ok, data, err = True, payload, None

    if not ok or err:
        body = f'<div class="xc-tool-err">⚠️ {esc(str(err or "调用失败"))}</div>'
    else:
        body = _tool_payload_to_html(tool, data or {})

    st.markdown(
        '<div class="xc-msg"><div class="xc-av">🛠️</div>'
        '<div class="xc-col"><div class="xc-who">'
        f'<span class="xc-name">星辰 AI · 工具</span>'
        f'<span class="xc-role xc-role-tool">{esc(title)}</span></div>'
        f'<div class="xc-bubble xc-tool-card">{body}</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _tool_payload_to_html(tool: str, data: dict) -> str:
    """把各类工具结果 dict 转成紧凑 HTML 表格/列表。"""
    if not data:
        return '<div class="xc-tool-err">（无数据）</div>'
    rows = []
    if tool == "smart_pick":
        picks = data.get("picks") or []
        if not picks:
            return f'<div class="xc-tool-err">未选出标的（策略：{esc(str(data.get("strategy","")))}）</div>'
        for p in picks[:8]:
            nm = esc(str(p.get("name", p.get("code", ""))))
            sc = esc(str(p.get("score", "")))
            rs = esc(str(p.get("reason", "") or p.get("signal", "")))
            rows.append(f"<tr><td>{nm}</td><td>{sc}</td><td>{rs}</td></tr>")
        return (
            '<table class="xc-tool-tbl"><thead><tr><th>标的</th><th>评分</th><th>信号</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
        )
    if tool in ("analyze_technical", "risk_assess"):
        for k, v in list(data.items())[:10]:
            rows.append(f"<tr><td>{esc(str(k))}</td><td>{esc(str(v))}</td></tr>")
        return '<table class="xc-tool-tbl"><tbody>' + "".join(rows) + "</tbody></table>"
    if tool == "fund_flow":
        for k in ("code", "name", "main_net_inflow", "northbound", "summary"):
            if k in data:
                rows.append(f"<tr><td>{esc(k)}</td><td>{esc(str(data[k]))}</td></tr>")
        return '<table class="xc-tool-tbl"><tbody>' + "".join(rows) + "</tbody></table>"
    if tool == "run_backtest":
        for k in ("code", "strategy", "total_return", "win_rate", "sharpe", "trades", "summary"):
            if k in data:
                rows.append(f"<tr><td>{esc(k)}</td><td>{esc(str(data[k]))}</td></tr>")
        return '<table class="xc-tool-tbl"><tbody>' + "".join(rows) + "</tbody></table>"
    if tool == "stock_news":
        items = data.get("news") or data.get("items") or []
        if not items:
            return '<div class="xc-tool-err">（暂无新闻）</div>'
        for it in items[:6]:
            t = esc(str(it.get("title", "")))
            d = esc(str(it.get("date", it.get("time", ""))))
            rows.append(f'<tr><td>{t}</td><td>{d}</td></tr>')
        return '<table class="xc-tool-tbl"><thead><tr><th>标题</th><th>时间</th></tr></thead>' \
               f'<tbody>{"".join(rows)}</tbody></table>'
    if tool in ("portfolio_query", "conditional_orders"):
        if data.get("error"):
            return f'<div class="xc-tool-err">{esc(str(data["error"]))}</div>'
        items = data.get("orders") or data.get("positions") or data.get("accounts") or []
        if isinstance(items, list) and items:
            for it in items[:8]:
                if isinstance(it, dict):
                    cells = "".join(f"<td>{esc(str(v))}</td>" for v in it.values())
                    rows.append(f"<tr>{cells}</tr>")
            return '<table class="xc-tool-tbl"><tbody>' + "".join(rows) + "</tbody></table>"
        for k, v in list(data.items())[:10]:
            rows.append(f"<tr><td>{esc(str(k))}</td><td>{esc(str(v))}</td></tr>")
        return '<table class="xc-tool-tbl"><tbody>' + "".join(rows) + "</tbody></table>"
    if tool == "get_realtime_quote":
        # 实时盘口：A 股红涨绿跌语义着色（change_pct>0 红，<0 绿）
        cp = data.get("change_pct")
        cur = data.get("current")
        color = "#ff4d4f" if (cp is not None and cp > 0) else ("#00d486" if (cp is not None and cp < 0) else "#999")
        head = ""
        if cur is not None:
            sign = "+" if (cp is not None and cp > 0) else ""
            cp_txt = f"{sign}{cp:.2f}%" if cp is not None else ""
            chg_txt = f"{sign}{data.get('change', 0):.2f}" if cp is not None else ""
            head = (f'<div style="font-size:18px;font-weight:700;color:{color}">'
                    f'{esc(str(cur))} <span style="font-size:13px">{chg_txt} {cp_txt}</span></div>')
        meta = (f'<div style="color:#aaa;font-size:12px;margin:4px 0">'
                f'{esc(str(data.get("name", "")))} · {esc(str(data.get("ticker", "")))}'
                f' · {esc(str(data.get("datetime", "")))}</div>')
        # 市场时段徽标：收盘后/周末查到的是上一交易日快照，明确提示避免误读为实时价
        ms = data.get("market_status_hint")
        if ms:
            _ms_cold = any(k in ms for k in ("收盘", "周末", "休市", "盘前"))
            _ms_color = "#f59e0b" if _ms_cold else "#00d486"
            meta += (f'<div style="display:inline-block;margin-top:2px;padding:1px 8px;'
                     f'border-radius:10px;font-size:11px;color:{_ms_color};'
                     f'border:1px solid {_ms_color}55">{esc(str(ms))}</div>')
        kv = [
            ("今开", data.get("open")), ("昨收", data.get("prev_close")),
            ("最高", data.get("high")), ("最低", data.get("low")),
            ("成交量", data.get("volume")), ("成交额", data.get("amount")),
        ]
        kv_html = "".join(
            f'<div class="xc-kv"><span>{esc(str(k))}</span><b>{esc(str(v))}</b></div>'
            for k, v in kv if v is not None
        )
        return head + meta + f'<div class="xc-kv-grid">{kv_html}</div>'
    if tool == "get_market_sentiment":
        # 市场情绪温度计：0-100 大数字 + 视觉温度条 + 8 项指标（中文名）
        temp = data.get("temperature")
        label = data.get("temperature_label", "")
        bar_color = "#ff4d4f" if temp is not None and temp >= 55 else ("#00d486" if temp is not None and temp < 45 else "#f59e0b")
        if temp is not None:
            pct = max(0, min(100, float(temp)))
            head = (
                f'<div style="font-size:22px;font-weight:700;color:{bar_color}">'
                f'温度计 {temp:.0f} <span style="font-size:13px;color:#aaa">{esc(str(label))}</span></div>'
                f'<div style="height:8px;border-radius:6px;background:rgba(125,140,180,.2);'
                f'margin:6px 0 2px;overflow:hidden">'
                f'<div style="height:100%;width:{pct:.0f}%;border-radius:6px;'
                f'background:{bar_color};transition:width .4s"></div></div>'
                f'<div style="font-size:11px;color:#888">冰点 0 ───── 中性 50 ───── 亢奋 100</div>'
            )
        else:
            head = '<div class="xc-tool-err">（温度计不可用）</div>'
        inds = data.get("indicators") or {}
        # 中文名映射（避免用户看到 up_count 这类内部键）
        try:
            from modules.shepherd import THRESHOLDS as _SHEP_TH
            _name_map = {k: _SHEP_TH.get(k, {}).get("name", k) for k in inds}
        except Exception:
            _name_map = {k: k for k in inds}
        ind_html = "".join(
            f'<div class="xc-kv"><span>{esc(str(_name_map.get(k, k)))}</span><b>{esc(str(v))}</b></div>'
            for k, v in inds.items()
        )
        unavail = data.get("meta", {}).get("unavailable") or []
        warn = (f'<div class="xc-tool-err" style="margin-top:6px">部分数据缺失：{esc(", ".join(unavail))}</div>'
                if unavail else "")
        return head + f'<div class="xc-kv-grid" style="margin-top:6px">{ind_html}</div>' + warn
    for k, v in list(data.items())[:10]:
        rows.append(f"<tr><td>{esc(str(k))}</td><td>{esc(str(v))}</td></tr>")
    return '<table class="xc-tool-tbl"><tbody>' + "".join(rows) + "</tbody></table>"


def _render_chips(options):
    cols = st.columns(len(options))
    for i, o in enumerate(options):
        if cols[i].button(o["label"], key=f"xc_chip_{i}", use_container_width=True,
                          help="点击直接把该问题发送给星辰 AI"):
            st.session_state["_xc_pending"] = o["prompt"]
            # fragment 内严禁裸 rerun（会整页变暗卡死）；限定作用域为本 fragment
            st.rerun(scope="fragment")


def _tutorial_example_buttons():
    """使用指南里的可点击示例：点击直接把问题塞给星辰 AI（顶层 rerun 触发提交）。"""
    examples = [
        ("🔍 个股诊断", "太极实业 600667 怎么样？"),
        ("📊 横向对比", "对比 贵州茅台 和 五粮液 谁更值得买"),
        ("⚡ 实时盘口", "600519 现在实时价格和盘口怎么样"),
        ("🌡️ 市场情绪", "现在市场情绪如何，温度计到冰点了吗"),
    ]
    cols = st.columns(2)
    for i, (label, prompt) in enumerate(examples):
        if cols[i % 2].button(label, key=f"xc_tut_ex_{i}", use_container_width=True,
                              help=f"点击直接问：{prompt}"):
            st.session_state["_xc_pending"] = prompt
            st.rerun()  # 顶层 rerun：整页重跑让 fragment_chat 读取 _xc_pending 并提交


def render_ai_tutorial():
    """星辰 AI 新手教程模块：首次使用引导（纯展示层，不改动任何业务逻辑）。"""
    with st.expander("📘 使用指南 · 第一次用星辰 AI 看这里", expanded=False):
        st.markdown(
            "**🎯 你能问什么**\n"
            "- **个股诊断**：*太极实业 600667 怎么样？*\n"
            "- **横向对比**：*对比贵州茅台和五粮液谁更值得买*\n"
            "- **实时盘口**：*600519 现在实时价格和盘口怎么样*\n"
            "- **市场情绪**：*现在市场情绪如何，温度计到冰点了吗*\n"
            "- **事件解读**：*最近半导体有哪些重要事件？*\n"
            "- **持仓 / 仓位建议**：*当前市场环境下适合建仓吗？*\n\n"
            "**📦 怎么区分问答**\n"
            "- 你的提问会显示在 **右侧蓝色方框** 里、带「**你问**」标签；\n"
            "- 星辰 AI 的回复在 **左侧 🌟 气泡** 里，一眼分清谁说的。\n\n"
            "**🧹 常用按钮**\n"
            "- 顶部「🗑️ 清空」：重开一轮干净对话；\n"
            "- 右下角「▼ 回到底部」：快速跳到最新消息。\n\n"
            "**💾 其它**\n"
            "- 对话按你的账号保存，**刷新页面不丢失**；\n"
            "- 回复为模型推演，**不构成投资建议**，请独立判断。\n\n"
            "下面 4 个示例点一下就能直接问 👇"
        )
        _tutorial_example_buttons()


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
        # 深层守卫：后端历史偶发含结构损坏条目（非 dict / 缺 role），
        # render_message 中 m.get 会抛 AttributeError；只保留合法会话条目
        valid = [m for m in msgs if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        st.session_state["xc_messages"] = valid if valid else [dict(WELCOME)]


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
render_user_badge(sidebar=True)  # 在左侧边栏底部显示用户头像 / 退出登录

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
        '<div style="display:flex;align-items:center;gap:10px">'
        f'{STAR_AI_LOGO(26)}'
        '<span style="font-size:22px;font-weight:800;color:var(--txt)">星辰 AI</span>'
        '<span style="font-size:13px;color:var(--txt2)">对话 + 分析一体 · A股分析搭档</span>'
        '</div>',
        unsafe_allow_html=True,
    )
with h_right:
    _ck = "xc_clear_confirm"
    if st.session_state.get(_ck):
        if st.button("确认清空", key="xc_clear_cfm", type="primary", use_container_width=True, help="确认清空对话"):
            st.session_state["xc_messages"] = [dict(WELCOME)]
            st.session_state["xc_task_id"] = None
            st.session_state["xc_task_started_at"] = None
            st.session_state.pop(_ck, None)
            st.rerun()
        if st.button("取消", key="xc_clear_cancel", use_container_width=True):
            st.session_state.pop(_ck, None)
    else:
        if st.button("🗑️ 清空", key="xc_clear", use_container_width=True, help="清空对话"):
            st.session_state[_ck] = True

st.markdown(
    '<div class="xc-banner">💡 我可独立拉取行情 / 基本面 / 事件数据并给出研判；'
    '当前页面的对比组合或个股会自动作为上下文。回复为模型推演，不构成投资建议。</div>',
    unsafe_allow_html=True,
)

# 星辰 AI 新手教程模块（纯展示，不改动业务逻辑）
render_ai_tutorial()

# 加法式结果计数/摘要：对话消息总条数
st.caption(f"💬 当前对话共 {len(st.session_state.get('xc_messages', []))} 条消息")

# 加法式风险提示/免责声明（页面顶部独立标注，不影响既有 banner 文案）
st.caption("⚠️ 数据仅供参考，不构成投资建议；AI 回答为模型推演，请独立判断。")

# 加法式数据来源标注
st.caption("📡 数据来源：东方财富 / 新浪财经 / 公开财经资讯（经后端 ai_consult 任务聚合）")

# 加法式页面间快捷跳转：关联功能页（新增，不改动既有布局）
st.markdown("**🔗 相关页面**")
_pc1, _pc2, _pc3 = st.columns(3)
with _pc1:
    st.page_link("pages/1_行情看板.py", label="→ 行情看板")
with _pc2:
    st.page_link("pages/个股研究.py", label="→ 个股研究")
with _pc3:
    st.page_link("pages/L_消息中心.py", label="→ 消息中心")

# 加法式示例数据预览：只读示例回答（不写库、不改逻辑）
with st.expander("👀 查看示例回答（只读）", expanded=False):
    st.caption("以下为示例，仅展示 AI 可能的回答风格，非真实数据。")
    st.markdown(
        _md_to_html(
            "**【个股诊断示例】太极实业(600667)**\n\n"
            "- 近期量能温和放大，资金面偏积极；\n"
            "- 半导体板块情绪回暖，存在事件催化；\n"
            "- 风险提示：估值已不便宜，注意追高回撤。\n\n"
            "> 以上为示例文本，实际回答以你提问后的模型推演为准。"
        ),
        unsafe_allow_html=True,
    )

# 加法式最近浏览历史：展示最近在对话中提及的 6 位股票代码（纯前端 session，不接后端）
_xc_recent = st.session_state.get("xc_recent_stocks", [])
if _xc_recent:
    st.markdown("**🕘 最近浏览**")
    _rc = st.columns(min(len(_xc_recent), 6))
    for _i, _code in enumerate(_xc_recent[:6]):
        if _rc[_i].button(f"📈 {_code}", key=f"xc_recent_{_i}", help="向星辰 AI 追问该股票"):
            st.session_state["_xc_pending"] = f"{_code} 怎么样？"
            st.rerun()

# ── 渲染历史 ──
@safe_fragment("AI 对话")
def fragment_chat():
    for idx, m in enumerate(st.session_state["xc_messages"]):
        render_message(m, idx, username)

    # ── 思考中占位（含已等待时长 + 免费模型延迟提示，管理预期、提升感知效率）──
    if st.session_state.get("xc_task_id"):
        _started = st.session_state.get("xc_task_started_at") or time.time()
        _elapsed = int(time.time() - _started)
        _mm = _elapsed // 60
        _ss = _elapsed % 60
        _elapsed_str = f"{_mm}分{_ss:02d}秒" if _mm else f"{_ss}秒"
        st.markdown(
            f'<div class="xc-typing"><span class="dot"></span><span class="dot"></span>'
            f'<span class="dot"></span>'
            f'<span>星辰 AI 正在分析…（已等待 {_elapsed_str} · 当前使用免费模型，响应较慢属正常，请稍候）</span></div>',
            unsafe_allow_html=True,
        )

    # ── 回到底部按钮：由 apply_theme() 注入的 inject_scroll_nav 在首次
    #    components.html 中创建视口级浮动 ▼（right:24px;bottom:110px），
    #    以本页 st.chat_input 的 testid=stChatInput 存在性驱动出现/消失 ──

    # ── 收集输入 ──
    prompt = None
    if "_xc_pending" in st.session_state:
        prompt = st.session_state.pop("_xc_pending")
    user_text = st.chat_input(
        "问星辰 AI…（Enter 发送 / Shift+Enter 换行）",
        placeholder="例如：太极实业 600667 怎么样？",
    )
    if user_text:
        prompt = user_text

    # ── 提交后台任务 ──
    if prompt:
        # 守卫：上一轮分析仍在后台运行时禁止再堆叠新任务（否则覆盖 xc_task_id、
        # 丢掉前次结果并制造并发请求）；给出引导而非静默吞掉输入
        # 加法式：进入新一轮提交即清除上一轮失败重试标记，避免旧错误 UI 残留
        st.session_state.pop("_xc_failed_prompt", None)
        if st.session_state.get("xc_task_id"):
            st.session_state["xc_messages"].append(
                {"role": "assistant", "content": "⏳ 上一轮分析仍在进行中，请稍候它完成后再提问。"}
            )
            st.rerun(scope="fragment")
        st.session_state["xc_messages"].append({"role": "user", "content": prompt})
        # 加法式：意图识别 → 命中的结构化请求直接走 MCP 工具网关拿真实数据，
        # 渲染为「数据透视」卡片，与后台 ai_answer 的自然语言回答并存、互为补充。
        # 仅当置信度足够高（有明确标的或无需标的）才拦截，否则仍交后台 AI 自由回答。
        _intent = detect_intent(prompt)
        if _intent["tool"] and _intent["confidence"] >= 0.85:
            _tool_res = call_tool(_intent["tool"], **_intent["params"])
            st.session_state["xc_messages"].append(
                {"role": "tool", "tool": _intent["tool"], "payload": _tool_res}
            )
        # 加法式最近浏览历史：从用户提问中抽取 6 位股票代码，记录最近查看的标的
        # （纯前端 session，不接后端；仅追加到 session_state，fragment 内禁裸 rerun）
        for _code in re.findall(r"\b\d{6}\b", prompt):
            _rs = st.session_state.setdefault("xc_recent_stocks", [])
            if _code in _rs:
                _rs.remove(_code)
            _rs.insert(0, _code)
        st.session_state["xc_recent_stocks"] = st.session_state.get("xc_recent_stocks", [])[:8]
        history = [
            {"role": mm.get("role"), "content": mm.get("content", "")}
            for mm in st.session_state["xc_messages"][:-1]
            if isinstance(mm, dict) and mm.get("role") in ("user", "assistant")
        ]
        ctx = _slim_context()
        ctx["history"] = history[-6:]
        # 加法式加载态反馈：提交后台 AI 任务属网络请求，用 spinner 提示等待
        with st.spinner("加载中…"):
            task_id, err = submit_task_with_error("ai_consult", {"question": prompt, "context": ctx})
        if task_id:
            st.session_state["xc_task_id"] = task_id
            st.session_state["xc_task_started_at"] = time.time()
            # 加法式操作成功反馈：已成功提交分析任务
            st.toast("✅ 已发送，星辰 AI 正在分析…")
            st.rerun(scope="fragment")
        else:
            # 加法式失败重试：提交失败时不塞入错误消息气泡，改为错误提示 + 重试按钮；
            # 点击重试会重新提交同一问题（仅置位 _xc_pending，由 fragment 内 rerun 触发，禁裸 rerun）。
            st.session_state["_xc_failed_prompt"] = prompt
            st.session_state["xc_task_id"] = None
            st.rerun(scope="fragment")

    # ── 加法式失败重试入口：后台任务提交失败时展示 ──
    if st.session_state.get("_xc_failed_prompt"):
        st.error("⚠️ 加载失败，请稍后重试")
        if st.button("🔄 重试", key="xc_retry_btn", use_container_width=True):
            st.session_state["_xc_pending"] = st.session_state.pop("_xc_failed_prompt")
            st.rerun(scope="fragment")



fragment_chat()

# ── 复制最近一次 AI 回答（便于摘录 / 分享）──
_xc_msgs = st.session_state.get("xc_messages", [])
_xc_last_ai = next(
    (m.get("content", "") for m in reversed(_xc_msgs)
     if m.get("role") == "assistant" and m.get("content")),
    "",
)
if _xc_last_ai and _xc_last_ai != WELCOME["content"]:
    with st.expander("📋 复制最近回答", expanded=False):
        st.code(_xc_last_ai, language="text")

# ── 轮询后台任务（收进 fragment，#402）──
# 等待期间 st_autorefresh 只让本片段每 1.5s 局部重跑，不再整页全量重跑
# （否则页面顶部鉴权/历史渲染/上下文构建会被反复执行，造成卡顿）。
# 任务终态（成功/失败/超时）才用 st.rerun(scope="app") 升级为一次整页重跑，
# 以在页面级重新渲染聊天消息——这是 fragment 铁律允许的唯一整页重跑时机。
@safe_fragment("AI 任务轮询")
def _poll_ai_task():
    task_id = st.session_state.get("xc_task_id")
    if not task_id:
        return
    # 外层兜底：轮询后端任务时若通信异常，避免整个对话 fragment 崩溃、
    # 并清理残留的「正在分析」占位状态，给出友好提示。
    try:
        task = poll_task(task_id, max_wait=0.4)
    except Exception as _e:
        st.session_state["xc_task_id"] = None
        st.session_state["xc_task_started_at"] = None
        st.warning(f"⚠️ 与后端通信异常，已取消本次分析：{_e}")
        st.rerun(scope="app")
        return
    if task and task.get("status") == "success":
        result = task.get("result") or {}
        answer = result.get("answer") or "AI 暂未给出回答"
        st.session_state["xc_messages"].append({"role": "assistant", "content": answer})
        st.session_state["xc_task_id"] = None
        st.session_state["xc_task_started_at"] = None
        st.rerun(scope="app")
    elif task and task.get("status") == "error":
        st.session_state["xc_messages"].append(
            {"role": "assistant", "content": f"❌ AI 分析失败：{task.get('error') or '未知错误'}"}
        )
        st.session_state["xc_task_id"] = None
        st.session_state["xc_task_started_at"] = None
        st.rerun(scope="app")
    else:
        started = st.session_state.get("xc_task_started_at") or time.time()
        if time.time() - started > 240:
            st.session_state["xc_messages"].append(
                {"role": "assistant", "content": "❌ AI 响应超时，请重新提问。"}
            )
            st.session_state["xc_task_id"] = None
            st.session_state["xc_task_started_at"] = None
            st.rerun(scope="app")
            return
        try:
            from modules.autorefresh import st_autorefresh

            st_autorefresh(interval=1500, limit=300, key="xc_autorefresh")
        except Exception:
            pass


if st.session_state.get("xc_task_id"):
    _poll_ai_task()

# 加法式相关推荐块：底部「你可能也关注」静态推荐（加法式，不改既有逻辑、不接后端）
with st.expander("🔗 你可能也关注（相关推荐）", expanded=False):
    st.caption("以下为静态推荐，点击可直接向星辰 AI 提问（仅前端，不接后端）。")
    _recs = [
        {"label": "📈 贵州茅台 600519", "prompt": "贵州茅台 600519 当前估值怎么样？"},
        {"label": "🔋 宁德时代 300750", "prompt": "宁德时代 300750 近期走势如何？"},
        {"label": "🏦 招商银行 600036", "prompt": "招商银行 600036 值得长期持有吗？"},
        {"label": "💡 当前市场情绪", "prompt": "当前 A股 市场情绪和风格偏向如何？"},
    ]
    _rcols = st.columns(len(_recs))
    for _i, _r in enumerate(_recs):
        if _rcols[_i].button(_r["label"], key=f"xc_rec_{_i}", use_container_width=True,
                             help="向星辰 AI 提问该推荐主题"):
            st.session_state["_xc_pending"] = _r["prompt"]
            st.rerun()

# 加法式可折叠帮助/FAQ（与 Batch13 行内 help 不同，这是折叠面板）
with st.expander("💡 使用说明 / 常见问题", expanded=False):
    st.markdown(
        "**如何使用星辰 AI？**\n"
        "- 在底部输入框输入问题，按 Enter 发送（Shift+Enter 换行）；\n"
        "- 可点击上方快捷问题 chips 直接提问；\n"
        "- 对话历史按账号在后端持久化，刷新不丢失。\n\n"
        "**常见问题**\n"
        "- Q：回答需要多久？A：当前使用免费模型，首次响应可能较慢，请耐心等待。\n"
        "- Q：数据从哪来？A：聚合东方财富 / 新浪财经等公开市场数据。\n"
        "- Q：回答可靠吗？A：均为模型推演，不构成投资建议，请独立判断。"
    )

# 加法式键盘快捷键提示（纯提示文案，不绑定真实快捷键）
with st.expander("⌨️ 快捷键", expanded=False):
    st.markdown(
        "- **Enter**：发送当前输入框内容\n"
        "- **Shift + Enter**：在输入框内换行\n"
        "- **R**：刷新页面重新加载对话（浏览器快捷键）\n"
        "- 对话历史自动保存，无需手动操作"
    )

# 全局市场异动面板（与 P_市场情绪 页共享同一组件）
fragment_market_alerts_panel()
