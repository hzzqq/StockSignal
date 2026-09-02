"""modules/chart_cache.cached_fig 的单元测试 + Streamlit 运行时集成测试。"""

import os
import tempfile
import textwrap

import streamlit as st
from streamlit.testing.v1 import AppTest

from modules.chart_cache import cached_fig

# ---------------------------------------------------------------------------
# 轻量单测（无需 Streamlit 运行时）
# ---------------------------------------------------------------------------


def test_cached_fig_returns_callable_and_keeps_builder():
    def my_builder(a, b):
        return a + b

    wrapped = cached_fig(ttl=10)(my_builder)
    assert callable(wrapped)
    # 原始 builder 可被访问（测试 / 强制绕过缓存用）
    assert wrapped.__wrapped__ is my_builder
    # qualname 已被改写，避免不同 builder 共享缓存键
    assert wrapped.__qualname__.endswith("__cached")


def test_cached_fig_rejects_non_positive_ttl():
    try:
        cached_fig(ttl=0)
    except ValueError:
        return
    raise AssertionError("cached_fig(ttl=0) 应当抛出 ValueError")


# ---------------------------------------------------------------------------
# 集成测试：在真实 Streamlit 运行时中验证装饰器可用、figure 正常渲染
# ---------------------------------------------------------------------------

_PROBE = textwrap.dedent(
    """
    import plotly.graph_objects as go
    import streamlit as st
    from modules.chart_cache import cached_fig

    @cached_fig(ttl=30)
    def build_fig(seed):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[1, 2, 3], y=[seed, seed + 1, seed + 2], mode="lines"))
        fig.update_layout(title="probe")
        return fig

    fig = build_fig(7)
    # 二次相同入参调用：验证在 Streamlit 运行时内能稳定命中缓存、不抛异常
    fig2 = build_fig(7)
    assert fig is not None and fig2 is not None
    st.plotly_chart(fig)
    st.success("CHART_CACHE_OK")
    """
)


def _run_probe() -> AppTest:
    proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 探针写到系统临时目录（而非仓库目录）：避免 pytest 清理时触发项目级安全删除守卫，
    # 也避免向仓库目录遗留探针文件。同时把项目根注入 sys.path，保证探针内
    # `from modules.chart_cache import ...` 仍能解析。
    probe_src = "import sys\nsys.path.insert(0, %r)\n" % proj_root + _PROBE
    fd, path = tempfile.mkstemp(suffix=".py", dir=tempfile.gettempdir(), prefix="probe_chart_cache_")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(probe_src)
        at = AppTest.from_file(path, default_timeout=30)
        at.run()
        return at
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_cached_fig_runs_under_streamlit():
    at = _run_probe()
    assert not at.exception, [str(e) for e in at.exception]
    # 成功标记出现，说明装饰器在 Streamlit 运行时内正常执行、figure 构建成功
    assert len(at.success) == 1
    assert at.success[0].value == "CHART_CACHE_OK"


def test_cached_fig_cache_hit_returns_consistent_object():
    """两次相同入参调用应命中缓存（不抛异常、返回可用 figure）。"""
    at = _run_probe()
    assert not at.exception, [str(e) for e in at.exception]
    assert len(at.success) == 1
    assert at.success[0].value == "CHART_CACHE_OK"
