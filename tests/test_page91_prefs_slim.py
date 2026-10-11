"""
tests/test_page91_prefs_slim.py
===============================
T-266 空间治理守卫（用户截图：91 页偏好设置区大卡片×4 + 全宽 progress 指示器 +
单元素 tabs + 重复说明行，纵向空间浪费严重；用户要求「不需要的空间去除，
不能去除的做成点击/悬停才显现」）。

契约：
1. ui_theme.sf_card：body 为空 → 渲染紧凑节标题 .sf-section-title（而非大卡片）；
   dashboard_sf_css 必须携带 .sf-section-title 样式（全站 30+ 处空卡片一次受益）。
2. pages/91_我的.py：
   - 不得再有「全宽 progress 主题指示器」（st.progress(100 if ...)）；
   - 不得再用单元素 tabs 包装偏好设置（`_pref_tab, = st.tabs`）；
   - 偏好设置必须收进 ss_fold_useful 折叠区（点击才显现，标签带摘要）；
   - 数据源降级链说明必须收进 ss_hover_preview（悬停才显现）；
   - 重复说明 caption（提示：切换后整个界面会立即刷新 / K线默认根数： / 板块刷新间隔：）
     不得回潮（说明语义并入控件 help 或页首一行总说明）。

mutation 验证：恢复 sf_card 大卡片分支 / 换回单元素 tabs → 对应用例变红。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_THEME = ROOT / "modules" / "ui_theme.py"
PAGE91 = ROOT / "pages" / "91_我的.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_sf_card_empty_body_compact():
    """契约1：sf_card 空 body 走紧凑节标题分支，非空 body 保持原大卡片。"""
    src = _src(UI_THEME)
    assert ".sf-section-title" in src, "紧凑节标题类缺失"
    assert "if not str(body).strip():" in src, "sf_card 空 body 分支缺失"
    # 空分支必须早于大卡片渲染（先 return 紧凑分支）
    i_compact = src.index("sf-section-title")
    i_bigcard = src.index('<div class="sf-card">')
    assert i_compact < i_bigcard, "紧凑分支未前置"
    # 样式必须在 dashboard_sf_css 内（随 render_standard_page 每页注入）
    assert ".sf-section-title{{" in src, "dashboard_sf_css 未携带 .sf-section-title 样式"


def test_page91_no_progress_indicator():
    """契约2a：装饰性全宽 progress 主题指示器不得回潮。"""
    src = _src(PAGE91)
    assert "st.progress(100 if" not in src, "全宽 progress 主题指示器回潮"
    assert 'text="当前主题"' not in src, "当前主题进度条文案回潮"


def test_page91_no_single_tab_wrapper():
    """契约2b：不得用单元素 tabs 包装偏好设置。"""
    src = _src(PAGE91)
    assert "_pref_tab" not in src, "单元素 tabs 包装回潮"


def test_page91_prefs_in_fold_with_summary():
    """契约2c：偏好设置收进 ss_fold_useful（点击才显现），标签带主题摘要。"""
    src = _src(PAGE91)
    assert 'ss_fold_useful("⚙️ 偏好设置"' in src, "偏好设置未收进 ss_fold_useful"
    assert "render_preferences()" in src, "偏好设置渲染调用缺失"
    # fold 必须在 render_preferences 的【调用】之前（包裹语义；定义在前不算）
    i_fold = src.index('ss_fold_useful("⚙️ 偏好设置"')
    i_render = src.index("render_preferences()", i_fold)
    assert i_fold < i_render


def test_page91_datasource_hint_hover():
    """契约2d：数据源降级链说明收进悬停预览（鼠标放上去才显现）。"""
    src = _src(PAGE91)
    assert "数据源降级链说明" in src
    assert "ss_hover_preview(" in src
    i_hover = src.index("数据源降级链说明")
    seg = src[max(0, i_hover - 400): i_hover + 400]
    assert "ss_hover_preview" in seg and "mini=True" in seg, "数据源说明未用悬停预览"
    # 原 6 行大 info 块不得回潮
    assert "StockSignal 数据源降级链**（按顺序尝试，第一个成功即用）：\\n" not in src


def test_page91_duplicate_captions_removed():
    """契约2e：重复说明 caption 不得回潮（语义并入 help/页首一行）。"""
    src = _src(PAGE91)
    for gone in (
        "提示：切换后整个界面会立即刷新",
        "K线默认根数：打开行情看板时默认展示的最近 N 根日K",
        "板块刷新间隔：交易时段内行业板块数据的自动刷新频率",
        "所有设置已实时生效并保存在浏览器内存中",
    ):
        assert gone not in src, f"重复说明回潮：{gone[:20]}…"


def test_page91_syntax_valid():
    """改动后页面必须可被 AST 解析（防静默语法损坏）。"""
    ast.parse(_src(PAGE91))
