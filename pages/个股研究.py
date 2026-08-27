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

from modules.page_utils import render_standard_page
from modules.ui_kit import info_banner
render_standard_page(title="个股研究", icon="🎯")
info_banner("本页合并「快速选取」与「深度分析」两个子视图，用顶部分段切换；所有数据仅供参考，不构成投资建议。", icon="🎯")

from modules.session import trading_autorefresh
trading_autorefresh(key="hub_autorefresh")

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

    注意：子页多数已改用 ``modules.page_utils.render_standard_page``，该模块在导入时
    已把这三个函数绑进自己的命名空间，因此必须一并 patch，否则 no-op 不生效。
    """
    import modules.ui_theme as _uit
    import modules.session as _sess
    import modules.page_utils as _pu

    def _noop(*a, **k):
        return None

    _saved = (_uit.apply_page_config, _sess.require_auth, _sess.render_user_badge,
              _pu.apply_page_config, _pu.require_auth, _pu.render_user_badge)
    _uit.apply_page_config = _noop
    _sess.require_auth = _noop
    _sess.render_user_badge = _noop
    _pu.apply_page_config = _noop
    _pu.require_auth = _noop
    _pu.render_user_badge = _noop
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
        (_uit.apply_page_config, _sess.require_auth, _sess.render_user_badge,
         _pu.apply_page_config, _pu.require_auth, _pu.render_user_badge) = _saved
        st.session_state["_embed_active"] = False


_options = list(_SUBPAGES.keys())
# 支持从搜索 / 龙虎榜 / 其它页跳转时预选子视图（默认「快速选取」）
st.session_state.setdefault("hub_gyj_view", _options[0])
if st.session_state.get("hub_gyj_view") not in _options:
    st.session_state["hub_gyj_view"] = _options[0]

_view = st.radio(
    "研究视图",
    _options,
    horizontal=True,
    label_visibility="collapsed",
    key="hub_gyj_view",
)
st.divider()
_run_subpage(_SUBPAGES[_view])
