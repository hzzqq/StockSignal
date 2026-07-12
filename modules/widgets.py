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
def _ai_summary_compare(rows: list, question: str) -> str:
    """基于当前对比数据生成 AI 咨询简报（原多股对比页内逻辑，已全局化）。"""
    if not rows:
        return "请先完成一次多股对比，我再基于当前标的为你分析。"
    ranked = sorted(rows, key=lambda r: r["scores"]["composite"], reverse=True)
    best, worst = ranked[0], ranked[-1]
    avg = sum(r["scores"]["composite"] for r in rows) / len(rows)
    buy_count = sum(1 for r in rows if r["signal"] == "买入")
    sell_count = sum(1 for r in rows if r["signal"] == "卖出")
    names = "、".join(r["name"] for r in rows)
    return (
        f"**★ 星辰 · 多市场智能股票分析师**\n\n"
        f"当前组合：{names}（共 {len(rows)} 只）。\n\n"
        f"- 平均综合评分：**{avg:.0f}** 分\n"
        f"- 最强标的：**{best['name']}（{best['scores']['composite']} 分，{best['signal']}）**\n"
        f"- 最弱标的：**{worst['name']}（{worst['scores']['composite']} 分，{worst['signal']}）**\n"
        f"- 信号分布：买入 {buy_count} / 持有 {len(rows) - buy_count - sell_count} / 卖出 {sell_count}\n\n"
        f"**建议：** 优先关注 {best['name']}，其在趋势/动量维度领先；"
        f"{worst['name']} 评分偏弱，建议谨慎。\n\n"
        f"*关于你的问题「{question or '组合分析'}」：* 以上为基于量价与基本面的模型推演，"
        f"不构成投资建议，请独立决策并控制仓位。"
    )


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


def _ai_answer(rows, question, name=None, verdict=None, score=None) -> str:
    if rows:
        return _ai_summary_compare(rows, question)
    if name:
        ctx = f"（综合研判：{verdict}，评分 {score}）" if verdict else ""
        return (
            f"**★ 星辰 · 多市场智能股票分析师**\n\n"
            f"你正在查看 **{name}** 的深度分析{ctx}。\n\n"
            f"关于「{question}」：建议结合技术面趋势/动量、情报面事件催化与仓位纪律综合判断；"
            f"本页已给出支撑压力与分批作战计划，可作为决策参考。\n\n"
            f"*以上为模型推演，不构成投资建议。*"
        )
    return (
        f"**★ 星辰 · 多市场智能股票分析师**\n\n"
        f"关于「{question or '投资分析'}」：我可基于量价、基本面与事件催化为你做横向对比与归因。"
        f"请进入「多股对比」组建组合，或在「个股分析」查看单只标的后，再来问我，"
        f"我会结合当前数据给出更具体的结论。\n\n"
        f"*以上为模型推演，不构成投资建议。*"
    )


def render_ai_consultant() -> None:
    """全局 AI 咨询模块（右上角弹层内）：任意页面可用，自动读取当前对比/个股上下文。"""
    st.markdown("#### ★ 星辰 · 多市场智能股票分析师")
    # 当前上下文提示，让用户知道 AI 正基于什么在答
    rows = st.session_state.get("_cmp_rows")
    name, verdict, score = _current_stock_context()
    if rows:
        st.caption(f"📊 当前对比 {len(rows)} 只标的，我会基于组合数据分析。")
    elif name:
        st.caption(f"🎯 当前个股：{name}，我会结合本页研判分析。")
    else:
        st.caption("输入问题即可。进入「多股对比 / 个股分析」后我能给出更具体结论。")
    with st.form("ai_consult_global"):
        q = st.text_area(
            "AI 咨询",
            value=st.session_state.get("ai_consult_q", ""),
            placeholder="例如：这组合里谁最值得买？风险在哪？",
            height=80,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("🚀 咨询", use_container_width=True)
    if submitted:
        st.session_state["ai_consult_q"] = q
    qa = st.session_state.get("ai_consult_q")
    if qa:
        st.markdown(
            _ai_answer(rows, qa, name, verdict, score),
            unsafe_allow_html=True,
        )


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
