"""G11 Zen 专注模式守卫。

三层锁定：
1. 静态契约：`_ZEN_CSS` 必须含隐藏侧栏/页头的选择器（防被改坏）。
2. 注入契约：`render_standard_page` 必须调用 `render_zen_toggle`（防单点注入被摘除）。
3. 运行时：AppTest 验证「关态不注入 / 开态注入 CSS」且均无未捕获异常。
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from modules import page_utils, zen_mode


def test_zen_css_hides_sidebar_and_header():
    css = zen_mode._ZEN_CSS
    assert 'section[data-testid="stSidebar"]{display:none' in css, "必须隐藏侧栏"
    assert 'stHeader' in css, "必须隐藏页头装饰"


def test_render_standard_page_injects_zen():
    src = inspect.getsource(page_utils.render_standard_page)
    assert "render_zen_toggle" in src, "render_standard_page 必须单点注入 Zen"
    assert "zen_mode" in src


def test_zen_enabled_is_exception_safe():
    # 无 session_state 上下文时也不得抛错
    assert zen_mode.zen_enabled() in (True, False)


def _zen_app_on():  # noqa: D401
    import streamlit as st
    st.session_state["zen_mode"] = True
    from modules.zen_mode import render_zen_toggle
    render_zen_toggle()


def _zen_app_off():
    import streamlit as st
    st.session_state.pop("zen_mode", None)
    from modules.zen_mode import render_zen_toggle
    render_zen_toggle()


def _run_and_collect(func):
    from streamlit.testing.v1 import AppTest
    try:
        at = AppTest.from_function(func, default_timeout=60)
    except FileNotFoundError:
        # 环境竞态自愈：全量跑下 AppTest 模块级 TMP_DIR 目录偶发被外部清理
        # （Streamlit 在模块级 tempfile.TemporaryDirectory 中落脚本，GC/清理竞态致目录早失）。
        # mkdir 重建后重试一次；仍失败则向上抛——真实缺陷不静默。
        from streamlit.testing.v1.app_test import TMP_DIR
        Path(TMP_DIR.name).mkdir(parents=True, exist_ok=True)
        at = AppTest.from_function(func, default_timeout=60)
    at.run()
    assert not at.exception, f"Zen 注入抛出异常: {[str(e) for e in at.exception]}"
    return " ".join(str(getattr(m, "value", "")) for m in at.markdown)


@pytest.mark.parametrize("func,expect_css", [
    (_zen_app_on, True), (_zen_app_off, False),
], ids=["on", "off"])
def test_zen_runtime(func, expect_css):
    joined = _run_and_collect(func)
    has_css = 'stSidebar' in joined and 'display:none' in joined
    assert has_css is expect_css


def test_tmpdir_self_heal_after_external_cleanup():
    """mutation 自验：TMP_DIR 目录被外部清空后，自愈重试必须跑通（防自愈逻辑假绿）。

    放文件末尾：自愈路径会重建目录，不影响同进程后续 AppTest 测试。"""
    import shutil

    from streamlit.testing.v1.app_test import TMP_DIR
    shutil.rmtree(TMP_DIR.name, ignore_errors=True)
    assert not Path(TMP_DIR.name).exists(), "mutation 前置失败：目录应已被删除"
    joined = _run_and_collect(_zen_app_on)
    assert "stSidebar" in joined, "自愈后 Zen CSS 未注入"
