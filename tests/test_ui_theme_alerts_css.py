"""
tests/test_ui_theme_alerts_css.py
================================
T-278 原生组件 CSS 统一收敛守卫：双彩条修复 / 长文收敛 / 表格响应式 / 分隔线降噪。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.ui_theme import dashboard_sf_css  # noqa: E402

_CSS = dashboard_sf_css()


def test_double_bar_fixed():
    """双彩条修复：::before 绝对条被禁用，只留 border-left 单源。"""
    assert '[data-testid="stAlert"]::before' in _CSS
    # 该规则必须 display:none（不再画第二条彩条）
    idx = _CSS.index('[data-testid="stAlert"]::before')
    assert "display:none" in _CSS[idx:idx + 120], "alert ::before 双彩条未修复"


def test_alert_long_text_bounded():
    """长文收敛：stAlertContent 有 max-height（避免整卡撑满屏）。"""
    assert "stAlertContent" in _CSS
    idx = _CSS.index("max-height:420px")
    assert idx > 0, "alert 长文 max-height 缺失"


def test_dataframe_responsive():
    """表格响应式：容器 overflow auto + max-height（保留交互，不替换为 HTML）。"""
    assert "overflow:auto!important" in _CSS
    assert "overflow-x:auto!important" in _CSS
    assert "max-height:560px" in _CSS


def test_divider_subtle():
    """分隔线降噪：虚线 + 降透明度。"""
    assert "border-top:1px dashed" in _CSS


def test_semantic_colors_present_and_untouched():
    """红线：A 股语义色 token 仍为权威值（T-278 只动容器样式，不碰颜色语义）。"""
    # 涨跌语义（_TOKEN_CSS）：涨=红、跌=绿
    from modules.ui_kit import _TOKEN_CSS
    assert "--ss-up:#ff4d4f" in _TOKEN_CSS and "--ss-down:#00d486" in _TOKEN_CSS, \
        "A 股红涨绿跌语义 token 被改写（铁律 2）"
