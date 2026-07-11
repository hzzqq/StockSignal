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
