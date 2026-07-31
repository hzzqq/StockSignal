"""页面公共骨架：消除 40+ 页面重复的样板代码。

提供高频复用的页面级工具，取代各页面里复制粘贴的头部初始化：

- ``render_standard_page(title, icon, caption, layout)``：
    统一执行 ``apply_page_config`` + 标记活跃页 + ``require_auth`` + 用户徽章 +
    主题判断 + 仪表盘 CSS + 标题 + 副标题；返回 ``dark(bool)`` 供后续图表使用。
- ``import_autorefresh()``：安全导入 ``st_autorefresh``（无则返回 None）。
- ``get_fetcher()``：模块级 ``@st.cache_resource`` 的 ``StockFetcher`` 单例。

错误边界（safe_fragment / safe_section / page_error_boundary）已在 ``page_guard``
中统一提供，本模块不重复。
"""
import inspect

import streamlit as st
from streamlit.runtime.caching import cache_resource

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.fetcher import StockFetcher


def render_standard_page(title, icon="📊", caption=None, layout="wide"):
    """渲染页面标准头部，返回 dark(bool)。

    自动标记调用方页面为活跃页（用于侧边栏高亮），无需每个页面手写
    ``st.session_state["_active_page"] = __file__``。
    """
    apply_page_config(page_title=title, page_icon=icon, layout=layout)
    try:
        caller_file = inspect.stack()[1].filename
    except Exception:
        caller_file = __file__
    st.session_state["_active_page"] = caller_file
    require_auth()
    render_user_badge(sidebar=True)
    dark = _theme_is_dark()
    st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
    st.title(f"{icon} {title}")
    if caption:
        st.caption(caption)
    return dark


def import_autorefresh():
    """安全导入 st_autorefresh；模块缺失（老版 Streamlit）时返回 None。"""
    try:
        from modules.autorefresh import st_autorefresh
        return st_autorefresh
    except Exception:  # noqa: BLE001
        return None


@cache_resource(show_spinner=False)
def get_fetcher():
    """模块级 StockFetcher 单例（替代各页面重复的 ``@st.cache_resource`` 包装）。"""
    return StockFetcher()
