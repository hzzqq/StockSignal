"""
页面 2_多股对比：多股票横向对比
模仿 compare-analysis-20260710.html 的暗色 .sf-* 决策仪表盘风格，支持同屏对比 ≥5 只股票。
数据全部程序化（fetcher + technical + 价格相关性 + 启发式催化/弹性），前端由 modules.compare 生成。
"""
import streamlit as st

st.set_page_config(page_title="多股对比", page_icon="📊", layout="wide")
# 前置：本页为「决策仪表盘」暗色页面，由 ui_theme 按页面作用域(_active_page)强制暗色
st.session_state["_active_page"] = __file__

from modules.session import init_session_state, require_auth, render_user_badge
from modules.search_ui import multi_stock_search_input
from modules.compare import (
    fetch_compare, compare_css, build_header, build_one_line,
    build_table, build_vs_cards, build_radar, build_radar_right,
    build_action_plan, build_footer,
)

require_auth()
render_user_badge(sidebar=True)
st.title("📊 多股对比 · 决策仪表盘")

EXAMPLE = "600667,601133,002947,002167,600206"


with st.sidebar:
    st.markdown("### 对比设置")
    st.caption("输入 2~8 只股票（代码/中文名/拼音，逗号/空格分隔），一键同屏横向对比。")
    if st.button("载入示例（5只）", use_container_width=True):
        st.session_state["cmp_raw"] = EXAMPLE
        st.rerun()

    # 支持中文名/拼音/代码的多股票输入框
    codes = multi_stock_search_input(
        label="输入多只股票（逗号分隔）",
        key="cmp",
        default=EXAMPLE,
        placeholder="如 600519,茅台,gzmt,601088",
    )

    with st.form("cmp_form"):
        period = st.slider("回看天数", 60, 250, 120, 10)
        submitted = st.form_submit_button("开始对比", use_container_width=True, type="primary")

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

# ── 头部 + 核心结论 + 横向对比表（同一 scope 内）──
st.markdown(
    '<div class="compare-wrap">' + compare_css()
    + build_header(rows, period)
    + build_one_line(rows)
    + build_table(rows),
    unsafe_allow_html=True,
)

# ── 综合评分雷达（左图 + 右排行/风险）──
st.markdown(
    '<div class="card"><h2>综合评分雷达（%d 股五维对比）</h2></div>' % len(rows),
    unsafe_allow_html=True,
)
c1, c2 = st.columns([1.15, 1])
with c1:
    st.plotly_chart(build_radar(rows), use_container_width=True)
with c2:
    st.markdown(build_radar_right(rows), unsafe_allow_html=True)

# ── 两两 VS 卡 + 分层操作建议 + 页脚（同一 scope 内）──
st.markdown(
    build_vs_cards(rows) + build_action_plan(rows) + build_footer() + "</div>",
    unsafe_allow_html=True,
)
