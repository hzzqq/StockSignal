import logging
from modules.ui_kit import page_hero
logger = logging.getLogger(__name__)
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


def render_standard_page(title, icon="📊", caption=None, layout="wide", auth=True):
    """渲染页面标准头部，返回 dark(bool)。

    自动标记调用方页面为活跃页（用于侧边栏高亮），无需每个页面手写
    ``st.session_state["_active_page"] = __file__``。

    ``auth`` 默认 True（执行 require_auth + 用户徽章）。管理员页若已调用
    ``require_admin()``（内部已含 require_auth），传 ``auth=False`` 避免双重
    注入全局组件（重复 key 异常）。
    """
    apply_page_config(page_title=title, page_icon=icon, layout=layout)
    try:
        caller_file = inspect.stack()[1].filename
    except Exception as e:
        logger.warning(f"[page_utils] 处理异常: {e}")
        caller_file = __file__
    st.session_state["_active_page"] = caller_file
    if auth:
        require_auth()
    render_user_badge(sidebar=True)
    dark = _theme_is_dark()
    st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
    # 签名页头：图标 + 标题 + 副标题 + 实时状态胶囊（主题 / 交易时段）
    chips = _build_status_chips(dark)
    page_hero(title=title, icon=icon, subtitle=caption, chips=chips)
    return dark


def _build_status_chips(dark: bool) -> list:
    """构造页头右侧状态胶囊：主题模式 + A股交易时段。UI-only，无业务副作用。

    ★ chip 完全 inline style —— 不依赖外部 .ss-pill CSS class：
    streamlit 冷启动竞态下即便 ui_kit._KIT_CSS 未生效、chip 也照常可见。

    ★ 单一真理源 = 入参 ``dark``：不再读 session_state，调用方（render_standard_page
    已传入 ``_theme_is_dark()``）是唯一权威，避免「传参改了 chip 却没变」的隐 bug。
    """
    chips = []
    # 主题胶囊（白天/暗夜）—— 依据 dark 参数直接判定
    try:
        if dark:
            theme_html = (
                '<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                'font-weight:600;padding:5px 12px;border-radius:999px;'
                'border:1px solid #3b3b66;background:#1a1a2e;color:#c7d2fe">'
                '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                'background:#94a3b8"></span>暗夜</span>'
            )
        else:
            theme_html = (
                '<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                'font-weight:600;padding:5px 12px;border-radius:999px;'
                'border:1px solid #c7d2fe;background:#eef2ff;color:#4338ca">'
                '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                'background:#94a3b8"></span>白天</span>'
            )
        chips.append(theme_html)
    except Exception as e:
        logger.warning(f"[page_utils] 处理异常: {e}")
    # 交易时段胶囊（已休市 / 交易中）
    try:
        from modules.page_widgets import is_trading_now
        if is_trading_now():
            session_html = (
                '<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                'font-weight:600;padding:5px 12px;border-radius:999px;'
                'border:1px solid #ff4d4f;background:rgba(255,77,79,.10);color:#dc2626">'
                '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                'background:#ff4d4f;box-shadow:0 0 0 3px rgba(255,77,79,.25)"></span>交易中</span>'
            )
        else:
            session_html = (
                '<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                'font-weight:600;padding:5px 12px;border-radius:999px;'
                'border:1px solid #00d486;background:rgba(0,212,134,.10);color:#166534">'
                '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                'background:#00d486"></span>已休市</span>'
            )
        chips.append(session_html)
    except Exception as e:
        logger.warning(f"[page_utils] 处理异常: {e}")
    return chips


def import_autorefresh():
    """安全导入 st_autorefresh；模块缺失（老版 Streamlit）时返回 None。"""
    try:
        from modules.autorefresh import st_autorefresh
        return st_autorefresh
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[page_utils] 处理异常: {e}")
        return None


@cache_resource(show_spinner=False)
def get_fetcher():
    """模块级 StockFetcher 单例（替代各页面重复的 ``@st.cache_resource`` 包装）。"""
    return StockFetcher()
