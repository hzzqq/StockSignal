"""pytest 全局前置（根目录 conftest）。

确保在收集任何测试之前，streamlit 就以**真实**（venv 已装 1.59.2，API 完整）形式
常驻 sys.modules。这样各测试文件即使写了 `sys.modules["streamlit"] = 残缺桩`
（历史遗留），也会被真实 streamlit 占位、无法覆盖，从而避免 import 真实模块
（如 modules.session 的 @st.cache_data / @st.dialog / `from streamlit import v1`）
时因拿到残缺桩而抛 AttributeError。

若 venv 未安装 streamlit，则提供一份完整兜底桩（装饰器返回 identity，其余 noop），
行为等价。
"""
import sys


def _install_streamlit():
    # 优先使用真实 streamlit
    try:
        import streamlit  # noqa: F401  (真实，API 完整)
        return
    except Exception:
        pass

    # 兜底：venv 无 streamlit 时提供完整桩
    import types

    class _CtxMgr:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __getattr__(self, name):
            def _noop(*a, **k):
                return False

            return _noop

    st = types.ModuleType("streamlit")
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
    sys.modules["streamlit"] = st


_install_streamlit()
