"""离线纯函数测试：验证 _safe_title_html 做了 HTML 转义（修复存储型 XSS），
且保持业务语义（已读消息加删除线、None 安全）。

为避免导入 pages.L_消息中心 时触发 Streamlit / 网络 / 鉴权等副作用并污染全局
sys.modules（曾导致真实模块 import 期因残缺 streamlit 桩而失败），这里在**临时
命名空间**中导入页面（仅桩入完整 streamlit 与页面所需的 modules.* 子桩），导入后
立即恢复 sys.modules，做到零全局污染——后续测试（如 import 真实 modules.session
含 @st.cache_data / @st.dialog / streamlit.v1）不受影响。
"""
import importlib
import os
import sys
import types


class _CtxMgr:
    """通用上下文管理器 / Streamlit 容器桩：支持 with，且任意方法都返回自身或 False。"""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        def _noop(*a, **k):
            return False

        return _noop


def _make_module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def _build_streamlit_stub():
    """完整 streamlit 桩：装饰器（cache_data/dialog/fragment…）返回 identity 装饰器，
    其余函数返回 noop，保证任意 import / 调用都不抛错。"""
    st = _make_module("streamlit")
    st.session_state = {}
    st.query_params = {}
    st.cache_data = lambda *a, **k: (lambda f: f)
    st.cache_resource = lambda *a, **k: (lambda f: f)
    st.fragment = lambda *a, **k: (lambda f: f)
    st.dialog = lambda *a, **k: (lambda f: f)
    st.singleton = lambda *a, **k: (lambda f: f)
    st.container = lambda *a, **k: _CtxMgr()
    st.columns = lambda sizes, *a, **k: [_CtxMgr() for _ in sizes]
    st.spinner = lambda *a, **k: _CtxMgr()
    for fn in (
        "markdown", "title", "caption", "metric", "success", "info", "warning",
        "error", "button", "checkbox", "radio", "text_input", "text_area",
        "selectbox", "slider", "set_page_config", "rerun", "write", "header",
        "subheader", "json", "dataframe", "table", "image", "plotly_chart",
        "pyplot", "line_chart", "bar_chart", "sidebar", "expander", "tabs",
        "balloons", "snow", "toast", "exception", "code", "divider", "stop",
    ):
        setattr(st, fn, lambda *a, **k: None)

    def _getattr(name):
        if name.startswith("cache") or name.startswith("experimental_") or name in (
            "fragment", "dialog", "singleton",
        ):
            return lambda *a, **k: (lambda f: f)
        return lambda *a, **k: None

    st.__getattr__ = _getattr
    return st


def _load_safe_title_html():
    """在临时命名空间导入页面，取回 _safe_title_html 后恢复全局 sys.modules。"""
    saved = dict(sys.modules)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    # 临时命名空间：仅桩入完整 streamlit 与页面所需 modules.* 子桩
    sys.modules["streamlit"] = _build_streamlit_stub()
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
    try:
        mod = importlib.import_module("pages.L_消息中心")
        return mod._safe_title_html
    finally:
        # 恢复导入前状态：全局 sys.modules 零污染
        sys.modules.clear()
        sys.modules.update(saved)


_safe_title_html = _load_safe_title_html()


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
