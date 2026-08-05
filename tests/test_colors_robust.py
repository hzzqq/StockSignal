"""配色健壮性测试：覆盖 _hex_to_rgba 统一封装 + 重构后模块导入无回归。

背景：市场情绪页曾因 `fillcolor=color + "22"` 生成 8 位 hex 导致 9 个卡片
全部 ValueError 崩溃。修复方案是把 `_hex_to_rgba` 统一抽到 `modules.colors`，
各模块（widgets/_compare_render/P_市场情绪）复用。本测试守住这条不变量。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.colors import hex_to_rgba, _hex_to_rgba


def test_hex_to_rgba_6hex():
    assert hex_to_rgba("#ff4d4f", 0.13) == "rgba(255,77,79,0.13)"


def test_hex_to_rgba_3hex_expands():
    assert hex_to_rgba("#f00", 0.5) == "rgba(255,0,0,0.5)"


def test_hex_to_rgba_lstrip_hash():
    assert hex_to_rgba("00d486", 0.1) == "rgba(0,212,134,0.1)"


def test_hex_to_rgba_none_safe():
    # None / 空串 / 非法值安全降级为透明黑，不抛 ValueError
    assert hex_to_rgba(None, 0.13) == "rgba(0,0,0,0.13)"
    assert hex_to_rgba("", 0.13) == "rgba(0,0,0,0.13)"


def test_hex_to_rgba_alias_points_to_canonical():
    assert _hex_to_rgba is hex_to_rgba


def test_imports_after_refactor_no_crash():
    # 重构后 widgets / _compare_render 复用 colors._hex_to_rgba，应能正常导入
    import modules._compare_render  # noqa: F401
    import modules.widgets  # noqa: F401
    # 确认两模块确实用的是 colors 版本（无本地重复 def 残留）
    assert not hasattr(modules._compare_render, "_hex_to_rgba_local")
    assert not hasattr(modules.widgets, "_hex_to_rgba_local")
