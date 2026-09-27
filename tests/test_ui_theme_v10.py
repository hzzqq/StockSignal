"""
tests/test_ui_theme_v10.py — T-176 前端美观升级 v10 守卫（双主题质感增强层）。

【契约】老板拍板：双主题都做（暗色玻璃终端 / 亮色精致 SaaS）+ 克制微动效。
守卫钉住增强层的存在性与不可回退项：
  1. 暗色玻璃层：多层极光背景 + 玻璃卡片 + 数字渐变；
  2. 亮色 SaaS 层：分层柔和阴影 + 统一大圆角；
  3. 微动效共用件：淡入 keyframes + prefers-reduced-motion 降级 + ::selection；
  4. A股红涨绿跌语义色在两主题中不可反转（#ff4d4f 涨 / #00d486 跌）；
  5. ui_kit 令牌层有 v10 玻璃变量与 hero/stat 微动效。
纯字符串断言（CSS 层无逻辑），不触网、不渲染。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.ui_theme import _DARK_CSS, _LIGHT_CSS  # noqa: E402
from modules.ui_kit import _TOKEN_CSS  # noqa: E402


def test_dark_glass_layer_present():
    """暗色玻璃终端层：极光背景 + 玻璃卡片 + 数字渐变。"""
    assert "v10" in _DARK_CSS, "暗色主题缺 v10 增强层标记"
    assert _DARK_CSS.count("radial-gradient") >= 4, "暗色背景应为多层极光光斑"
    assert "backdrop-filter" in _DARK_CSS
    assert "--ss-glass-bg:linear-gradient" in _DARK_CSS, "暗色玻璃底变量定义被掏空（引用仍在也不算）"
    # 数字渐变文字 + 等宽数字
    assert "background-clip: text" in _DARK_CSS or "background-clip:text" in _DARK_CSS
    assert "tabular-nums" in _DARK_CSS


def test_light_saas_layer_present():
    """亮色精致 SaaS 层：分层柔和阴影 + 大圆角。"""
    assert "v10" in _LIGHT_CSS, "亮色主题缺 v10 增强层标记"
    assert "--ss-saas-shadow:0 1px 2px" in _LIGHT_CSS, "亮色分层阴影定义被掏空（引用仍在也不算）"
    assert "border-radius:16px" in _LIGHT_CSS or "border-radius: 16px" in _LIGHT_CSS
    assert "tabular-nums" in _LIGHT_CSS


def test_micro_motion_shared():
    """克制微动效共用件：淡入 keyframes + reduced-motion 降级 + ::selection。"""
    for name, css in (("dark", _DARK_CSS), ("light", _LIGHT_CSS)):
        assert "@keyframes ss-fade-in" in css, f"{name} 缺淡入 keyframes"
        assert "prefers-reduced-motion" in css, f"{name} 缺 reduced-motion 降级"
        assert "::selection" in css, f"{name} 缺选区配色"


def test_up_down_semantics_unchanged():
    """A股红涨绿跌语义不可反转：涨红 #ff4d4f / 跌绿 #00d486 必须在两主题原样存在。"""
    for name, css in (("dark", _DARK_CSS), ("light", _LIGHT_CSS)):
        assert "#ff4d4f" in css, f"{name} 缺涨红语义色"
        assert "#00d486" in css, f"{name} 缺跌绿语义色"


def test_kit_tokens_v10():
    """ui_kit 令牌层：v10 微动效与 hero/stat 质感。"""
    assert "@keyframes ss-fade-in" in _TOKEN_CSS
    assert "prefers-reduced-motion" in _TOKEN_CSS
    assert "::selection" in _TOKEN_CSS
