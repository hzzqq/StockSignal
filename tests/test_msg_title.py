"""
离线纯函数测试：验证 _safe_title_html 对消息标题做了 HTML 转义（修复存储型 XSS），
且保持业务语义（已读消息加删除线、None 安全）。

为避免导入 pages.L_消息中心 时触发 Streamlit / 网络 / 鉴权等副作用，这里在导入前
把 streamlit 及依赖的 modules.* 子模块全部打桩（stub）。
"""
import sys
import types


class _CtxMgr:
    """通用上下文管理器 / Streamlit 容器桩：支持 with，且任意方法都返回自身或 False。"""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        # 容器 / 列上的方法（checkbox/button/markdown/caption...）一律作为 no-op
        def _noop(*a, **k):
            return False
        return _noop


def _make_module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ── 1) 打桩 streamlit（必须在导入页面模块之前） ──
_st = _make_module("streamlit")
_st.session_state = {}
_st.query_params = {}
_st.cache_data = lambda *a, **k: (lambda f: f)  # 装饰器：原样返回函数
_st.markdown = lambda *a, **k: None
_st.title = lambda *a, **k: None
_st.caption = lambda *a, **k: None
_st.metric = lambda *a, **k: None
_st.success = lambda *a, **k: None
_st.info = lambda *a, **k: None
_st.radio = lambda *a, **k: "全部"
_st.text_input = lambda *a, **k: ""
_st.button = lambda *a, **k: False
_st.checkbox = lambda *a, **k: False
_st.rerun = lambda *a, **k: None
_st.spinner = lambda *a, **k: _CtxMgr()
_st.container = lambda *a, **k: _CtxMgr()
_st.columns = lambda sizes, *a, **k: [_CtxMgr() for _ in sizes]
sys.modules["streamlit"] = _st

# ── 2) 打桩 modules.* 子模块 ──
_mods = _make_module("modules")
sys.modules["modules"] = _mods
sys.modules["modules.ui_theme"] = _make_module(
    "modules.ui_theme",
    apply_page_config=lambda *a, **k: None,
    dashboard_sf_css=lambda *a, **k: "",
    _theme_is_dark=lambda *a, **k: False,
)
sys.modules["modules.session"] = _make_module(
    "modules.session",
    require_auth=lambda *a, **k: None,
    render_user_badge=lambda *a, **k: None,
    safe_switch_page=lambda *a, **k: None,
    api_get=lambda *a, **k: (500, {}),
    trading_autorefresh=lambda *a, **k: None,
)
sys.modules["modules.fetcher"] = _make_module(
    "modules.fetcher", StockFetcher=lambda: _CtxMgr()
)
sys.modules["modules.page_guard"] = _make_module(
    "modules.page_guard",
    safe_section=lambda *a, **k: _CtxMgr(),
    render_data_degradation_banner=lambda *a, **k: None,
    get_data_source_health=lambda *a, **k: {"status": "ok", "down": [], "degraded": []},
)
sys.modules["modules.page_widgets"] = _make_module(
    "modules.page_widgets", UP="#f00", DOWN="#0f0"
)

# ── 3) 导入被测函数（页面模块顶层代码会在桩环境内安全执行） ──
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.L_消息中心 import _safe_title_html  # noqa: E402


def test_normal_title_preserved():
    """正常标题应原样保留，不应被错误转义。"""
    assert _safe_title_html("正常标题 大涨 +3.21%") == "正常标题 大涨 +3.21%"


def test_script_tag_escaped():
    """含 <script> 的标题必须被转义，渲染后不应出现原始标签。"""
    out = _safe_title_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_read_wrapped_in_strikethrough():
    """已读消息（read=True）应包在 ~~ 删除线中。"""
    assert _safe_title_html("重要消息", read=True) == "~~重要消息~~"


def test_none_title_safe_empty():
    """None 标题应安全返回空字符串，不抛异常。"""
    assert _safe_title_html(None) == ""
    assert _safe_title_html(None, read=True) == "~~~~"


def test_html_entities_escaped():
    """其它 HTML 特殊字符也应被转义。"""
    out = _safe_title_html("<img src=x onerror=alert(1)>")
    assert "<img" not in out
    assert "&lt;img" in out
