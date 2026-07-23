"""
页面 2_多股对比：多股票横向对比
模仿 compare-analysis-20260710.html 的暗色 .sf-* 决策仪表盘风格，支持同屏对比 ≥5 只股票。
数据全部程序化（fetcher + technical + 价格相关性 + 启发式催化/弹性），前端由 modules.compare 生成。
"""
import streamlit as st
import pandas as pd

from modules.ui_theme import apply_page_config
from modules.page_guard import safe_fragment

apply_page_config(page_title="多股对比", page_icon="📊", layout="wide")

# 本页「星辰决策仪表盘」跟随全局主题（右上角开关可切暗夜 / 白天）
st.session_state["_active_page"] = __file__

from modules.session import require_auth, render_user_badge
from modules.search_ui import multi_stock_search_input
from modules.background_tasks import submit_task_with_error, poll_task
from streamlit_autorefresh import st_autorefresh
from modules.compare import (
    compare_css, build_header, build_one_line,
    build_table, build_pairwise_card, build_radar, build_radar_right,
    build_action_plan, build_footer, METHODS,
    build_method_card, build_aggregate_card, build_extra_card,
)

require_auth()
render_user_badge(sidebar=True)
st.title("📊 多股对比 · 决策仪表盘")

EXAMPLE = "600667,601133,002947,002167,600206"


# AI 咨询逻辑已移至 modules.widgets.render_ai_consultant（全局通用，任意页面可用）


# ── 对比设置（位于标题下方主区域，逐个输入、可增删、带匹配结果）──
@safe_fragment("对比设置")
def fragment_compare_setup():
    with st.container(border=True):
        st.markdown("### 对比设置")
        st.caption("输入 2~8 只股票（代码/中文名/拼音），逐个添加，支持增删。")

        c1, c2 = st.columns([3, 1])
        with c1:
            codes = multi_stock_search_input(
                label="股票列表",
                key="cmp_multi",
                default=EXAMPLE,
                placeholder="代码 / 名称 / 拼音",
                max_rows=8,
            )
        with c2:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            if st.button("载入示例（5只）", use_container_width=True, key="cmp_load_example"):
                st.session_state["cmp_multi_items"] = [
                    {"id": i, "value": c, "code": c, "name": None}
                    for i, c in enumerate(EXAMPLE.split(","))
                ]
                st.rerun(scope="fragment")

        with st.form("cmp_form"):
            period = st.slider("回看天数", 60, 250, 120, 10)
            submitted = st.form_submit_button("开始对比", use_container_width=True, type="primary")

        st.session_state["_cmp_period_input"] = period

    if submitted:
        # ⚠️ 兜底：multi_stock_search_input 可能返回 None 而非空列表，len(None) 会抛 TypeError
        if len(codes or []) < 2:
            st.warning("请至少输入 2 只有效股票。")
        else:
            task_id, err = submit_task_with_error("compare", {"codes": codes, "period": period})
            if task_id:
                st.session_state["compare_task_id"] = task_id
                st.session_state["_cmp_rows"] = None
                # ⚠️ 修复：codes 是 fragment_compare_setup 的局部变量，
                # fragment_compare_result 在 pending/running 分支会引用 len(codes) 而崩溃（NameError）。
                # 提交时把 codes 存入 session_state，结果 fragment 读取同一份。
                st.session_state["cmp_codes"] = list(codes)
                st.info(f"📡 已提交 {len(codes)} 只股票的后台对比任务，切到其他页面也会继续跑。")
            else:
                err = err or "未知错误"
                if "登录" in err or "过期" in err or "凭证" in err:
                    st.error(f"❌ {err}")
                    if st.button("重新登录", key="cmp_relogin", use_container_width=True):
                        st.session_state.clear()
                        st.switch_page("pages/0_登录.py")
                else:
                    st.error(f"❌ 后台任务提交失败：{err}，请刷新重试。")



fragment_compare_setup()

@st.cache_data(ttl=1)
def _poll_compare_once(task_id: str) -> dict | None:
    """缓存 1 秒：避免同一次 fragment 重跑中多次调用 poll_task 造成请求堆积。"""
    return poll_task(task_id, max_wait=0.5)


@safe_fragment
def fragment_compare_result():
    """对比结果区：轮询 + 加载反馈 + 自动渲染，fragment 隔离不阻塞整页。"""
    compare_task_id = st.session_state.get("compare_task_id")
    if compare_task_id:
        task = _poll_compare_once(compare_task_id)
        if task and task.get("status") == "success":
            rows = task.get("result") or []
            # 还原序列化后的 DataFrame
            for r in rows:
                if "df" in r and isinstance(r["df"], list):
                    r["df"] = pd.DataFrame(r["df"])
                    if "date" in r["df"].columns:
                        r["df"]["date"] = pd.to_datetime(r["df"]["date"], errors="coerce")
            st.session_state["_cmp_rows"] = rows
            st.session_state["_cmp_period"] = st.session_state.get("_cmp_period_input", 120)
            del st.session_state["compare_task_id"]
            st.toast("✅ 多股对比完成")
        elif task and task.get("status") == "error":
            st.error(f"对比失败：{task.get('error')}")
            del st.session_state["compare_task_id"]
        elif task and task.get("status") in ("pending", "running"):
            _cmp_codes = st.session_state.get("cmp_codes", [])
            st.warning(
                f"⏳ 正在后台并行拉取 {len(_cmp_codes)} 只股票数据：行情、技术面、相关性... 完成后自动显示，无需切换页面。",
                icon="⏳",
            )
            st.progress(0.0, text="等待对比结果...")
            st_autorefresh(interval=1000, limit=30, key="compare_autorefresh")
            return

    rows = st.session_state.get("_cmp_rows")
    if not rows:
        st.info("👇 在下方输入股票代码/名称后点击「开始对比」。已预填示例（5只），直接点击即可查看效果。")
        return

    # 部分标的行情缺失提示
    failed = [r.get("name", str(r.get("code", "?"))) for r in rows if r.get("error")]
    if failed:
        st.warning(f"以下标的行情获取失败，已按中性默认展示：{'、'.join(failed)}")

    _period = st.session_state.get("_cmp_period", st.session_state.get("_cmp_period_input", 120))

    # ── 头部 + 核心结论 + 横向对比表（同一 compare-wrap 内）──
    st.markdown(
        '<div class="compare-wrap">' + compare_css()
        + build_header(rows, _period)
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

    # ── 新增维度：估值 · 财务 · 资金面 ──
    st.markdown(build_extra_card(rows), unsafe_allow_html=True)

    # ── 两两对比选择器 + 选中 pair 卡片 ──
    if len(rows) >= 2:
        pairs = [(rows[i], rows[j]) for i in range(len(rows)) for j in range(i + 1, len(rows))]
        # ⚠️ 兜底：上游对比结果若缺 'name' 字段，a['name'] 会抛 KeyError；统一用 .get 兜底
        pair_labels = [f"{a.get('name', '?')} vs {b.get('name', '?')}" for a, b in pairs]
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
        help="短期=动量量能；长期=趋势稳定；价值=低估(PB/股息)；板块=业务关联度；业绩=催化；"
             "政策=政策敏感；宏观=弹性；微观=技术结构；资金=主力净流入；事件=输入事件看利好利空。",
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


fragment_compare_result()
