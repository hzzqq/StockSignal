"""
页面 Z：新手教程（项目使用引导）

目标：让用户 5 分钟独立上手 StockSignal。内容全部为 UI / 引导层，不改动任何业务逻辑。
包含：
  1) 🚀 三步上手 checklist（session_state 勾选 + 进度条 + 直达按钮）
  2) 🧭 模块导览（复用 modules.widgets._NAV_GROUPS 分组，page_link 跳转，无浏览器上下文降级按钮）
  3) 📖 术语表（红涨绿跌 / 归一化 / 回测 / 北向资金 / 融资余额 …）
  4) ❓ 常见问题（可折叠）
  5) 🎬 教学视频（assets/tutorial_overview.mp4，缺失时给友好占位）
  6) 🗺️ 文字版分步漫游（可折叠，配合 present 出的 HTML 漫游 artifact）
  7) 📅 最后更新相对时间 + 完成引导

铁律：UI-only；fragment 内无整页 st.rerun；A股红涨绿跌；信号灯语义独立。
"""
import os
from pathlib import Path

import streamlit as st

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, safe_switch_page, _rel_time, get_token
from modules.widgets import _NAV_GROUPS
from modules.page_widgets import _section_title, _empty_info
from modules.page_guard import safe_fragment

apply_page_config(page_title="新手教程", page_icon="📘", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("📘 新手教程 · 5 分钟玩转 StockSignal")
st.caption("本页帮你快速上手：三步完成首次操作、认识各模块、看懂术语与常见疑问。看完即可独立使用本平台。")

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
VIDEO_PATH = ASSET_DIR / "tutorial_overview.mp4"
WALK_PATH = ASSET_DIR / "tutorial_walkthrough.html"

_LAST_UPDATED = "2026-07-21"


# ──────────────────────────────────────────────────────────────
# 通用：导航链接（page_link 在无浏览器上下文降级为按钮）
# ──────────────────────────────────────────────────────────────
def _link(path: str, label: str, icon: str = "🔗") -> None:
    try:
        st.page_link(path, label=label, icon=icon)
    except Exception:
        if st.button(f"{icon} {label}", key=f"tut_link_{path}", use_container_width=True):
            safe_switch_page(path)


# ──────────────────────────────────────────────────────────────
# 1) 三步上手
# ──────────────────────────────────────────────────────────────
@safe_fragment
def fragment_onboarding():
    _section_title("🚀 三步上手（勾选完成，进度自动保存）", accent="#2b8aef")
    steps = [
        ("tut_step1", "① 看盘", "打开《行情看板》，看指数迷你卡、行业板块涨跌榜、龙虎榜，先感受市场温度。",
         "pages/1_行情看板.py"),
        ("tut_step2", "② 选股", "在《个股研究》里搜索一只股票，看 K 线、技术面分析与评分，理解一只股票怎么看。",
         "pages/个股研究.py"),
        ("tut_step3", "③ 跟踪", "把看好的股票加入自选股，到《持仓中心》跟踪涨跌、设置价格预警。",
         "pages/持仓中心.py"),
    ]
    done = 0
    for key, title, desc, page in steps:
        c1, c2 = st.columns([0.06, 0.94])
        with c1:
            checked = st.checkbox(" ", value=st.session_state.get(key, False), key=key, label_visibility="collapsed")
        with c2:
            st.markdown(f"**{title}**　{desc}")
            if st.button(f"去操作 → {title}", key=f"go_{key}", help=f"跳转到 {page}"):
                safe_switch_page(page)
        if checked:
            done += 1
    st.progress(done / len(steps))
    if done == len(steps):
        st.success("🎉 三步全部完成！你已经掌握基础操作，可以去《策略回测》试跑你的第一个策略，"
                   "或用《星辰 AI》问一句「帮我看看某某股票」。")
    else:
        st.caption(f"已完成 {done}/{len(steps)} 步。每完成一步勾选左侧方框即可；进度会保留在当前会话。")


# ──────────────────────────────────────────────────────────────
# 2) 模块导览
# ──────────────────────────────────────────────────────────────
@safe_fragment
def fragment_modules():
    _section_title("🧭 模块导览（点击直达）", accent="#2b8aef")
    st.caption("平台按「看盘 → 选股 → 管仓 → 回测 → 交流 → 账户」组织，挑感兴趣的先点开看看。")
    # 守卫：导航配置缺失或非列表时降级为空态，避免迭代崩溃
    if not _NAV_GROUPS or not isinstance(_NAV_GROUPS, (list, tuple)):
        _empty_info("模块导览暂不可用（导航配置缺失）。")
        return
    for gname, items in _NAV_GROUPS:
        with st.expander(gname, expanded=False):
            for path, label, icon in items:
                _link(path, label, icon)
    with st.expander("👤 账户", expanded=False):
        _link("pages/👤_我的.py", "我的", "👤")
    st.page_link("app.py", label="🏠 返回首页", icon="🏠")


# ──────────────────────────────────────────────────────────────
# 3) 术语表
# ──────────────────────────────────────────────────────────────
@safe_fragment
def fragment_glossary():
    _section_title("📖 术语表（看不懂的词先查这里）", accent="#2b8aef")
    terms = [
        ("红涨绿跌", "A股惯例：价格/指数上涨用红色，下跌用绿色（与欧美相反）。本平台全局统一。"),
        ("归一化（起点=100）", "把不同量纲的序列都缩放到同一起点 100，便于在同一张图里横向比较。例如融资余额万亿级与 RSI 0-100 可同图叠加。"),
        ("回测", "用历史行情验证一个交易策略：假设过去按规则买卖，看能赚多少、胜率多高、最大回撤多大。"),
        ("北向资金", "通过沪/深股通从香港流入 A 股的外资，常被视为聪明钱风向标（2024-08 起停披露实时值，历史段仍真实）。"),
        ("融资余额", "投资者向券商借钱买股的总额。余额持续增加代表杠杆资金看多。"),
        ("金叉 / 死叉", "短期均线向上穿过长期均线叫金叉（偏多信号）；向下穿过叫死叉（偏空信号）。"),
        ("多因子", "同时用多个指标（资金/情绪/估值/宏观/技术）给股票或市场打分，而非只看单一维度。"),
        ("压力位 / 支撑位", "价格涨到某一位置容易遇阻回落叫压力位；跌到某一位置容易止跌反弹叫支撑位。"),
        ("夏普比率", "衡量「每承担一单位风险换来多少超额收益」，越高代表风险收益性价比越好。"),
        ("最大回撤", "一段时间内从最高点到最低点的最大跌幅，用来衡量最坏情况会亏多少。"),
    ]
    for name, desc in terms:
        st.markdown(f"- **{name}**：{desc}")


# ──────────────────────────────────────────────────────────────
# 4) 常见问题
# ──────────────────────────────────────────────────────────────
@safe_fragment
def fragment_faq():
    _section_title("❓ 常见问题", accent="#2b8aef")
    faqs = [
        ("数据为什么有时加载不出来？", "部分数据来自外部接口，需要联网/代理。加载失败页面会优雅提示，不影响其他功能；可稍后重试或刷新。"),
        ("红涨绿跌能改吗？", "A股惯例已全局固定为红涨绿跌，个股分析页也遵循此约定，无需也不建议修改。"),
        ("回测结果能当真吗？", "回测基于历史数据，含手续费与止损等假设，仅作策略参考，不等于未来收益，实盘需谨慎。"),
        ("自选股在哪里管理？", "《持仓中心》里包含自选股监控、持仓盈亏与组合收益；也可在任意个股页一键加入自选。"),
        ("忘记密码怎么办？", "在登录页点击「忘记密码」按提示重置；管理员可在《用户管理》中重置普通用户密码。"),
        ("手机能远程用吗？", "可通过远程桌面连接运行本平台的电脑使用；当前无官方手机 App，但网页端自适应可用。"),
    ]
    for q, a in faqs:
        with st.expander(f"❔ {q}", expanded=False):
            st.markdown(a)


# ──────────────────────────────────────────────────────────────
# 4.5) 常见误区
# ──────────────────────────────────────────────────────────────
@safe_fragment
def fragment_mistakes():
    _section_title("⚠️ 常见误区（新手最容易踩的坑）", accent="#ef4444")
    mistakes = [
        ("红=跌、绿=涨？", "错。A股惯例是**红涨绿跌**，红色代表上涨、绿色代表下跌，与欧美相反。本平台全局统一此配色。"),
        ("回测收益 = 未来收益？", "错。回测基于历史数据并含手续费 / 止损等假设，可能过拟合或含未来函数，仅作策略参考，不等于实盘表现。"),
        ("一根金叉就满仓？", "错。单一技术信号胜率有限，应等多因子共振（资金 + 估值 + 基本面）并配合仓位管理，避免一把梭。"),
        ("跌多了就能抄底？", "错。弱势股可能继续下行，抄底需结合基本面企稳与信号反转，别把「便宜」当「安全」。"),
        ("北向资金盘中实时可见？", "错。2024-08 起已停披露实时值，盘中看不到；本平台展示的历史段真实，勿据此做盘中决策。"),
        ("自选股越多越好？", "错。跟踪标的过多反而难以聚焦，建议精选 10–20 只重点跟踪，其余用条件选股随时筛选。"),
        ("平台结论 = 投资建议？", "错。本平台仅做数据分析，**不构成任何投资建议**，盈亏自负；重大决策请结合自身判断与正规渠道。"),
    ]
    for q, a in mistakes:
        with st.expander(f"⚠️ {q}", expanded=False):
            st.markdown(a)


# ──────────────────────────────────────────────────────────────
# 4.6) 快捷键说明
# ──────────────────────────────────────────────────────────────
@safe_fragment
def fragment_hotkeys():
    _section_title("⌨️ 快捷键说明（Streamlit 原生）", accent="#2b8aef")
    st.caption("以下为 Streamlit 运行时的浏览器快捷键（不同版本略有差异），熟练后可大幅提升操作效率：")
    keys = [
        ("R", "重新运行当前页面（刷新数据与图表）"),
        ("C", "清除缓存（遇到旧数据 / 接口异常时，按此强制重载）"),
        ("A", "展开 / 收起左侧边栏"),
        ("Ctrl / Cmd + K", "打开命令面板（快速跳转页面，较新版本支持）"),
    ]
    for k, d in keys:
        st.markdown(f"- **`{k}`**：{d}")
    st.info("💡 提示：本平台的侧边栏导航与首页卡片已覆盖绝大多数跳转需求，快捷键主要用来「刷新」与「清缓存」。")
# ──────────────────────────────────────────────────────────────
@safe_fragment
def fragment_video():
    _section_title("🎬 教学视频 · 平台快速漫游", accent="#2b8aef")
    if VIDEO_PATH.exists():
        try:
            st.video(str(VIDEO_PATH))
        except Exception:
            _empty_info("教学视频文件存在但无法预览，请在 assets/ 目录直接打开。")
    else:
        _empty_info("🎞️ 教学视频尚未生成（assets/tutorial_overview.mp4 缺失）。"
                "你可先阅读下面的「文字版分步漫游」，或在终端运行视频生成后刷新本页。")

    with st.expander("🗺️ 文字版分步漫游（配合 HTML 漫游 artifact 食用更佳）", expanded=False):
        for i, (t, d) in enumerate([
            ("第 1 步 · 认识首页", "登录后进入首页，看到「功能模块」分组卡片与「最近浏览」。点任意卡片进入对应模块。"),
            ("第 2 步 · 看盘", "《行情看板》顶部是指数迷你卡（上证/深证/创业等），下方是行业板块涨跌榜与龙虎榜，点板块可展开明细。"),
            ("第 3 步 · 选股与研究", "《个股研究》搜股票代码/名称 → 看 K 线（可拖动缩放）、技术面分析、给股票打分，并加入自选或垃圾股。"),
            ("第 4 步 · 管仓与预警", "《持仓中心》跟踪自选股涨跌；《价格预警》设置价格/涨跌幅触发提醒，异动会推到《消息中心》。"),
            ("第 5 步 · 回测策略", "《策略回测》选策略与区间跑回测，看收益曲线、夏普比率与交易明细，验证你的想法。"),
            ("第 6 步 · 问 AI", "右上角 ★ 或侧边栏《星辰 AI》可对话式问诊个股、对比、解读事件与持仓。"),
        ], start=1):
            st.markdown(f"**{t}**：{d}")
        st.caption("📎 完整交互式漫游见随附的 HTML 文件（tutorial_walkthrough.html），可在浏览器打开逐步点击。")

    if WALK_PATH.exists():
        st.caption(f"📎 文字漫游配套 HTML：{WALK_PATH.name}（已随本次更新一并生成，可在文件管理器打开）。")


# ──────────────────────────────────────────────────────────────
# 页面主体
# ──────────────────────────────────────────────────────────────
fragment_onboarding()
st.markdown("---")
fragment_modules()
st.markdown("---")
fragment_glossary()
st.markdown("---")
fragment_faq()
st.markdown("---")
fragment_mistakes()
st.markdown("---")
fragment_hotkeys()
st.markdown("---")
fragment_video()

st.markdown("---")
st.caption(f"📅 本页最近整理于 {_LAST_UPDATED}（{_rel_time(_LAST_UPDATED + 'T00:00:00')}）　·　"
           f"StockSignal 新手引导模块")
