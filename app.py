"""
StockSignal 主入口
A股事件驱动投资分析平台
"""

import time
import urllib.request
import urllib.error

import requests
import streamlit as st

st.set_page_config(
    page_title="StockSignal · A股事件驱动投资分析平台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.session_state["_active_page"] = __file__

# ── 鉴权门禁：未登录直接跳到 /登录 ──
from modules.session import require_auth, render_user_badge, is_admin, get_user, safe_switch_page, get_token
from modules.widgets import render_global_search, render_theme_toggle, render_notifications, get_recent_stocks, render_session_countdown
require_auth()

user = get_user() or {}


def _check_backend():
    try:
        with urllib.request.urlopen("http://127.0.0.1:5050/api/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# ── 顶部状态栏 ──
st.title("📊 StockSignal · A股事件驱动投资分析平台")
st.caption("A股事件驱动投资分析平台 · 快速识别行情主线 · 回测事件驱动策略")

status_col1, status_col2, status_col3, status_col4 = st.columns(4)
with status_col1:
    role_label = "管理员" if user.get("role") == "admin" else "普通用户"
    st.metric(label="当前用户", value=user.get("username", "-"), delta=role_label, delta_color="off")
with status_col2:
    backend_ok = _check_backend()
    st.metric(label="后端服务", value="✅ 正常" if backend_ok else "❌ 异常")
with status_col3:
    st.metric(label="当前时间", value=time.strftime("%H:%M:%S"))
with status_col4:
    st.metric(label="版本", value="v1.0")

st.markdown("---")

# ── 功能模块卡片（与左侧边栏保持一致） ──
st.header("📦 功能模块")

modules = [
    {
        "title": "行情看板",
        "icon": "📈",
        "desc": "交互式 K线、均线、成交量、行业热力图与板块涨跌",
        "page": "pages/1_行情看板.py",
        "admin": False,
    },
    {
        "title": "个股分析",
        "icon": "🔍",
        "desc": "个股深度决策仪表盘：趋势、情绪、事件、作战计划",
        "page": "pages/2_个股分析.py",
        "admin": False,
    },
    {
        "title": "事件追踪",
        "icon": "🔔",
        "desc": "产业事件、价格信号、宏观数据三类信号综合评分与时间轴",
        "page": "pages/3_事件追踪.py",
        "admin": False,
    },
    {
        "title": "策略回测",
        "icon": "⚙️",
        "desc": "事件驱动 / 均线交叉策略回测，收益曲线与夏普比率",
        "page": "pages/4_策略回测.py",
        "admin": False,
    },
    {
        "title": "仓位管理",
        "icon": "💰",
        "desc": "持仓盈亏统计、持仓导入与 Excel 导出",
        "page": "pages/5_仓位管理.py",
        "admin": False,
    },
    {
        "title": "我的",
        "icon": "👤",
        "desc": "个人信息、自选股、偏好设置、外观与数据源配置",
        "page": "pages/6_我的.py",
        "admin": False,
    },
]

admin_modules = [
    {
        "title": "用户管理",
        "icon": "👥",
        "desc": "用户 CRUD、角色分配与操作日志",
        "page": "pages/7_用户管理.py",
        "admin": True,
    },
    {
        "title": "系统配置",
        "icon": "⚙️",
        "desc": "股票数据、缓存、系统参数与运行配置",
        "page": "pages/8_系统配置.py",
        "admin": True,
    },
]

# 普通用户功能模块
visible_modules = [m for m in modules if not m.get("admin", False)]
cols = st.columns(3)
for i, m in enumerate(visible_modules):
    with cols[i % 3]:
        with st.container(border=True):
            st.subheader(f"{m['icon']} {m['title']}")
            st.markdown(m["desc"])
            if st.button("进入 →", key=f"nav_{m['title']}", use_container_width=True, help=m["desc"]):
                safe_switch_page(m["page"])

# 管理员功能模块
if is_admin():
    st.markdown("---")
    st.header("🛡️ 管理后台")
    cols_admin = st.columns(3)
    for i, m in enumerate(admin_modules):
        with cols_admin[i % 3]:
            with st.container(border=True):
                st.subheader(f"{m['icon']} {m['title']}")
                st.markdown(m["desc"])
                if st.button("进入 →", key=f"nav_admin_{m['title']}", use_container_width=True):
                    safe_switch_page(m["page"])

st.markdown("---")

# ── 快捷入口 ──
st.markdown("---")
st.header("⚡ 快捷入口")

# 最近浏览（session_state 维护）
recent = get_recent_stocks()
if recent:
    st.subheader("🕘 最近浏览")
    rc = st.columns(min(len(recent), 4))
    for i, r in enumerate(recent[:4]):
        with rc[i]:
            if st.button(f"{r['code']}\n{r['name']}", key=f"recent_{r['code']}", use_container_width=True):
                safe_switch_page("pages/1_行情看板.py")

# 自选股数量 + 未读提醒（调后端）
try:
    wl_resp = requests.get(
        f"http://127.0.0.1:5050/api/watchlist",
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=5,
    )
    wl_count = len(wl_resp.json().get("data") or []) if wl_resp.status_code == 200 else 0
except Exception:
    wl_count = 0

ce1, ce2, ce3 = st.columns(3)
with ce1:
    st.metric("自选股", f"{wl_count} 只", help="在行情看板添加到自选股")
with ce2:
    st.metric("未读事件", "—", help="事件追踪模块的信号评分与提醒")
with ce3:
    st.metric("数据更新", time.strftime("%H:%M"), help="界面数据刷新时间")

# ── 项目简介（可折叠） ──
with st.expander("📖 项目简介", expanded=False):
    st.markdown("""
    StockSignal 是一款面向个人投资者的 **A股事件驱动分析工具**，通过整合三类核心催化信号：

    | 类型 | 说明 | 示例 |
    |------|------|------|
    | **产业事件** | 政策发布、行业并购、产能变化 | 光伏装机补贴、半导体设备禁令 |
    | **价格信号** | 大宗商品、上游原材料价格变动 | MLCC 涨价、煤炭港口价格 |
    | **宏观数据** | PMI、CPI、社融等关键宏观指标 | PMI 超预期 → 顺周期主线 |

    帮助用户**快速识别行情主线**、**可视化行业轮动**、**回测事件驱动策略**。
    """)

# ── 侧边栏 ──
with st.sidebar:
    # 全局股票搜索
    render_global_search()
    st.markdown("---")
    # 主题快速切换
    render_theme_toggle()
    st.markdown("---")
    # 通知中心
    render_notifications()
    st.markdown("---")

    st.header("导航")
    st.markdown("""
    **功能页面：**
    - 📈 行情看板（含板块涨跌）— K线、均线、成交量、行业板块
    - 🔍 个股分析 — 个股深度决策仪表盘
    - 🔔 事件追踪 — 信号评分、事件时间轴
    - ⚙️ 策略回测 — 事件驱动 / 均线交叉
    - 💰 仓位管理 — 持仓盈亏、Excel导出
    - 👤 我的（含偏好设置）— 个人信息、自选股、外观与数据源设置
    """)

    if is_admin():
        st.markdown("""
        **管理后台：**
        - 👥 用户管理 — 用户CRUD、操作日志
        - ⚙️ 系统配置 — 股票数据、系统配置
        """)

    st.markdown("---")
    render_session_countdown()
    st.markdown("---")
    render_user_badge(sidebar=True)

    # 角色标识
    if user.get("role") == "admin":
        st.success("🛡️ 管理员模式")
    else:
        st.info("👤 普通用户模式")

    st.caption("软件工程实训课程设计")
    st.caption("作者：hzz")
