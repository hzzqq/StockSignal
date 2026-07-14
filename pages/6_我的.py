"""
页面6：我的
个人信息入口、我的自选股、快捷操作。
"""

import streamlit as st
import requests
from datetime import datetime

from modules.session import require_auth, render_user_badge, safe_switch_page, API_BASE, get_user, get_token
from modules.ui_theme import get_current_mode, FONT_SCALE, FONT_DEFAULT

st.set_page_config(page_title="我的", page_icon="👤", layout="wide")
st.session_state["_active_page"] = __file__

# 确保 theme_mode 在 require_auth()/apply_theme() 之前就有默认值，避免默认 light 与后面被改回 dark 造成闪烁/状态错位
st.session_state.setdefault("theme_mode", "light")

st.title("👤 我的")
require_auth()
render_user_badge(sidebar=True)

user = get_user() or {}


def render_preferences():
    """偏好设置（由独立的设置页合并而来）。

    提供暗夜/白天模式切换、K线默认参数、数据源优先级等个性化设置。
    所有设置存储在 session_state 中，切换即时生效（st.rerun）。
    """
    # ── 初始化设置项的 session_state 默认值 ──
    _SETTINGS_KEYS = {
        "theme_mode": "light",          # dark / light（项目约定默认白天模式）
        "font_size": FONT_DEFAULT,      # small / medium(标准) / large / xlarge / xxlarge
        "kline_default_count": 120,     # K线默认显示根数
        "sector_refresh_interval": 60,  # 行业板块刷新间隔(秒)
    }
    for _key, _default in _SETTINGS_KEYS.items():
        if _key not in st.session_state:
            st.session_state[_key] = _default

    # ── 当前模式指示器 ──
    _current = get_current_mode()
    _mode_icon = "🌙" if _current == "dark" else "☀️"
    _mode_label = "暗夜模式" if _current == "dark" else "白天模式"

    col_ind1, col_ind2 = st.columns([2, 8])
    with col_ind1:
        st.markdown(f"<h3 style='margin:0;'>{_mode_icon} {_mode_label}</h3>", unsafe_allow_html=True)
    with col_ind2:
        st.progress(100 if _current == "dark" else 33, text="当前主题")

    st.markdown("---")

    # ════════════════════════════════════
    # 🎨 外观设置
    # ════════════════════════════════════
    st.subheader("🎨 外观设置")

    col_dark, col_light = st.columns(2)
    with col_dark:
        if st.button(
            "🌙 暗夜模式",
            type="primary",
            use_container_width=(st.session_state["theme_mode"] == "dark"),
            help="专业交易终端风格 · OLED暗色背景 + 金色点缀",
        ):
            st.session_state["theme_mode"] = "dark"
            st.rerun()
    with col_light:
        if st.button(
            "☀️ 白天模式",
            use_container_width=(st.session_state["theme_mode"] != "dark"),
            help="清爽金融仪表盘风格 · 浅灰白底 + 蓝金点缀",
        ):
            st.session_state["theme_mode"] = "light"
            st.rerun()

    st.caption("提示：切换后整个界面会立即刷新，无需手动操作。")

    # 字号档位：小 / 标准(原“中”) / 大 / 特大 / 巨大，至少 5 档。
    # 名称与 rem 数值均来自 ui_theme.FONT_SCALE 唯一数据源，保证与全局注入一致。
    _font_cn = {"small": "小", "medium": "标准", "large": "大", "xlarge": "特大", "xxlarge": "巨大"}
    _font_opts = {k: (v, FONT_SCALE[k]) for k, v in _font_cn.items()}
    _font_labels = {k: f"{v[0]} ({v[1]})" for k, v in _font_opts.items()}
    _font_current = st.selectbox(
        "字体大小",
        options=list(_font_opts.keys()),
        format_func=lambda x: _font_labels[x],
        index=list(_font_opts.keys()).index(st.session_state["font_size"]),
        key="setting_font_size",
        help="调整全局文字大小（影响标题、正文、表格等）。默认「标准」比旧版更大。",
    )
    if _font_current != st.session_state.get("font_size"):
        st.session_state["font_size"] = _font_current
        # 实际 CSS 注入由 ui_theme.apply_theme() 全局统一处理（覆盖 html/body/.stApp），
        # 这里仅更新设置并重跑，使全局字号立即生效。
        st.rerun()

    st.markdown("")

    # ════════════════════════════════════
    # 📊 行情看板默认参数
    # ════════════════════════════════════
    st.subheader("📊 行情看板默认参数")

    _kline_count = st.slider(
        "K 线图默认显示数量",
        min_value=20, max_value=500, step=10,
        value=int(st.session_state["kline_default_count"]),
        key="setting_kline_count",
        help="打开行情看板时，K线图默认展示的最近 N 根 K 线（可随时在页面上拖动滑块调整）",
    )
    if _kline_count != st.session_state["kline_default_count"]:
        st.session_state["kline_default_count"] = _kline_count

    _refresh_interval = st.slider(
        "行业板块自动刷新间隔（秒）",
        min_value=15, max_value=300, step=15,
        value=int(st.session_state["sector_refresh_interval"]),
        key="setting_refresh_interval",
        help="交易时间内行业板块数据的自动刷新频率。设为 300 秒则几乎不自动刷新",
    )
    if _refresh_interval != st.session_state["sector_refresh_interval"]:
        st.session_state["sector_refresh_interval"] = _refresh_interval

    st.markdown("")

    # ════════════════════════════════════
    # 🔧 数据源偏好
    # ════════════════════════════════════
    st.subheader("🔧 数据源偏好")

    st.info("""
    **StockSignal 数据源降级链**（按顺序尝试，第一个成功即用）：
    1. **akshare** — 最全、最快（推荐首选）
    2. **BaoStock** — 备选，稳定但较慢
    3. **新浪财经** — 快速但数据有限
    4. **东方财富** — 兜底源

    当某个数据源超时/报错时会自动切换到下一个。
    """)

    st.multiselect(
        "数据源优先级排序（拖动调整顺序）",
        options=["akshare", "BaoStock", "新浪财经", "东方财富"],
        default=["akshare", "BaoStock", "新浪财经", "东方财富"],
        key="setting_ds_order",
        help="数据获取时的尝试顺序（越靠前越优先使用）",
    )

    st.markdown("")

    # ════════════════════════════════════
    # 💾 重置与保存
    # ════════════════════════════════════
    st.subheader("💾 重置与保存")

    col_reset, col_save = st.columns([1, 3])
    with col_reset:
        if st.button("🗑️ 恢复默认设置", type="secondary"):
            for _key, _default in _SETTINGS_KEYS.items():
                st.session_state[_key] = _default
            st.rerun()
    with col_save:
        st.caption(
            "💡 所有设置已实时生效并保存在浏览器内存中。\n"
            "关闭或刷新浏览器后会恢复为默认值。"
        )

    st.markdown("---")
    with st.expander("📋 当前全部设置一览", expanded=False):
        import json as _json
        _summary = {k: st.session_state[k] for k in _SETTINGS_KEYS}
        st.json(_summary)

# ── 个人信息卡片 ──
col1, col2 = st.columns([1, 3])
with col1:
    st.markdown("### 🧑‍💼 当前用户")
    st.markdown(f"**用户名：** {user.get('username', '-')}")
    st.markdown(f"**角色：** {'管理员' if user.get('role') == 'admin' else '普通用户'}")
    st.markdown(f"**登录时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}")

with col2:
    st.markdown("### 快捷入口")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📈 行情看板", width="stretch"):
            safe_switch_page("pages/1_行情看板.py")
    with c2:
        if st.button("💰 仓位管理", width="stretch"):
            safe_switch_page("pages/5_仓位管理.py")
    with c3:
        if st.button("🔔 事件追踪", width="stretch"):
            safe_switch_page("pages/3_事件追踪.py")

st.markdown("---")

# ── 我的自选股 ──
st.subheader("⭐ 我的自选股")

try:
    resp = requests.get(
        f"{API_BASE}/api/watchlist",
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=5,
    )
    if resp.status_code == 200:
        body = resp.json()
        if body.get("status") == "ok" and body.get("data"):
            watchlist = body["data"]
            if watchlist:
                import pandas as pd
                df = pd.DataFrame(watchlist)
                st.dataframe(df, width="stretch")
            else:
                st.info("暂无自选股，请在行情看板中添加。")
        else:
            st.info("暂无自选股，请在行情看板中添加。")
    else:
        st.warning(f"获取自选股失败：HTTP {resp.status_code}")
except Exception as e:
    st.error(f"获取自选股失败：{e}")

st.markdown("---")

# ── 登录历史 ──
st.subheader("🕘 登录历史")

try:
    resp = requests.get(
        f"{API_BASE}/api/auth/logins",
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=5,
    )
    if resp.status_code == 200:
        body = resp.json()
        logs = (body.get("data") or []) if body.get("status") == "ok" else []
        if logs:
            import pandas as pd
            _hist = [
                {
                    "时间": (r.get("created_at", "")[:19].replace("T", " ")),
                    "账号": r.get("username", "-"),
                    "操作": r.get("action", "-"),
                    "详情": r.get("detail", "") or "—",
                }
                for r in logs
            ]
            st.dataframe(pd.DataFrame(_hist), width="stretch", use_container_width=True)
        else:
            st.info("暂无登录记录。")
    else:
        st.warning(f"获取登录历史失败：HTTP {resp.status_code}")
except Exception as e:
    st.error(f"获取登录历史失败：{e}")

st.markdown("---")

# ── 账号绑定（邮箱 / 手机） ──
st.subheader("🔗 账号绑定")

_col_mail, _col_phone = st.columns(2)
with _col_mail:
    st.markdown("**📧 邮箱绑定**")
    if st.button("绑定邮箱", key="bind_mail", use_container_width=True):
        st.info("邮箱绑定功能需在后端接入邮件服务后开放（当前为本地部署，暂未启用）。")
with _col_phone:
    st.markdown("**📱 手机号绑定**")
    if st.button("绑定手机", key="bind_phone", use_container_width=True):
        st.info("手机号绑定需接入短信网关，当前为本地部署，暂未启用。")

st.caption("说明：邮箱 / 手机号绑定用于找回密码与异地登录提醒，本地演示环境暂未接入第三方服务。")

st.markdown("---")

# ── 系统消息 / 通知占位 ──
st.subheader("📢 系统通知")
st.info("暂无新通知。")

# ------------------------------------------------------------------
# 偏好设置（原「设置」页合并而来，作为独立页签）
# ------------------------------------------------------------------
st.markdown("---")
_pref_tab, = st.tabs(["⚙️ 偏好设置"])
with _pref_tab:
    render_preferences()
