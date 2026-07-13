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
import requests
import streamlit as st

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
        .ai-consult-wrap { background:#1a1a2e; color:#e2e8f0; padding:4px; border-radius:10px; }
        .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#e2e8f0 !important; }
        .ai-consult-wrap .stButton button { background:#667eea !important; color:#0f0f23 !important; }
        .ai-consult-wrap textarea { background:#15152a !important; color:#e2e8f0 !important; border-color:#2d2d44 !important; }
        .ai-consult-wrap textarea::placeholder { color:#64748b !important; }
        </style>
        """
    return """
    <style>
    .ai-consult-wrap { background:#ffffff; color:#111827; padding:4px; border-radius:10px; }
    .ai-consult-wrap .stMarkdown, .ai-consult-wrap .stMarkdown p { color:#111827 !important; }
    .ai-consult-wrap .stButton button { background:#d4a02a !important; color:#ffffff !important; }
    .ai-consult-wrap textarea { background:#ffffff !important; color:#111827 !important; border-color:#d1d5db !important; }
    .ai-consult-wrap textarea::placeholder { color:#9ca3af !important; }
    </style>
    """


def render_ai_consultant() -> None:
    """全局 AI 咨询模块（右上角弹层内）：任意页面可用，后台异步运行。"""
    st.markdown(_ai_popover_theme_css(), unsafe_allow_html=True)
    st.markdown('<div class="ai-consult-wrap">', unsafe_allow_html=True)
    st.markdown("#### ★ 星辰 · 多市场智能股票分析师")

    rows = st.session_state.get("_cmp_rows")
    name, verdict, score = _current_stock_context()
    if rows:
        st.caption(f"📊 当前对比 {len(rows)} 只标的，AI 会结合组合数据并独立拉取每只股票的量价/基本面分析。")
    elif name:
        st.caption(f"🎯 当前个股：{name}，AI 会独立拉取最新数据并给出研判。")
    else:
        st.caption("输入股票代码或名称，AI 会独立拉取数据并给出见解；也可先进入「个股分析/多股对比」获得更具体结论。")

    with st.form("ai_consult_global"):
        q = st.text_area(
            "AI 咨询",
            value=st.session_state.get("ai_consult_q", ""),
            placeholder="例如：太极实业怎么样？/ 这组合里谁最值得买？风险在哪？",
            height=80,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("🚀 咨询", use_container_width=True)

    if submitted and q:
        st.session_state["ai_consult_q"] = q
        # 提交后台任务，不阻塞当前页
        task_id = submit_task("ai_consult", {"question": q, "context": _slim_context()})
        if task_id:
            st.session_state["ai_task_id"] = task_id
            st.info("🤔 AI 已开始在后台思考，你可以继续操作或切到其他页面，完成后结果会保留在这里。")

    # 轮询后台任务状态
    task_id = st.session_state.get("ai_task_id")
    if task_id:
        task = poll_task(task_id, max_wait=0.4)
        if task and task.get("status") == "success":
            result = task.get("result") or {}
            st.session_state["ai_answer"] = result.get("answer", "AI 暂未给出回答")
            del st.session_state["ai_task_id"]
        elif task and task.get("status") == "error":
            st.session_state["ai_answer"] = f"❌ AI 分析失败：{task.get('error') or '未知错误'}"
            del st.session_state["ai_task_id"]
        elif task and task.get("status") in ("pending", "running"):
            st.info("🤔 AI 正在后台分析量价、基本面与事件… 你可以切到其他页面，完成后自动显示。")

    # 展示答案
    if st.session_state.get("ai_answer"):
        st.markdown("---")
        st.markdown(st.session_state["ai_answer"], unsafe_allow_html=True)

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
