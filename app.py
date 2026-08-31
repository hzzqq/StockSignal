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
from modules import decision as _decision
from modules import shepherd as _sh
from modules import shepherd_ladder as _sl
from modules import shepherd_forecast as _sf
apply_page_config(
    page_title="StockSignal · A股事件驱动投资分析平台",
    layout="wide"
)
st.session_state["_active_page"] = __file__

# ── 鉴权门禁：未登录直接跳到 /登录 ──
from modules.session import require_auth, render_user_badge, is_admin, get_user, safe_switch_page, get_token
from modules.widgets import render_global_search, render_notifications, get_recent_stocks, render_session_countdown
from modules.fundflow import warm_fundflow_caches
require_auth()

# 性能加速：非阻塞后台预热全市场资金流缓存，首个资金流向类页面访问即命中缓存
warm_fundflow_caches()

user = get_user() or {}


@st.cache_data(ttl=15, show_spinner=False)
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


# ── 今日决策（情绪信号 → 仓位建议）──
# 只读本地快照 data/daily_snapshot.json，**零网络**：首页是打开频次最高的页面，
# 任何抓取都会拖慢首屏。快照由 scripts/daily_snapshot.py 每日收盘后落盘。
def _build_estimate_payload():
    """无收盘快照时的兜底载荷：只用本地数据（连板梯队历史 + 牧羊人本地缓存），零网络。

    返回与 daily_snapshot 同构的 dict，多一个 estimate=True 标记；has_signal 表示
    是否真的拿到了任一本地信号（否则估算无意义，回退到原空态提示）。
    """
    overall = None
    try:
        overall = _sl.ladder_promotion_rates().get("overall")
    except Exception:  # noqa: BLE001
        overall = None
    temp = None
    cycle_name = ""
    bias = "中性"
    score = None
    try:
        _df = _sh.get_shepherd_indicators(days=1)
        if _df is not None and not getattr(_df, "empty", True):
            _row = _df.iloc[-1].to_dict()
            temp = _sh.shepherd_temperature(_row)
            _fc = _sf.forecast_next_day(_row, None)
            _cyc = (_fc or {}).get("cycle") or {}
            cycle_name = _cyc.get("name", "")
            bias = (_fc or {}).get("bias", "中性")
            score = (_fc or {}).get("score")
    except Exception:  # noqa: BLE001
        pass  # 缓存缺失/网络受限：temp 留 None，derive_position 兜底 50
    pos = _decision.derive_position(temp, score, bias, cycle_name, overall)
    return {
        "date": "估算", "temperature": temp, "cycle": cycle_name, "bias": bias,
        "confidence": None, "position": pos, "overall": overall,
        "estimate": True, "has_signal": temp is not None or overall is not None,
    }


def _render_decision_card(payload, stale=False):
    pos = payload.get("position") or {}
    date = payload.get("date") or "-"
    temp = payload.get("temperature")
    estimate = payload.get("estimate", False)
    with st.container(border=True):
        if estimate:
            st.caption("📡 实时估算（尚未生成今日收盘快照，仅供参考）")
        elif stale:
            st.caption(f"⚠️ 快照日期 {date}，已超 20 小时未更新 —— 今天跑过 daily_snapshot.py 吗？")
        else:
            st.caption(f"数据日期 {date} · 由「市场温度 + 情绪周期 + 连板晋级率」透明推导")

        c1, c2, c3, c4, c5 = st.columns([1, 1.4, 1, 1.1, 1.1])
        with c1:
            st.metric("🌡️ 市场温度", f"{temp:.0f}" if temp is not None else "—",
                      help="牧羊人 17 项综合温度 0-100，越高越热")
        with c2:
            st.metric("🔄 情绪周期", payload.get("cycle") or "-",
                      help="六阶段定位：冰点 / 修复试探 / 修复确认 / 主升高潮 / 高潮分化 / 退潮")
        with c3:
            st.metric("🧭 次日方向", payload.get("bias") or "-",
                      delta=f"置信 {payload.get('confidence') or '-'}", delta_color="off")
        with c4:
            st.metric("📊 建议仓位", f"{pos.get('pct', '-')}%",
                      delta=pos.get("band") or "-", delta_color="off",
                      help="温度基准 + 方向/周期/晋级率调节，clamp 5~95%")
        with c5:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("🎯 决策面板 →", key="td_open", use_container_width=True,
                         help="看完整信号明细与推导理由，盘后可一键归档复盘"):
                safe_switch_page("pages/54_今日决策面板.py")

        reasons = pos.get("reasons") or []
        if reasons:
            with st.expander("仓位怎么算出来的", expanded=False):
                for r in reasons:
                    st.caption(f"· {r}")
                st.caption("⚠️ 由指标透明推导的概率参考，非确定性指令，不构成投资建议。")


def _render_today_decision():
    try:
        snap = _decision.load_snapshot()
    except Exception:  # noqa: BLE001
        return  # 首页绝不能因为读快照失败而崩

    st.header("🎯 今日决策")
    if not snap:
        # 兜底：用本地数据即时算估算仓位（零网络），避免每日开盘首页空白
        try:
            est = _build_estimate_payload()
        except Exception:  # noqa: BLE001
            est = None
        if not est or not est.get("has_signal"):
            st.info(
                "还没有决策快照。收盘后跑一次 `python scripts/daily_snapshot.py` 即可生成"
                "（建议配成每日定时任务），或进《今日决策面板》直接看实时读数。"
            )
            if st.button("🎯 打开今日决策面板 →", key="td_open_empty"):
                safe_switch_page("pages/54_今日决策面板.py")
            return
        _render_decision_card(est, stale=False)
        return

    _render_decision_card(snap, stale=_decision.is_stale())


_render_today_decision()

st.markdown("---")

# ── 功能模块卡片（分组，与左侧边栏自定义导航保持一致） ──
# 分组顺序对应日常操作流：看盘 → 选股 → 管仓 → 回测 → 交流 → 账户。
# 合并页：🎯个股研究＝股票选取+个股分析；💼持仓中心＝自选股监控+仓位管理+组合收益。
# 图标去重：📡事件追踪、🚨价格预警、🛠️系统配置。
st.header("📦 功能模块")

HOME_GROUPS = [
    ("🎯 决策闭环", [
        ("🎯", "今日决策面板", "pages/54_今日决策面板.py",
         "情绪信号→仓位建议→复盘归档：温度+周期六阶段+连板晋级率透明推导今日该几成仓"),
    ]),
    ("📘 新手引导", [
        ("📘", "新手教程", "pages/96_新手教程.py", "5 分钟上手：三步操作 + 模块导览 + 术语表 + 教学视频"),
    ]),
    ("📊 市场纵览", [
        ("🌅", "每日晨报", "pages/51_每日晨报.py", "开盘前速览：隔夜要闻、自选股快照、复盘笔记"),
        ("📈", "行情看板", "pages/10_行情看板.py", "指数迷你卡、行业板块涨跌榜、龙虎榜、相关性矩阵"),
        ("👁️", "智能盯盘", "pages/14_智能盯盘.py", "板块异动+自选涨跌+资金流+预警聚合，盘中自动刷新"),
        ("🌊", "资金流向", "pages/35_资金流向.py", "北向资金、板块资金流、大盘主力净流入、个股资金动向"),
        ("🧮", "市场驱动力", "pages/15_市场驱动力.py", "21指标五维归一化子图：资金/情绪/估值/宏观/技术 vs 上证参考线"),
        ("📊", "市场强弱", "pages/13_市场强弱.py", "指数+关键资金面归一化多线 + 强弱信号灯，一眼看懂当前市场"),
        ("📡", "事件追踪", "pages/23_事件追踪.py", "产业事件、价格信号、宏观数据三类信号综合评分与时间轴"),
        ("📅", "财报日历", "pages/16_财报日历.py", "业绩报表、业绩预告、披露日历，按报告期查看"),
        ("🌈", "板块轮动", "pages/12_板块轮动.py", "行业板块热力图、涨跌排行与资金轮动视图"),
        ("🌡️", "市场情绪", "pages/50_市场情绪.py", "市场广度与情绪温度计：ADL/ADR/新高新低/VIX/涨停/PCR/北向/融资/PE 综合冷热读数"),
    ]),
    ("🔎 选股研究", [
        ("🎯", "个股研究", "pages/24_个股研究.py", "快速选取 + 深度分析二合一：K线/技术面/打分/决策仪表盘"),
        ("🧭", "形态选股", "pages/31_形态选股.py", "K线形态 + 金叉死叉 + 背离扫描，手动/自选池双模式"),
        ("🏛️", "基本面分析", "pages/22_基本面分析.py", "个股估值、历史分位、行业横向对比与大盘主线判断"),
        ("📊", "多股对比", "pages/21_多股对比.py", "同屏横向对比 ≥5 只股票：雷达图、VS 卡、分层操作建议"),
        ("🧰", "ETF筛选", "pages/33_ETF筛选.py", "按类型/涨跌/成交额筛选 ETF 与基金，支持排序"),
    ]),
    ("💼 我的持仓", [
        ("💼", "持仓中心", "pages/45_持仓中心.py", "自选池 + 持仓盈亏 + 收益归因三合一"),
        ("🩺", "体检扫描", "pages/34_体检扫描.py", "一键批量体检自选+持仓：技术形态、主力资金、预警清单"),
        ("🚨", "价格预警", "pages/47_价格预警.py", "自选股多维预警：价格/涨跌幅/量能/技术信号触发提醒"),
        ("📤", "数据导出", "pages/95_数据导出.py", "资金流/财报/组合/自选股统一 CSV 导出与一键打包"),
        ("🎮", "模拟交易", "pages/42_模拟交易.py", "虚拟资金买卖 A 股，跟踪持仓盈亏与净值曲线"),
    ]),
    ("🧪 策略工具", [
        ("⚙️", "策略回测", "pages/30_策略回测.py", "事件驱动 / 均线交叉策略回测，收益曲线与夏普比率"),
    ]),
    ("💬 社区与 AI", [
        ("🌟", "星辰 AI", "pages/53_星辰AI.py", "对话 + 分析一体：个股诊断、横向对比、事件解读、持仓建议"),
        ("💬", "股吧", "pages/52_股吧.py", "社区讨论：发表观点、评论点赞，可关联个股一键跳转"),
        ("🔔", "消息中心", "pages/94_消息中心.py", "聚合自选股异动、社区动态与系统通知，统一已读"),
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
    ("👤", "我的", "pages/91_我的.py", "个人信息、自选股、偏好设置、外观与数据源配置"),
]
if is_admin():
    acct_items += [
        ("👥", "用户管理", "pages/92_用户管理.py", "用户 CRUD、角色分配与操作日志"),
        ("🛠️", "系统配置", "pages/93_系统配置.py", "股票数据、缓存、系统参数与运行配置"),
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
                st.session_state["pick_stock_confirmed"] = str(r["code"])
                st.session_state["pick_stock_query"] = str(r["code"])
                safe_switch_page("pages/24_个股研究.py")

# 快捷功能入口
try:
    st.caption("⚡ 一键直达常用功能")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📔 情绪笔记", key="qe_mood_note", use_container_width=True,
                     help="记录今日情绪快照 + 次日走势预判，并可回填实际走势形成复盘闭环"):
            # 置标记：目标页据此提示并把笔记区块高亮一次（一次性，刷新即消）
            st.session_state["shep_focus_note"] = True
            safe_switch_page("pages/50_市场情绪.py")
    with c2:
        if st.button("🔮 次日走势预判", key="qe_mood_fc", use_container_width=True,
                     help="牧羊人 18 项指标 → 情绪周期定位 + 次日方向与置信度 + 三情景推演"):
            st.session_state["shep_focus_note"] = True
            safe_switch_page("pages/50_市场情绪.py")
except Exception:  # noqa: BLE001
    pass

# 自选股数量 + 未读提醒（调后端）
try:
    wl_resp = requests.get(
        "http://127.0.0.1:5050/api/watchlist",
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
    st.metric("最近浏览", f"{len(recent)} 只", help="本次会话查看过的股票（点击上方「最近浏览」可直达个股研究）")
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
