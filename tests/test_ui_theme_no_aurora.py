"""守卫生：ui_theme.py 的 _DARK_CSS / _LIGHT_CSS 绝不含极光 hex。

背景：T-357 + 1372683（2026-10-28）将极光色 #667eea/#764ba2 统一为品牌靛紫 #4f46e5/#7c3aed。
本测试钉死"永不回退"——任何人在 ui_theme.py 里重新引入这两个 hex，这里立即红。
"""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
UI_THEME = ROOT / "modules" / "ui_theme.py"

AURORA_HEXES = ("#667eea", "#764ba2")
INDIGO_HEXES = ("#4f46e5", "#7c3aed")


def _read_theme():
    return UI_THEME.read_text(encoding="utf-8", errors="replace")


def test_ui_theme_no_aurora_hex():
    """ui_theme.py 整体不含任何极光 hex（大小写不敏感）。"""
    src = _read_theme().lower()
    for hex_ in AURORA_HEXES:
        assert hex_ not in src, f"❌ 发现极光残留 {hex_} in ui_theme.py"


def test_ui_theme_has_indigo_brand():
    """ui_theme.py 内含品牌靛紫（确认没被误删）。"""
    src = _read_theme().lower()
    for hex_ in INDIGO_HEXES:
        assert hex_ in src, f"❌ 品牌靛紫 {hex_} 不见了（可能被误删）"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
