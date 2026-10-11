"""
tests/test_zero_gap_collapse.py
===============================
T-263 顶部空白收敛守卫（用户实证：页43 hero 前堆积 22 个零高注入容器 ≈ 363px 纯 gap）。

契约：
1. ui_kit 注入层必须携带「纯注入容器不占 flex gap」CSS（两形态：style 首拍 / link 首拍），
   且选择器必须带 :not(:has(> :not(style):not(link)))——保证混合可见内容的容器
   （顶栏 mega markdown = style,style,style,div / st.caption / 卡片）永不误伤。
2. 零高组件 iframe 自隐藏 JS（ZERO_GAP_HIDE_SELF_JS）必须接入 scroll_nav 单次注入
   脚本（占位符必须被替换）。
3. prefs_persist 两个 height=0 注入脚本必须并入自隐藏 JS 且保持单 <script> 块
   （scroll_nav 模块约束：同 payload 第二段 <script> 不保证执行）。

mutation 验证：注释 ui_kit 规则 / 断开 __ZERO_GAP_JS__ 接线 / 移除 prefs 并入 → 对应用例变红。
"""
import re

from modules import prefs_persist, scroll_nav
from modules.ui_kit import _KIT_CSS


def test_kit_css_carries_zero_gap_rules():
    """契约1：两条纯注入容器收敛规则必须存在于 _KIT_CSS。"""
    rule = (
        '[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]'
        ':has([data-testid="stMarkdownContainer"] > style:first-child)'
    )
    assert rule in _KIT_CSS, "T-263 收敛规则（style 首拍形态）缺失"
    assert '[data-testid="stMarkdownContainer"] > link:first-child' in _KIT_CSS, \
        "T-263 收敛规则（link 首拍形态，字体注入）缺失"
    assert _KIT_CSS.count("{display:none}") >= 2, "收敛规则 display:none 动作缺失"


def test_selector_excludes_mixed_visible_content():
    """契约1（防误伤面）：选择器必须显式排除任何非 style/link 子节点。"""
    guard = ':not(:has([data-testid="stMarkdownContainer"] > :not(style):not(link)))'
    assert guard in _KIT_CSS, (
        "误伤防线缺失：选择器未排除混合可见内容容器——"
        "顶栏 mega / st.caption / 卡片等 markdown 会被整块隐藏"
    )


def test_scroll_nav_zero_gap_js_wired():
    """契约2：_nav_script 产物必须并入自隐藏 JS 且不留占位符。"""
    body = scroll_nav._nav_script(False, 120, 150, True, False)
    assert "__ZERO_GAP_JS__" not in body, "占位符未替换——接线断裂"
    assert "stElementContainer" in body, "自隐藏 JS 未并入单次注入脚本"
    assert re.search(r"contentWindow", body) and re.search(r"===\s*window", body), "自识别逻辑缺失"


def test_prefs_persist_scripts_embed_zero_gap_single_block():
    """契约3：save/restore 两个注入脚本必须并入自隐藏 JS，且保持单 <script> 块。"""
    captured = {}

    def _fake_html(payload, height=0, **kw):
        captured["payload"] = payload
        captured["height"] = height

    orig = prefs_persist.components.html
    prefs_persist.components.html = _fake_html
    try:
        prefs_persist.save_prefs({"theme_mode": "dark"})
        p1 = captured["payload"]
        assert p1.count("<script>") == 1, "save_prefs 出现多 <script> 块（不保证执行）"
        assert "stElementContainer" in p1, "save_prefs 未并入自隐藏 JS"
        assert "localStorage.setItem" in p1, "save_prefs 原有功能语句丢失"

        prefs_persist.restore_prefs_from_local_storage()
        p2 = captured["payload"]
        assert p2.count("<script>") == 1, "restore 出现多 <script> 块（不保证执行）"
        assert "stElementContainer" in p2, "restore 未并入自隐藏 JS"
        assert "URLSearchParams" in p2, "restore 原有功能语句丢失"
        assert captured["height"] == 0
    finally:
        prefs_persist.components.html = orig


def test_zero_gap_js_targets_only_self():
    """自隐藏 JS 只允许命中自身 iframe（contentWindow 恒等判断），不得按索引/类名误伤其他组件。"""
    js = scroll_nav.ZERO_GAP_HIDE_SELF_JS
    assert re.search(r"contentWindow", js) and re.search(r"===\s*window", js), \
        "缺少自身识别（contentWindow 恒等）判断"
    assert "querySelectorAll('iframe')" in js or "querySelectorAll(\"iframe\")" in js
    # 不允许出现按 class/序号直接隐藏其他容器的危险模式
    assert "stIFrame" not in js, "不得按 stIFrame 类名批量隐藏（会误伤真实图表组件）"
