"""
页面 2_多股对比：多股票横向对比
模仿 compare-analysis-20260710.html 的暗色 .sf-* 决策仪表盘风格，支持同屏对比 ≥5 只股票。
数据全部程序化（fetcher + technical + 价格相关性 + 启发式催化/弹性），前端由 modules.compare 生成。
"""
import streamlit as st

st.set_page_config(page_title="多股对比", page_icon="📊", layout="wide")

# 强制本页进入「星辰决策仪表盘」暗色主题（离开本页后自动恢复全局主题）
st.session_state["_active_page"] = __file__

from modules.session import init_session_state, require_auth, render_user_badge
from modules.search_ui import multi_stock_search_input
from modules.compare import (
    fetch_compare, compare_css, build_header, build_one_line,
    build_table, build_pairwise_card, build_radar, build_radar_right,
    build_action_plan, build_footer, METHODS,
    build_method_card, build_aggregate_card,
)

require_auth()
render_user_badge(sidebar=True)
st.title("📊 多股对比 · 决策仪表盘")

EXAMPLE = "600667,601133,002947,002167,600206"


def _ai_summary(rows, question: str) -> str:
    """基于当前对比数据生成简单的 AI 咨询简报。"""
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


with st.sidebar:
    st.markdown("### 对比设置")
    st.caption("输入 2~8 只股票（代码/中文名/拼音），一键同屏横向对比。")
    if st.button("载入示例（5只）", use_container_width=True):
        st.session_state["cmp_items"] = [
            {"id": i, "value": code, "code": code, "name": None}
            for i, code in enumerate(EXAMPLE.split(","))
        ]
        st.rerun()

    # 支持中文名/拼音/代码的多股票输入框（动态行版）
    codes = multi_stock_search_input(
        label="输入多只股票",
        key="cmp",
        default=EXAMPLE,
        placeholder="600519 / 茅台 / gzmt",
    )

    with st.form("cmp_form"):
        period = st.slider("回看天数", 60, 250, 120, 10)
        submitted = st.form_submit_button("开始对比", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("### ★ 星辰 · 多市场智能股票分析师")
    with st.form("ai_consult_form"):
        question = st.text_area(
            "AI 咨询",
            value=st.session_state.get("ai_consult_q", ""),
            placeholder="例如：这组合里谁最值得买？风险在哪？",
            height=80,
            label_visibility="collapsed",
        )
        consult_submitted = st.form_submit_button("🚀 咨询", use_container_width=True)
    if consult_submitted:
        st.session_state["ai_consult_q"] = question
        st.rerun()
    if "ai_consult_q" in st.session_state and st.session_state["ai_consult_q"]:
        rows_for_ai = st.session_state.get("_cmp_rows")
        st.markdown(
            _ai_summary(rows_for_ai, st.session_state["ai_consult_q"]),
            unsafe_allow_html=True,
        )
    else:
        st.caption("完成对比后，可在此输入问题获取基于当前标的的智能简报。")

if submitted:
    if len(codes) < 2:
        st.warning("请至少输入 2 只有效股票。")
    else:
        with st.spinner(f"正在拉取 {len(codes)} 只股票数据并计算对比指标（回看 {period} 天）…"):
            try:
                rows = fetch_compare(codes, period)
                st.session_state["_cmp_rows"] = rows
                st.session_state["_cmp_period"] = period
            except Exception as e:  # noqa: BLE001
                st.error(f"对比生成失败：{e}")

rows = st.session_state.get("_cmp_rows")
if not rows:
    st.info("👈 在左侧输入股票代码/名称后点击「开始对比」。已预填示例（5只），直接点击即可查看效果。")
    st.stop()

# 部分标的行情缺失提示
failed = [r["name"] for r in rows if r.get("error")]
if failed:
    st.warning(f"以下标的行情获取失败，已按中性默认展示：{'、'.join(failed)}")

period = st.session_state.get("_cmp_period", 120)

# ── 头部 + 核心结论 + 横向对比表（同一 compare-wrap 内）──
st.markdown(
    '<div class="compare-wrap">' + compare_css()
    + build_header(rows, period)
    + build_one_line(rows)
    + build_table(rows),
    unsafe_allow_html=True,
)

# ── 综合评分雷达（左图 + 右标签云/风险）──
st.markdown(
    '<div class="card"><h2>综合评分雷达（%d 股五维对比）</h2></div>' % len(rows),
    unsafe_allow_html=True,
)
c1, c2 = st.columns([1.15, 1])
with c1:
    st.plotly_chart(build_radar(rows), use_container_width=True)
with c2:
    st.markdown(build_radar_right(rows), unsafe_allow_html=True)

# ── 两两对比选择器 + 选中 pair 卡片 ──
if len(rows) >= 2:
    pairs = [(rows[i], rows[j]) for i in range(len(rows)) for j in range(i + 1, len(rows))]
    pair_labels = [f"{a['name']} vs {b['name']}" for a, b in pairs]
    selected_label = st.selectbox(
        "选择两两对比",
        options=pair_labels,
        index=0,
        help="从下方选择两只股票进行 1:1 深度对比。",
    )
    selected_idx = pair_labels.index(selected_label)
    a, b = pairs[selected_idx]
    st.markdown(
        build_pairwise_card(a, b, selected_idx + 1) + build_action_plan(rows) + build_footer(),
        unsafe_allow_html=True,
    )
else:
    st.markdown(build_footer(), unsafe_allow_html=True)

# ── 对比方法选择器（位于方法结果卡片上方）──
st.markdown("### 对比方法")
method = st.radio(
    "选择对比维度（不同方法按各自权重重排标的并给出结论）",
    options=list(METHODS.keys()),
    index=0,
    horizontal=True,
    help="短期=动量量能；长期=趋势稳定；价值=低估；板块=业务关联度；业绩=催化；"
         "政策=政策敏感；宏观=弹性；微观=技术结构；事件=输入事件看利好利空。",
)
event_text = ""
if method == "事件":
    event_text = st.text_input(
        "输入事件（如：AI芯片扩产 / 新能源补贴退坡 / 半导体国产化）",
        key="cmp_event",
        placeholder="描述一个事件，对比各股在该事件上的业务关联度与利好/利空",
    )
st.caption(METHODS[method])

# ── 对比方法卡片（选定方法）+ 大汇总（九维结论）──
st.markdown(
    '<div class="compare-wrap">'
    + build_method_card(rows, method, event_text)
    + build_aggregate_card(rows, event_text)
    + "</div>",
    unsafe_allow_html=True,
)
