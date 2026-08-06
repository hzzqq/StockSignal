"""
tests/test_widgets_base.py
=========================
锁定 modules/_widgets_base.py 的纯函数（项目内零测试覆盖，51 行）。

该模块跨页面共享，被「星辰 AI」多处 logo 渲染与三大指数卡片依赖：
  - STAR_AI_LOGO：内联 SVG logo；size 非数值/非正数安全降级为 20（R2 修复点，须锁）
  - _INDEX_INFOS：指数卡片数据源完整性（code/label 必填，A股三大指数恒在）
  - render_empty_state：T12 统一空态基建，避免数据缺失白屏（须锁输出结构）
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


def test_render_empty_state_basic():
    html = wb.render_empty_state("暂无数据")
    assert "暂无数据" in html
    # 默认图标 + 居中容器
    assert "📭" in html
    assert "text-align:center" in html
    # 走 CSS 变量，暗/亮主题自适应
    assert "var(--txt2)" in html and "var(--txt)" in html


def test_render_empty_state_with_hint():
    html = wb.render_empty_state("加载失败", icon="⚠️", hint="请稍后重试")
    assert "加载失败" in html
    assert "⚠️" in html
    assert "请稍后重试" in html


def test_render_empty_state_no_hint_omits_hint_block():
    html = wb.render_empty_state("空")
    # 无 hint 时不应出现 hint 段落（hint_html 为空）
    assert "var(--txt2)" in html  # hint 容器本是 txt2，但无单独补充行
    # 关键：hint 文本不出现（未传入）
    assert "请稍后重试" not in html


def test_render_empty_state_escapes_message_and_hint():
    """R73 回归：message/hint 为数据派生文本时必须转义，防止结构注入。"""
    evil = '<img src=x onerror=alert(1)>'
    html = wb.render_empty_state(evil, hint=evil)
    assert evil not in html                       # 原始标签不得出现
    assert "&lt;img src=x onerror=alert(1)&gt;" in html  # 已被转义
    # None/非字符串安全降级，绝不抛异常
    assert wb.render_empty_state(None).startswith("<div")
    assert wb.render_empty_state("x", hint=None).startswith("<div")
