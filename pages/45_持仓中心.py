"""
持仓中心（合并页）
------------------
将「自选股监控」「仓位管理」「组合收益」合并为单页，用分段选择器切换三个子视图：
  ⭐ 自选池    → pages/46_自选股监控.py（自选股实时行情 / 股票池管理）
  💼 持仓      → pages/40_仓位管理.py（持仓盈亏 / 导入导出）
  📈 收益归因  → pages/41_组合收益.py（净值曲线 / 基准对比 / 收益贡献 / 回撤）

实现方式（monkeypatch + 直接调用）：同「个股研究」，子视图渲染主体已抽取至
modules.portfolio_views（P0-1 契约，exec 动态加载已消除），仅运行当前选中子视图。
"""
import os
import streamlit as st
import streamlit.components.v1 as components
from modules.page_utils import render_standard_page
import modules.scroll_nav as sn
from modules.ui_kit import info_banner
from modules.widgets import render_entry_cards
render_standard_page(title='持仓中心', icon='💼', caption='⚠️ 持仓中心为模拟/历史数据聚合视图，仅供学习，不构成投资建议。')
info_banner("本页合并「自选池 / 持仓 / 收益归因」三个子视图，用顶部分段切换；持仓与收益均为模拟或历史数据，仅供学习。", icon="💼")
_HERE = os.path.dirname(__file__)
_SUBPAGES = {'⭐ 自选池': os.path.join(_HERE, '46_自选股监控.py'), '💼 持仓': os.path.join(_HERE, '40_仓位管理.py'), '📈 收益归因': os.path.join(_HERE, '41_组合收益.py')}
# P0-1 契约：path→callable 映射（键复用 _SUBPAGES 路径值），同「个股研究」24 页
from modules.portfolio_views import render_watchlist_monitor, render_position_manager, render_portfolio_returns
_SUBPAGE_FNS = {
    _SUBPAGES['⭐ 自选池']: render_watchlist_monitor,  # P0-1c 已抽取
    _SUBPAGES['💼 持仓']: render_position_manager,  # P0-1c 已抽取
    _SUBPAGES['📈 收益归因']: render_portfolio_returns,  # P0-1c 已抽取
}

def _run_subpage(path: str) -> None:
    """在合并页内运行子视图渲染函数（临时 no-op 子页样板函数，避免重复渲染）。

    子视图渲染主体已抽取至 modules.portfolio_views（P0-1 契约，exec 动态加载已消除）；
    样板函数仍需 patch：渲染函数内部会调用 render_standard_page 等页面级样板，
    嵌入态必须 no-op，否则与合并页重复渲染。
    """
    import modules.ui_theme as _uit
    import modules.session as _sess
    import modules.page_utils as _pu

    def _noop(*a, **k):
        return None
    _saved = (_uit.apply_page_config, _sess.require_auth, _sess.render_user_badge, _pu.apply_page_config, _pu.require_auth, _pu.render_user_badge)
    _uit.apply_page_config = _noop
    _sess.require_auth = _noop
    _sess.render_user_badge = _noop
    _pu.apply_page_config = _noop
    _pu.require_auth = _noop
    _pu.render_user_badge = _noop
    st.session_state['_embed_active'] = True
    try:
        _SUBPAGE_FNS[path]()
    except Exception as exc:
        from modules.page_guard import render_error_card
        render_error_card(f'子模块 {os.path.basename(path)}', exc, hint='该子视图加载失败，已隔离。可切换上方视图或刷新页面重试。')
        if st.button('🔄 重试', key='hub_subpage_retry'):
            st.rerun()
    finally:
        _uit.apply_page_config, _sess.require_auth, _sess.render_user_badge, _pu.apply_page_config, _pu.require_auth, _pu.render_user_badge = _saved
        st.session_state['_embed_active'] = False
_options = list(_SUBPAGES.keys())
st.session_state.setdefault('hub_cang_view', _options[0])
if st.session_state.get('hub_cang_view') not in _options:
    st.session_state['hub_cang_view'] = _options[0]
_view = st.radio('持仓视图', _options, horizontal=True, label_visibility='collapsed', key='hub_cang_view', help='切换三个子视图：⭐ 自选池（自选股实时行情）/ 💼 持仓（持仓盈亏与导入导出）/ 📈 收益归因（净值曲线与收益贡献）。切换会重新加载对应模块。')
render_entry_cards([
    {'path': 'pages/46_自选股监控.py', 'label': '⭐ 自选池', 'icon': '⭐', 'desc': '自选股实时行情 / 股票池管理'},
    {'path': 'pages/40_仓位管理.py', 'label': '💼 持仓', 'icon': '💼', 'desc': '持仓盈亏 / 导入导出'},
    {'path': 'pages/41_组合收益.py', 'label': '📈 收益归因', 'icon': '📈', 'desc': '净值曲线 / 基准对比 / 收益贡献'},
], columns=3, active_label=_view)
st.caption(f"📍 当前：持仓中心 › **{_view}**")
if st.button('🔄', key='hub_manual_refresh', help='刷新：重新加载持仓中心数据'):
    st.rerun()
st.session_state.setdefault('hub_recent_viewed', [])
_hrv_left, _hrv_right = st.columns([3, 1])
with _hrv_left:
    _hrv_sym = st.text_input('输入标的代码', key='hub_recent_input')
with _hrv_right:
    if st.button('记录', key='hub_recent_add'):
        _s = (_hrv_sym or '').strip().upper()
        if _s:
            _hist = st.session_state['hub_recent_viewed']
            if _s in _hist:
                _hist.remove(_s)
            _hist.insert(0, _s)
            st.session_state['hub_recent_viewed'] = _hist[:8]
if st.session_state['hub_recent_viewed']:
    st.caption('🕘 最近浏览：' + '\u3000'.join((f'#{s}' for s in st.session_state['hub_recent_viewed'])))
st.divider()
with st.spinner(f'正在加载「{_view}」...'):
    _run_subpage(_SUBPAGES[_view])
st.caption('数据来源：东方财富 / 新浪财经。')
st.divider()
if st.button('↑ 回到顶部', key='hub_top', width="stretch"):
    st.session_state['_hub_scroll_top'] = True
if st.session_state.get('_hub_scroll_top'):
    sn.back_to_top_button()
    st.session_state['_hub_scroll_top'] = False
with st.expander('⌨️ 快捷键'):
    st.markdown('- `🔄 刷新`：点击顶部「🔄 刷新」按钮重载当前合并页全部子视图')
    st.markdown('- `↑ 回到顶部`：点击底部「↑ 回到顶部」返回页首')
    st.markdown('- `持仓视图`：使用上方分段选择器在 ⭐自选池 / 💼持仓 / 📈收益归因 间切换')
    st.markdown('- `🕘 最近浏览`：在上方输入框记录想跟踪的标的代码，纯前端记忆')