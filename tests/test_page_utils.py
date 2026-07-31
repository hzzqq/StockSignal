"""page_utils 轻量离线测试（不依赖 Streamlit 运行时）。"""
from modules.page_utils import (
    render_standard_page,
    import_autorefresh,
    get_fetcher,
)
from modules.fetcher import StockFetcher


def test_get_fetcher_returns_stockfetcher():
    """get_fetcher 单例返回 StockFetcher 实例。"""
    f = get_fetcher()
    assert isinstance(f, StockFetcher)


def test_render_standard_page_is_callable():
    """render_standard_page 可被页面调用（真实调用需 Streamlit 运行时，此处只校验接口）。"""
    assert callable(render_standard_page)


def test_import_autorefresh_returns_callable_or_none():
    """import_autorefresh 返回可调用或 None（老版 Streamlit 缺失时）。"""
    r = import_autorefresh()
    assert r is None or callable(r)
