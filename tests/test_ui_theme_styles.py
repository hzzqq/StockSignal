# -*- coding: utf-8 -*-
"""tests/test_ui_theme_styles.py — T-186 四风格主题切换器守卫。

覆盖：注册表完整性 / 红涨绿跌语义四套钉住 / mode 联动 / classic 默认零影响 /
apply_theme 接线 / 切换器存在。纯注册表与源码断言，不渲染 UI。
"""
from __future__ import annotations

import inspect

from modules import ui_theme
from modules.ui_theme import STYLE_PRESETS


def test_registry_complete():
    """五套齐全：classic + 四新风格；字段完整。"""
    assert set(STYLE_PRESETS) == {
        "classic", "terminal", "swiss", "aurora", "ink", "cyber"}
    for k, p in STYLE_PRESETS.items():
        assert set(p) == {"label", "mode", "vars", "extra"}, k
        assert isinstance(p["label"], str) and p["label"], k


def test_semantic_colors_pinned_all_styles():
    """红涨绿跌四套全钉住：--buy/--ss-up 为红系，--sell/--ss-down 为绿系，绝不反转。"""
    reds = {"terminal": "#ff5c5c", "swiss": "#d93025",
            "aurora": "#ff5c7a", "ink": "#c0392b", "cyber": "#ff2a6d"}
    greens = {"terminal": "#3ddc97", "swiss": "#0f9d58",
              "aurora": "#2fe0a8", "ink": "#1e7f6b", "cyber": "#00ff9f"}
    for k in ("terminal", "swiss", "aurora", "ink", "cyber"):
        vars_ = STYLE_PRESETS[k]["vars"]
        assert f"--buy:{reds[k]}" in vars_, k
        assert f"--sell:{greens[k]}" in vars_, k
        assert f"--ss-up:{reds[k]}" in vars_, k
        assert f"--ss-down:{greens[k]}" in vars_, k


def test_mode_binding():
    """terminal/aurora 锁暗色，swiss/ink 锁亮色，classic 不锁（尊重用户暗/亮切换）。"""
    assert STYLE_PRESETS["terminal"]["mode"] == "dark"
    assert STYLE_PRESETS["aurora"]["mode"] == "dark"
    assert STYLE_PRESETS["swiss"]["mode"] == "light"
    assert STYLE_PRESETS["ink"]["mode"] == "light"
    assert STYLE_PRESETS["cyber"]["mode"] == "dark"
    assert STYLE_PRESETS["classic"]["mode"] is None


def test_classic_default_noop():
    """classic 零注入：vars/extra 均为空——行为与特性上线前逐位一致。"""
    assert STYLE_PRESETS["classic"]["vars"] == ""
    assert STYLE_PRESETS["classic"]["extra"] == ""


def test_apply_theme_wired():
    """apply_theme 已接线：开头 _sync_style_mode()，inject_kit_css 后 inject_style_css()。"""
    src = inspect.getsource(ui_theme.apply_theme)
    assert "_sync_style_mode()" in src
    assert "style_switcher()" in src  # T-187a：切换器必须挂载（曾漏挂致侧边栏无入口）
    assert src.index("style_switcher()") < src.index("inject_kit_css()")
    assert src.index("inject_kit_css()") < src.index("inject_style_css()")


def test_switcher_and_injector_exist():
    """T-195 侧栏退役后：style_switcher 保留兼容（sidebar 渲染退役），注入器仍在。

    界面风格选择的用户入口已迁移至顶栏右侧用户下拉（top_nav ssSetStyle JS），
    持久化管道（URL prefs/localStorage/后端）与 apply_style_css 注入不变。
    """
    assert callable(ui_theme.style_switcher)  # 兼容保留（生产不再调用）
    assert callable(ui_theme.inject_style_css)
    assert callable(ui_theme._sync_style_mode)
    sw_src = inspect.getsource(ui_theme.style_switcher)
    assert "selectbox" in sw_src  # 函数体保留（未删，回滚可用）
    # 生产入口迁移：顶栏 JS 风格下拉必须存在
    from modules import top_nav
    tn_src = inspect.getsource(top_nav)
    assert "ssSetStyle" in tn_src, "顶栏 JS 风格切换必须存在"
    assert "ss_prefs" in tn_src, "顶栏 JS 必须写 prefs localStorage（三路持久化一致）"


def test_non_classic_styles_have_visual_layers():
    """四套新风格的 vars/extra 均非空（真的会注入东西，不是空壳）。"""
    for k in ("terminal", "swiss", "aurora", "ink", "cyber"):
        assert STYLE_PRESETS[k]["vars"], k
        assert STYLE_PRESETS[k]["extra"], k


def test_st_toolbar_hidden_both_modes():
    """T-200：stToolbar（Deploy 按钮+状态控件的容器）必须整体隐藏——其悬浮在
    自绘顶栏右上角图标（搜索/✦/⚙️/👤）之上造成重叠并拦截点击；曾只清 padding
    未隐藏，Deploy 文字压住图标。dark/light 两套全局 CSS 都要钉住。"""
    marker = '[data-testid="stToolbar"] { display: none !important; }'
    assert marker in ui_theme._DARK_CSS
    assert marker in ui_theme._LIGHT_CSS


def test_ink_seal_below_topnav():
    """T-200：墨韵印章 top 必须 ≥ 顶栏 52px（曾 top:16px 上半截被不透明顶栏盖住）。"""
    extra = STYLE_PRESETS["ink"]["extra"]
    assert 'content:"量策"' in extra
    assert 'content:"量策";position:fixed;top:64px' in extra
