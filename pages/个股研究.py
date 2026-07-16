"""
个股研究（合并页）
------------------
将「股票选取」与「个股分析」合并为单页，用分段选择器切换两个子视图：
  ⚡ 快速选取  → pages/1_股票选取.py（参数设置 / K线 / 技术面 / 打分 / 自选·垃圾股）
  🔬 深度分析  → pages/2_个股分析.py（决策仪表盘 / 五维雷达 / 作战计划）

实现方式（monkeypatch exec）：
  临时把子页顶部样板函数（apply_page_config / require_auth / render_user_badge）
  替换为 no-op 后再 exec 子页源码，仅运行「当前选中」的子视图。
  → 子页文件保持零改动、仍可独立运行；避免了 st.tabs 预渲染所有子页导致的重复取数性能回退。
"""
import os
import streamlit as st

from modules.ui_theme import apply_page_config
apply_page_config(page_title="个股研究", page_icon="🎯", layout="wide")
st.session_state["_active_page"] = __file__

from modules.session import require_auth, render_user_badge
require_auth()
render_user_badge(sidebar=True)

_HERE = os.path.dirname(__file__)
_SUBPAGES = {
    "⚡ 快速选取": os.path.join(_HERE, "1_股票选取.py"),
    "🔬 深度分析": os.path.join(_HERE, "2_个股分析.py"),
}


def _run_subpage(path: str) -> None:
    """在合并页内安全运行子页源码。

    临时把子页会重复执行的样板函数 no-op 化（子页仍会 import 它们，
    绑定到当前的 no-op），避免二次 set_page_config / 二次全局组件 / 二次用户徽标。
    子页其余业务逻辑与 session_state 命名空间彼此独立，正常执行。
    """
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
    finally:
        _uit.apply_page_config, _sess.require_auth, _sess.render_user_badge = _saved
        st.session_state["_embed_active"] = False


_options = list(_SUBPAGES.keys())
# 支持从搜索 / 龙虎榜 / 其它页跳转时预选子视图（默认「快速选取」）
st.session_state.setdefault("hub_gyj_view", _options[0])
if st.session_state.get("hub_gyj_view") not in _options:
    st.session_state["hub_gyj_view"] = _options[0]

st.markdown("### 🎯 个股研究")
_view = st.radio(
    "研究视图",
    _options,
    horizontal=True,
    label_visibility="collapsed",
    key="hub_gyj_view",
)
st.divider()
_run_subpage(_SUBPAGES[_view])
