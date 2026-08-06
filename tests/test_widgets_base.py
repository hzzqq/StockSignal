"""
tests/test_widgets_base.py
=========================
锁定 modules/_widgets_base.py 的纯函数（项目内零测试覆盖，51 行）。

该模块跨页面共享，被「星辰 AI」多处 logo 渲染与三大指数卡片依赖：
  - STAR_AI_LOGO：内联 SVG logo；size 非数值/非正数安全降级为 20（R2 修复点，须锁）
  - _INDEX_INFOS：指数卡片数据源完整性（code/label 必填，A股三大指数恒在）
"""

from __future__ import annotations

import modules._widgets_base as wb


def test_star_ai_logo_default_size():
    svg = wb.STAR_AI_LOGO()
    assert svg.startswith("<svg")
    assert 'width="20"' in svg
    assert 'height="20"' in svg
    assert 'aria-label="星辰 AI"' in svg
    assert "667eea" in svg and "764ba2" in svg  # 紫蓝主色 + 星芒金


def test_star_ai_logo_custom_size():
    svg = wb.STAR_AI_LOGO(32)
    assert 'width="32"' in svg
    assert 'height="32"' in svg


def test_star_ai_logo_size_safety_degradation():
    # None / 非数值 / 非正数 -> 降级 20，绝不崩溃
    for bad in (None, "abc", -5, 0, -100):
        svg = wb.STAR_AI_LOGO(bad)
        assert 'width="20"' in svg, f"size={bad!r} 未降级到 20"
        assert 'height="20"' in svg


def test_index_infos_integrity():
    infos = wb._INDEX_INFOS
    assert isinstance(infos, list) and len(infos) >= 3
    # A股三大指数必在
    codes = {i["code"] for i in infos}
    assert "000001" in codes and "399001" in codes and "399006" in codes
    # 每条必须有 name / code / label
    for it in infos:
        assert "name" in it and "code" in it and "label" in it
