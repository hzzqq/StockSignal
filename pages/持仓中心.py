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
    finally:
        _uit.apply_page_config, _sess.require_auth, _sess.render_user_badge = _saved
        st.session_state["_embed_active"] = False


_options = list(_SUBPAGES.keys())
st.session_state.setdefault("hub_cang_view", _options[0])
if st.session_state.get("hub_cang_view") not in _options:
    st.session_state["hub_cang_view"] = _options[0]

st.markdown("### 💼 持仓中心")
_view = st.radio(
    "持仓视图",
    _options,
    horizontal=True,
    label_visibility="collapsed",
    key="hub_cang_view",
    help="切换三个子视图：⭐ 自选池（自选股实时行情）/ 💼 持仓（持仓盈亏与导入导出）/ 📈 收益归因（净值曲线与收益贡献）。切换会重新加载对应模块。",
)
st.divider()
with st.spinner(f"正在加载「{_view}」..."):
    _run_subpage(_SUBPAGES[_view])
