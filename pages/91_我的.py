"""
页面6：我的
个人信息入口、我的自选股、快捷操作。
"""

import streamlit as st
import requests
import time
from datetime import datetime

from modules.session import safe_switch_page, API_BASE, get_user, get_token, persist_prefs, get_avatar_path, save_avatar, get_avatar_data_url, set_avatar_data_url, save_avatar_to_backend, render_avatar
from modules.ui_theme import get_current_mode, FONT_SCALE, FONT_DEFAULT, sf_metric
from modules.format_helpers import safe_int

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_metric

# 安全解析字体档位在选项列表中的下标；legacy 值不在选项中时回退到默认档位，避免 .index() 抛 ValueError。
from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, xc_content_card, info_banner, ss_fold_useful, ss_hover_preview
from modules.widgets import render_entry_cards
from modules.page_utils import fmt_rel as _fmt_rel
def _resolve_font_index(value, font_opts, default):
    keys = list(font_opts.keys())
    if value in keys:
        return keys.index(value)
    return keys.index(default) if default in keys else 0
from modules.page_widgets import _empty_info
# 确保 theme_mode 在 apply_theme()/require_auth() 之前就有默认值，避免默认 dark 与后面被改回 light 造成闪烁/状态错位
st.session_state.setdefault("theme_mode", "dark")

# 加法式风险提示/免责声明作为副标题
render_standard_page(
    title="我的", icon="👤",
    caption="⚠️ 本页展示的数据与分析仅供参考，不构成任何投资建议。",
)

user = get_user() or {}

# 加法式操作成功反馈：刷新本页缓存后给出成功提示
if st.session_state.get("_my_cache_toast"):
    st.session_state.pop("_my_cache_toast", None)
    xc_success_box("✅ 本页缓存已刷新")


def _cached_get(url, headers, ttl=10):
    """加法式性能优化：同一页面内的交互（切换主题/字体等）会触发整页重跑，
    原实现每次重跑都重新打 /api/watchlist、/api/auth/logins，造成重复请求与卡顿。
    这里用 session_state 做短 TTL(默认10秒) 缓存，避免短时间内重复拉取；
    并限制缓存条目上限防 session_state 膨胀。返回的 Response 对象可重复调用 .json()。"""
    _cache = st.session_state.setdefault("_my_cached_get", {})
    _now = time.time()
    if url in _cache:
        _ts, _val = _cache[url]
        if _now - _ts < ttl:
            return _val
    _resp = requests.get(url, headers=headers, timeout=5)
    _cache[url] = (_now, _resp)
    if len(_cache) > 20:
        _oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(_oldest, None)
    return _resp
