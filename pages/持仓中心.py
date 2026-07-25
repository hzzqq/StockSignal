"""
持仓中心（合并页）
------------------
将「自选股监控」「仓位管理」「组合收益」合并为单页，用分段选择器切换三个子视图：
  ⭐ 自选池    → pages/C_自选股监控.py（自选股实时行情 / 股票池管理）
  💼 持仓      → pages/5_仓位管理.py（持仓盈亏 / 导入导出）
  📈 收益归因  → pages/H_组合收益.py（净值曲线 / 基准对比 / 收益贡献 / 回撤）

实现方式（monkeypatch exec）：同「个股研究」，子页文件零改动、仅运行当前选中子视图。
"""
import os
import streamlit as st
import streamlit.components.v1 as components

from modules.ui_theme import apply_page_config
apply_page_config(page_title="持仓中心", page_icon="💼", layout="wide")
st.session_state["_active_page"] = __file__

from modules.session import require_auth, render_user_badge
require_auth()
render_user_badge(sidebar=True)

_HERE = os.path.dirname(__file__)
_SUBPAGES = {
    "⭐ 自选池": os.path.join(_HERE, "C_自选股监控.py"),
    "💼 持仓": os.path.join(_HERE, "5_仓位管理.py"),
    "📈 收益归因": os.path.join(_HERE, "H_组合收益.py"),
}


def _run_subpage(path: str) -> None:
    """在合并页内安全运行子页源码（临时 no-op 子页样板函数，避免重复渲染）。"""
    import modules.ui_theme as _uit
    import modules.session as _sess

    def _noop(*a, **k):
        return None

    _saved = (_uit.apply_page_config, _sess.require_auth, _sess.render_user_badge)
    _uit.apply_page_config = _noop
    _sess.require_auth = _noop
    _sess.render_user_badge = _noop
    st.session_state["_embed_active"] = True
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        g = {"__name__": "__main__", "__file__": path, "__builtins__": __builtins__}
        exec(compile(src, path, "exec"), g)
    except Exception as exc:  # noqa: BLE001
        # 子页异常隔离：单视图崩溃不影响合并页其它部分（错误边界）
        from modules.page_guard import render_error_card
        render_error_card(
            f"子模块 {os.path.basename(path)}",
            exc,
            hint="该子视图加载失败，已隔离。可切换上方视图或刷新页面重试。",
        )
        # 加法式失败重试：子视图加载异常时提供「🔄 重试」按钮（非 fragment，可用 st.rerun）。
        if st.button("🔄 重试", key="hub_subpage_retry"):
            st.rerun()
    finally:
        _uit.apply_page_config, _sess.require_auth, _sess.render_user_badge = _saved
        st.session_state["_embed_active"] = False


_options = list(_SUBPAGES.keys())
st.session_state.setdefault("hub_cang_view", _options[0])
if st.session_state.get("hub_cang_view") not in _options:
    st.session_state["hub_cang_view"] = _options[0]

st.markdown("### 💼 持仓中心")
# 加法式（新角度·风险提示）：合并页顶部明示数据属性与免责声明。
st.caption("⚠️ 持仓中心为模拟/历史数据聚合视图，仅供学习，不构成投资建议。")
# 加法式（新角度·页面间快捷跳转）：一键直达三个子视图对应独立页面。
_hc1, _hc2, _hc3 = st.columns(3)
with _hc1:
    st.page_link("pages/C_自选股监控.py", label="⭐ 自选股监控", icon="⭐")
with _hc2:
    st.page_link("pages/5_仓位管理.py", label="💼 仓位管理", icon="💼")
with _hc3:
    st.page_link("pages/H_组合收益.py", label="📈 组合收益", icon="📈")
_view = st.radio(
    "持仓视图",
    _options,
    horizontal=True,
    label_visibility="collapsed",
    key="hub_cang_view",
    help="切换三个子视图：⭐ 自选池（自选股实时行情）/ 💼 持仓（持仓盈亏与导入导出）/ 📈 收益归因（净值曲线与收益贡献）。切换会重新加载对应模块。",
)

# 加法式（新角度·手动刷新按钮）：顶部「🔄 刷新」按钮，重新加载当前合并页全部子视图（顶层非 fragment，st.rerun 安全）。
if st.button("🔄 刷新", key="hub_manual_refresh"):
    st.rerun()

# 加法式（新角度·最近浏览历史）：记录最近手动查看的标的，纯前端 session_state，chips 形式展示。
st.session_state.setdefault("hub_recent_viewed", [])
_hrv_left, _hrv_right = st.columns([3, 1])
with _hrv_left:
    _hrv_sym = st.text_input("输入标的代码", key="hub_recent_input")
with _hrv_right:
    if st.button("记录", key="hub_recent_add"):
        _s = (_hrv_sym or "").strip().upper()
        if _s:
            _hist = st.session_state["hub_recent_viewed"]
            if _s in _hist:
                _hist.remove(_s)
            _hist.insert(0, _s)
            st.session_state["hub_recent_viewed"] = _hist[:8]
if st.session_state["hub_recent_viewed"]:
    st.caption("🕘 最近浏览：" + "　".join(f"#{s}" for s in st.session_state["hub_recent_viewed"]))

st.divider()
with st.spinner(f"正在加载「{_view}」..."):
    _run_subpage(_SUBPAGES[_view])

# 加法式便利：长页面底部「↑ 回到顶部」按钮，通过 session_state 触发滚动。
# 加法式（新角度·数据来源标注）：明示聚合数据出处，纯展示不改动子视图。
st.caption("数据来源：东方财富 / 新浪财经。")
st.divider()
if st.button("↑ 回到顶部", key="hub_top", use_container_width=True):
    st.session_state["_hub_scroll_top"] = True
if st.session_state.get("_hub_scroll_top"):
    components.html("<script>window.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    st.session_state["_hub_scroll_top"] = False

# 加法式（新角度·键盘快捷键提示）：纯提示，不绑定真实快捷键逻辑，亦不改动既有布局。
with st.expander("⌨️ 快捷键"):
    st.markdown("- `🔄 刷新`：点击顶部「🔄 刷新」按钮重载当前合并页全部子视图")
    st.markdown("- `↑ 回到顶部`：点击底部「↑ 回到顶部」返回页首")
    st.markdown("- `持仓视图`：使用上方分段选择器在 ⭐自选池 / 💼持仓 / 📈收益归因 间切换")
    st.markdown("- `🕘 最近浏览`：在上方输入框记录想跟踪的标的代码，纯前端记忆")
