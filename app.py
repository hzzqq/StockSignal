"""
StockSignal 主入口
A股事件驱动投资分析平台
"""

import time
import urllib.request
import urllib.error

import requests
import streamlit as st

from modules.ui_theme import apply_page_config, dashboard_sf_css
from modules.ui_kit import xc_bento_kpi
from modules import decision as _decision
from modules import shepherd as _sh
from modules import shepherd_ladder as _sl
from modules import shepherd_forecast as _sf
apply_page_config(
    page_title="StockSignal · A股事件驱动投资分析平台",
    layout="wide"
)
# T-283：首页与其余 67 页对齐——注入全站组件收敛层（T-278 原生 alert 深色卡 /
# T-279 caption 截断·metric 等高·expander 紧凑 / T-280 下载按钮·pills·分段选择器
# ·dropzone）。此前首页从不调 render_standard_page，该层从未在首页生效：
# 实测（2026-10-14）首页 st.warning 走原生 light 底白横条直插深色页面。
# 注入顺序与 page_utils.render_standard_page 一致（apply_page_config 之后）。
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
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
        # ⚠️ get_shepherd_indicators 返回 (df, meta) 二元组，必须解包。
        # 曾漏解包：_df 实为元组 → 元组无 .empty → 下面 getattr(..., True) 默认值恒定生效
        # → 整块被跳过、异常又被 except 吞掉 → 首页温度/周期/方向永远显示兜底值，
        # 真实情绪数据从未上过首页。守卫见 tests/test_daily_snapshot_wiring.py。
        _df, _shep_meta = _sh.get_shepherd_indicators(days=1)
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
    # 事件驱动催化：首页兜底估算也接通事件因子（与 54_ / build_snapshot 同源），
    # 消除首页「实时估算」与归档快照的活/归档漂移（S6）。走模块级 300s TTL 缓存，
    # 失败降级为 None（不臆造）。
    event_adj_val = None
    event_as_of = None
    try:
        _evd = _decision._event_position_adj()
        if isinstance(_evd, dict):
            event_adj_val = _evd.get("adj")
            event_as_of = _evd.get("as_of")
    except Exception:  # noqa: BLE001
        event_adj_val = None
    pos = _decision.derive_position(temp, score, bias, cycle_name, overall,
                                    event_adj=event_adj_val)
    # 双源新鲜度守卫：与 build_snapshot / 54_ 共用 assess_freshness（S7）。
    # 估算路径无快照，牧羊人真实截止日未知 → 仅事件因子参与；但只要事件因子滞后
    # 达阈值，仍会显式告警，避免「快照新鲜」假象掩盖事件信号陈旧。
    _fresh = _decision.assess_freshness({"牧羊人情绪": None, "事件因子": event_as_of})
    return {
        "date": "估算", "temperature": temp, "cycle": cycle_name, "bias": bias,
        "confidence": None, "position": pos, "overall": overall,
        "event_factor": {"available": event_adj_val is not None,
                          "adj": event_adj_val, "as_of": event_as_of},
        "data_freshness": _fresh,
        "estimate": True, "has_signal": temp is not None or overall is not None,
    }


def _render_decision_card(payload, stale=False):
    pos = payload.get("position") or {}
    date = payload.get("date") or "-"
    temp = payload.get("temperature")
    estimate = payload.get("estimate", False)
    with st.container(border=True):
        if estimate:
            st.caption("📡 实时估算（尚未生成今日收盘快照，仅供参考）· 由「市场温度 + 情绪周期 + 连板晋级率 + 事件驱动」透明推导")
        elif stale:
            st.caption(f"⚠️ 快照日期 {date}，已超 20 小时未更新 —— 今天跑过 daily_snapshot.py 吗？")
        else:
            st.caption(f"数据日期 {date} · 由「市场温度 + 情绪周期 + 连板晋级率 + 事件驱动」透明推导")

        # 双源新鲜度警示（与 54_ 同源）：事件因子滞后等关键陈旧不再被「快照新鲜」掩盖（S7）
        _fresh = payload.get("data_freshness")
        if _fresh and _fresh.get("status") in ("warn", "stale"):
            _bits = [
                f"{name}截至 {s['as_of']}（滞后 {s['lag_days']} 天）"
                for name, s in _fresh.get("sources", {}).items()
                if s.get("status") in ("warn", "stale") and s.get("as_of")
            ]
            if _bits:
                st.warning("⏰ 数据滞后：" + "、".join(_bits) + "——决策依据可能偏旧，谨慎参考")

        c1, c2, c3, c4, c5 = st.columns([1, 1.4, 1, 1.1, 1.1])
        with c1:
            st.metric("🌡️ 市场温度", f"{temp:.0f}" if temp is not None else "—",
                      help="牧羊人 17 项综合温度 0-100，越高越热",
                      delta_color="off")
        with c2:
            st.metric("🔄 情绪周期", payload.get("cycle") or "-",
                      help="六阶段定位：冰点 / 修复试探 / 修复确认 / 主升高潮 / 高潮分化 / 退潮",
                      delta_color="off")
        with c3:
            st.metric("🧭 次日方向", payload.get("bias") or "-",
                      delta=f"置信 {payload.get('confidence') or '-'}", delta_color="off")
        with c4:
            st.metric("📊 建议仓位", f"{pos.get('pct', '-')}%",
                      delta=pos.get("band") or "-", delta_color="off",
                      help="温度基准 + 方向/周期/晋级率调节，clamp 5~95%")
        with c5:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("🎯 决策面板 →", key="td_open", width="stretch",
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


# ── 紧凑状态行：状态退到一行 caption，不再用 4 个指标卡抢占首屏视觉 ──
_backend_ok = _check_backend()
_role = "管理员" if user.get("role") == "admin" else "普通用户"
st.caption(
    f"👤 {user.get('username', '-')}（{_role}）　·　"
    + ("🟢 后端正常" if _backend_ok else "🔴 后端未连接")
    + f"　·　🕒 {time.strftime('%H:%M:%S')}　·　🏷️ v1.0"
)

st.markdown("---")

# ── 项目说明（轻量化卡片，置于页面顶部，非折叠）──
def _render_project_intro():
    """首页顶部项目说明：轻量卡片，不折叠，让首次进入的用户一眼看懂平台定位。"""
    st.markdown(
        """
        <style>
        .ss-intro{max-width:100%;background:linear-gradient(135deg,
            color-mix(in srgb,var(--acc1) 8%,var(--card)) 0%,var(--card) 100%);
            border:1px solid color-mix(in srgb,var(--acc1) 28%,var(--border));
            border-radius:18px;padding:1.4rem 1.6rem;margin-bottom:.4rem}
        .ss-intro-badge{display:inline-block;background:color-mix(in srgb,var(--acc1) 14%,transparent);
            color:var(--acc1);border:1px solid color-mix(in srgb,var(--acc1) 35%,transparent);
            border-radius:999px;padding:.3rem .9rem;font-size:.78rem;font-weight:700;margin-bottom:.7rem}
        .ss-intro h2{margin:.1rem 0 .5rem;font-size:1.35rem;color:var(--txt)}
        .ss-intro p{margin:0 0 .9rem;color:var(--txt2);line-height:1.65;font-size:.92rem}
        .ss-intro p b{color:var(--txt)}
        .ss-intro-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem}
        .ss-intro-cell{background:color-mix(in srgb,var(--acc1) 6%,var(--card));
            border:1px solid var(--border);border-radius:12px;padding:.8rem .9rem}
        .ss-intro-cell .ss-intro-ic{font-size:1.3rem}
        .ss-intro-cell b{display:block;margin:.25rem 0 .15rem;color:var(--txt);font-size:.95rem}
        .ss-intro-cell small{color:var(--txt2);font-size:.76rem;line-height:1.4}
        @media(max-width:640px){.ss-intro-grid{grid-template-columns:1fr}}
        </style>
        <div class="ss-intro">
          <span class="ss-intro-badge">A股事件驱动 · 决策闭环</span>
          <h2>把「事件催化」翻译成可执行的仓位决策</h2>
          <p>StockSignal 是一款面向个人投资者的 <b>A股事件驱动分析工具</b>，整合三类核心催化信号，
          帮你 <b>快速识别行情主线</b>、<b>可视化行业轮动</b>、<b>回测事件驱动策略</b>。</p>
          <div class="ss-intro-grid">
            <div class="ss-intro-cell"><span class="ss-intro-ic">🏛️</span><b>产业事件</b><small>政策发布 / 行业并购 / 产能变化</small></div>
            <div class="ss-intro-cell"><span class="ss-intro-ic">📈</span><b>价格信号</b><small>大宗 / 上游原材料价格变动</small></div>
            <div class="ss-intro-cell"><span class="ss-intro-ic">📊</span><b>宏观数据</b><small>PMI / CPI / 社融等关键指标</small></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
_render_project_intro()

st.markdown("---")

# ── 今日决策（情绪信号 → 仓位建议）──
# 项目说明卡片置于页面顶部后，今日决策紧随其下，形成「先懂平台 → 再看今日该怎么做」的叙事。
_render_today_decision()

st.markdown("---")

# ── ⚡ 快捷入口：常用直达 + 快捷入口 合并为单一区块（轻量化，不折叠）──
st.header("⚡ 快捷入口")

# 常用直达：高频功能一键跳转
_QUICK = [
    ("🎯", "今日决策面板", "pages/54_今日决策面板.py"),
    ("📈", "行情看板", "pages/10_行情看板.py"),
    ("👁️", "智能盯盘", "pages/14_智能盯盘.py"),
    ("🔬", "个股研究", "pages/24_个股研究.py"),
    ("🏦", "持仓中心", "pages/45_持仓中心.py"),
    ("⚙️", "策略回测", "pages/30_策略回测.py"),
]
_qcols = st.columns(len(_QUICK))
for _i, (_qic, _qnm, _qpg) in enumerate(_QUICK):
    with _qcols[_i]:
        if st.button(f"{_qic} {_qnm}", key=f"quick_{_qnm}", width="stretch"):
            safe_switch_page(_qpg)

# 最近浏览（session_state 维护）
recent = get_recent_stocks()
if recent:
    st.subheader("🕘 最近浏览")
    rc = st.columns(min(len(recent), 4))
    for i, r in enumerate(recent[:4]):
        with rc[i]:
            if st.button(f"{r['code']}\n{r['name']}", key=f"recent_{r['code']}", width="stretch"):
                st.session_state["pick_stock_confirmed"] = str(r["code"])
                st.session_state["pick_stock_query"] = str(r["code"])
                safe_switch_page("pages/24_个股研究.py")

# 快捷功能入口
try:
    st.caption("⚡ 一键直达常用功能")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📔 情绪笔记", key="qe_mood_note", width="stretch",
                     help="记录今日情绪快照 + 次日走势预判，并可回填实际走势形成复盘闭环"):
            st.session_state["shep_focus_note"] = True
            safe_switch_page("pages/50_市场情绪.py")
    with c2:
        if st.button("🔮 次日走势预判", key="qe_mood_fc", width="stretch",
                     help="牧羊人 18 项指标 → 情绪周期定位 + 次日方向与置信度 + 三情景推演"):
            st.session_state["shep_focus_note"] = True
            safe_switch_page("pages/50_市场情绪.py")
except Exception:  # noqa: BLE001
    pass

# 自选股数量（调后端）
try:
    wl_resp = requests.get(
        "http://127.0.0.1:5050/api/watchlist",
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=5,
    )
    wl_count = len(wl_resp.json().get("data") or []) if wl_resp.status_code == 200 else 0
except Exception:
    wl_count = 0

# Bento 非对称网格：自选股 / 最近浏览 / 数据更新 三个读数错落成轻量信息块
xc_bento_kpi([
    {"label": "自选股", "value": f"{wl_count} 只", "meta": "在行情看板添加到自选股"},
    {"label": "最近浏览", "value": f"{len(recent)} 只", "meta": "点击上方「最近浏览」可直达个股研究"},
    {"label": "数据更新", "value": time.strftime("%H:%M"), "meta": "界面数据刷新时间"},
], template="1.4fr 1fr 1fr")

st.markdown("---")

# ── 账户（轻量化卡片行，替代原「全部功能模块」里的折叠分组）──
st.header("👤 账户")
_acct_items = [
    ("👤", "我的", "pages/91_我的.py", "个人信息、自选股、偏好设置、外观与数据源配置"),
]
if is_admin():
    _acct_items += [
        ("👥", "用户管理", "pages/92_用户管理.py", "用户 CRUD、角色分配与操作日志"),
        ("🛠️", "系统配置", "pages/93_系统配置.py", "股票数据、缓存、系统参数与运行配置"),
    ]
_acct_cols = st.columns(len(_acct_items))
for _i, (_ic, _nm, _pg, _desc) in enumerate(_acct_items):
    with _acct_cols[_i]:
        with st.container(border=True):
            st.markdown(f"**{_ic} {_nm}**")
            st.caption(_desc)
            if st.button("进入 →", key=f"acct_{_nm}", width="stretch"):
                safe_switch_page(_pg)

st.markdown("---")

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
