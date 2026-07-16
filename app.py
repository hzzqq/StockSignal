"""
StockSignal 主入口
A股事件驱动投资分析平台
"""

import time
import urllib.request
import urllib.error

import requests
import streamlit as st

from modules.ui_theme import apply_page_config
apply_page_config(
    page_title="StockSignal · A股事件驱动投资分析平台",
    page_icon="📊",
    layout="wide"
)
st.session_state["_active_page"] = __file__

# ── 鉴权门禁：未登录直接跳到 /登录 ──
from modules.session import require_auth, render_user_badge, is_admin, get_user, safe_switch_page, get_token
from modules.widgets import render_global_search, render_theme_toggle, render_notifications, get_recent_stocks, render_session_countdown
from modules.fundflow import warm_fundflow_caches
require_auth()

# 性能加速：非阻塞后台预热全市场资金流缓存，首个资金流向类页面访问即命中缓存
warm_fundflow_caches()

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

# ── 功能模块卡片（分组，与左侧边栏自定义导航保持一致） ──
# 分组顺序对应日常操作流：看盘 → 选股 → 管仓 → 回测 → 交流 → 账户。
# 合并页：🎯个股研究＝股票选取+个股分析；💼持仓中心＝自选股监控+仓位管理+组合收益。
# 图标去重：📡事件追踪、🚨价格预警、🛠️系统配置。
st.header("📦 功能模块")

HOME_GROUPS = [
    ("📊 市场纵览", [
        ("🌅", "每日晨报", "pages/A_每日晨报.py", "开盘前速览：隔夜要闻、自选股快照、复盘笔记"),
        ("📈", "行情看板", "pages/1_行情看板.py", "指数迷你卡、行业板块涨跌榜、龙虎榜、相关性矩阵"),
        ("👁️", "智能盯盘", "pages/K_智能盯盘.py", "板块异动+自选涨跌+资金流+预警聚合，盘中自动刷新"),
        ("🌊", "资金流向", "pages/F_资金流向.py", "北向资金、板块资金流、大盘主力净流入、个股资金动向"),
        ("📡", "事件追踪", "pages/3_事件追踪.py", "产业事件、价格信号、宏观数据三类信号综合评分与时间轴"),
        ("📅", "财报日历", "pages/G_财报日历.py", "业绩报表、业绩预告、披露日历，按报告期查看"),
        ("🌈", "板块轮动", "pages/M_板块轮动.py", "行业板块热力图、涨跌排行与资金轮动视图"),
    ]),
    ("🔎 选股研究", [
        ("🎯", "个股研究", "pages/个股研究.py", "快速选取 + 深度分析二合一：K线/技术面/打分/决策仪表盘"),
        ("🧭", "形态选股", "pages/B_形态选股.py", "K线形态 + 金叉死叉 + 背离扫描，手动/自选池双模式"),
        ("🏛️", "基本面分析", "pages/E_基本面分析.py", "个股估值、历史分位、行业横向对比与大盘主线判断"),
        ("📊", "多股对比", "pages/2_多股对比.py", "同屏横向对比 ≥5 只股票：雷达图、VS 卡、分层操作建议"),
        ("🧰", "ETF筛选", "pages/O_ETF筛选.py", "按类型/涨跌/成交额筛选 ETF 与基金，支持排序"),
    ]),
    ("💼 我的持仓", [
        ("💼", "持仓中心", "pages/持仓中心.py", "自选池 + 持仓盈亏 + 收益归因三合一"),
        ("🩺", "体检扫描", "pages/I_体检扫描.py", "一键批量体检自选+持仓：技术形态、主力资金、预警清单"),
        ("🚨", "价格预警", "pages/9_价格预警.py", "自选股多维预警：价格/涨跌幅/量能/技术信号触发提醒"),
        ("📤", "数据导出", "pages/J_数据导出.py", "资金流/财报/组合/自选股统一 CSV 导出与一键打包"),
        ("🎮", "模拟交易", "pages/N_模拟交易.py", "虚拟资金买卖 A 股，跟踪持仓盈亏与净值曲线"),
    ]),
    ("🧪 策略工具", [
        ("⚙️", "策略回测", "pages/4_策略回测.py", "事件驱动 / 均线交叉策略回测，收益曲线与夏普比率"),
    ]),
    ("💬 社区与 AI", [
        ("🌟", "星辰 AI", "pages/🌟_星辰AI.py", "对话 + 分析一体：个股诊断、横向对比、事件解读、持仓建议"),
        ("💬", "股吧", "pages/D_股吧.py", "社区讨论：发表观点、评论点赞，可关联个股一键跳转"),
        ("🔔", "消息中心", "pages/L_消息中心.py", "聚合自选股异动、社区动态与系统通知，统一已读"),
    ]),
]


def _render_group(title, items):
    st.subheader(title)
    cols = st.columns(3)
    for i, (icon, name, page, desc) in enumerate(items):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{icon} {name}**")
                st.caption(desc)
                if st.button("进入 →", key=f"nav_{name}", use_container_width=True, help=desc):
                    safe_switch_page(page)


for _g, _items in HOME_GROUPS:
    _render_group(_g, _items)

# 账户组（所有用户可见「我的」，管理员额外可见后台）
acct_items = [
    ("👤", "我的", "pages/👤_我的.py", "个人信息、自选股、偏好设置、外观与数据源配置"),
]
if is_admin():
    acct_items += [
        ("👥", "用户管理", "pages/7_用户管理.py", "用户 CRUD、角色分配与操作日志"),
        ("🛠️", "系统配置", "pages/8_系统配置.py", "股票数据、缓存、系统参数与运行配置"),
    ]
st.markdown("---")
_render_group("👤 账户" + ("　·　管理后台" if is_admin() else ""), acct_items)

st.markdown("---")

# ── 快捷入口 ──
st.header("⚡ 快捷入口")

# 最近浏览（session_state 维护）
recent = get_recent_stocks()
if recent:
    st.subheader("🕘 最近浏览")
    rc = st.columns(min(len(recent), 4))
    for i, r in enumerate(recent[:4]):
        with rc[i]:
            if st.button(f"{r['code']}\n{r['name']}", key=f"recent_{r['code']}", use_container_width=True):
                safe_switch_page("pages/个股研究.py")

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
# 注：分组导航由 require_auth()→render_sidebar_nav() 在顶部自动注入，此处仅补充
#     全局搜索 / 通知中心 / 会话倒计时 / 用户徽标等辅助组件。
with st.sidebar:
    st.markdown("---")
    # 全局股票搜索
    render_global_search()
    st.markdown("---")
    # 通知中心
    render_notifications()
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
