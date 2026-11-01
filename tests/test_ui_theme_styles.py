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
    """六套齐全：classic + 四新风格 + finpro（T-276 金融终端 Pro）；字段完整。"""
    assert set(STYLE_PRESETS) == {
        "classic", "terminal", "swiss", "aurora", "ink", "cyber", "finpro"}
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

    界面风格选择的用户入口已迁移至顶栏右侧用户下拉（T-201 起为纯锚点导航），
    持久化管道（URL prefs/localStorage/后端）与 apply_style_css 注入不变。
    """
    assert callable(ui_theme.style_switcher)  # 兼容保留（生产不再调用）
    assert callable(ui_theme.inject_style_css)
    assert callable(ui_theme._sync_style_mode)
    sw_src = inspect.getsource(ui_theme.style_switcher)
    assert "selectbox" in sw_src  # 函数体保留（未删，回滚可用）
    # 生产入口迁移：T-201 起顶栏风格切换为纯锚点导航（用户手势不受 iframe
    # sandbox 限制；原 JS select+ssSetStyle 路径因作用域/sandbox 双重缺陷废除）
    from modules import top_nav
    tn_src = inspect.getsource(top_nav)
    assert "ss-style-opt" in tn_src, "顶栏风格锚点切换必须存在"
    assert 'href="?' in tn_src, "风格锚点必须以相对 ?prefs 查询串导航"


def test_non_classic_styles_have_visual_layers():
    """四套新风格的 vars/extra 均非空（真的会注入东西，不是空壳）。"""
    for k in ("terminal", "swiss", "aurora", "ink", "cyber"):
        assert STYLE_PRESETS[k]["vars"], k
        assert STYLE_PRESETS[k]["extra"], k


def test_l3_tokens_present_all_styles():
    """P1-3：七风格 L3 组件语义层 6 token 齐套（finpro 模板 + 五风格补齐）。

    classic 无自带 vars（test_classic_default_noop 锁空），其 6 token 走
    ui_kit._TOKEN_CSS :root 默认值（test_ui_kit_tokens 已锁），不在此断言。
    硬约束：token 只能追加进 vars 分号字符串，禁止给 preset dict 加新 key。
    """
    l3 = ("--ss-glow:", "--ss-glow-soft:", "--ss-hero-overlay:",
          "--ss-shadow-card:", "--ss-shadow-lift:", "--ss-shadow-hero:")
    for k in ("terminal", "swiss", "aurora", "ink", "cyber", "finpro"):
        v = STYLE_PRESETS[k]["vars"]
        missing = [t for t in l3 if t not in v]
        assert not missing, f"{k} 缺 L3 token: {missing}"


def test_form_tokens_pinned_all_styles():
    """批4：六非 classic 风格形态令牌（圆角档位）钉住——切风格不只换色。

    档位即设计规范：terminal 方角 2px / swiss 极简 4px / aurora 大圆角 18px /
    ink 温润 8px / cyber 锐角 4px / finpro 商务 10px。"""
    radius_card = {"terminal": "2px", "swiss": "4px", "aurora": "18px",
                   "ink": "8px", "cyber": "4px", "finpro": "10px"}
    for k, px in radius_card.items():
        v = STYLE_PRESETS[k]["vars"]
        assert f"--ss-radius-card:{px}" in v, k
        assert "--ss-radius:" in v, k


def test_style_form_layer_complete():
    """批4：_STYLE_FORM 形态层六风格齐套、classic 零影响、注入器接线。

    每风格形态 CSS 必须落到原生组件容器（stMetric/stPlotlyChart 至少其一），
    且互不相同（真差异化，不是复制粘贴同一份）。"""
    styles = ("terminal", "swiss", "aurora", "ink", "cyber", "finpro")
    for k in styles:
        css = ui_theme._STYLE_FORM.get(k)
        assert css and css.strip(), f"{k} 形态层缺失"
        assert "stMetric" in css or "stPlotlyChart" in css, k
    assert "classic" not in ui_theme._STYLE_FORM, "classic 必须零形态注入"
    assert len({ui_theme._STYLE_FORM[k].strip() for k in styles}) == len(styles), \
        "各风格形态层雷同——差异化失效"
    # 注入器接线：inject_style_css 必须消费 _STYLE_FORM
    inj = inspect.getsource(ui_theme.inject_style_css)
    assert "_STYLE_FORM" in inj, "inject_style_css 未接线形态层"


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


def test_apply_page_config_locks_mode_before_native_theme():
    """T-283 防回潮：apply_page_config 必须在原生主题选型（theme = DARK/LIGHT →
    set_option）之前 _sync_style_mode()，且 ui_style 随 URL prefs 提前就位。

    此前风格锁定在 apply_theme() 内才执行（晚于本函数的 set_option），强制暗色
    风格（finpro/terminal/aurora/cyber）冷加载首屏的原生组件（stAlert/下拉弹层
    等 emotion 计算件）按默认 light 渲染——finpro 深蓝页直插白底横条
    （2026-10-14 浏览器实测）。classic mode=None 不受影响。"""
    src = inspect.getsource(ui_theme.apply_page_config)
    assert "_sync_style_mode()" in src, \
        "apply_page_config 缺少 _sync_style_mode()——强制暗/亮风格冷加载原生主题将回退 light"
    assert src.index("_sync_style_mode()") < src.index("theme = STREAMLIT_THEME_DARK"), \
        "_sync_style_mode() 必须在原生主题选型之前调用"
    assert "setdefault('ui_style'" in src, \
        "prefs 恢复块必须就位 ui_style，否则 _sync_style_mode() 读不到风格等于空转"


def test_home_injects_dashboard_sf_css():
    """T-283 防回潮：首页必须注入全站组件收敛层 dashboard_sf_css。

    首页不走 render_standard_page（仅 apply_page_config），T-278/279/280 的
    原生 alert 深色卡 / caption 截断 / metric 等高 / 下载按钮 / pills 层从未在
    首页生效（st.warning 白横条，2026-10-14 浏览器实测 sfAlert=False）。
    注入顺序必须与 render_standard_page 一致（apply_page_config 之后）。"""
    import pathlib
    root = pathlib.Path(ui_theme.__file__).resolve().parent.parent
    src = (root / "app.py").read_text(encoding="utf-8")
    assert "dashboard_sf_css()" in src, "首页缺少 dashboard_sf_css() 注入"
    assert src.index("apply_page_config(") < src.index("dashboard_sf_css()"), \
        "dashboard_sf_css() 必须在 apply_page_config 之后注入（与 render_standard_page 同序）"
