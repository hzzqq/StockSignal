"""tests/test_ui_bento.py — Bento 非对称网格助手单测（不依赖 Streamlit 运行时渲染）。

覆盖：_bento_html 结构 / 非对称模板 / 空单元格跳过 / xc_bento_grid 与 xc_bento_kpi 渲染
契约 / CSS 含 .xc-bento 类 / 空数据不产出。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from modules import ui_kit as kit


def test_bento_html_structure_and_template():
    out = kit._bento_html(["AAA", "BBB"], "1.2fr 1fr", 18)
    assert 'class="xc-bento"' in out
    assert "grid-template-columns:1.2fr 1fr" in out
    assert "gap:18px" in out
    assert out.count('class="xc-bento-cell"') == 2
    assert "AAA" in out and "BBB" in out


def test_bento_html_skips_empty_cells():
    out = kit._bento_html(["AAA", "", None, "CCC"], "1fr 1fr", 16)
    assert out.count('class="xc-bento-cell"') == 2
    assert "AAA" in out and "CCC" in out


def test_xc_bento_grid_renders(monkeypatch):
    captured = []
    monkeypatch.setattr(st, "markdown", lambda html, *a, **k: captured.append(html))
    kit.xc_bento_grid(["X", "Y"], template="1fr 1fr")
    out = captured[-1]
    assert 'class="xc-bento"' in out
    assert out.count('class="xc-bento-cell"') == 2
    assert "X" in out and "Y" in out


def test_xc_bento_kpi_renders_cells(monkeypatch):
    captured = []
    monkeypatch.setattr(st, "markdown", lambda html, *a, **k: captured.append(html))
    kit.xc_bento_kpi(
        [{"label": "A", "value": "1"}, {"label": "B", "value": "2"}],
        template="1.3fr 1fr",
    )
    out = captured[-1]
    # 容器 + 非对称模板
    assert 'class="xc-bento"' in out
    assert "grid-template-columns:1.3fr 1fr" in out
    # 每张卡 = 一个 bento-cell 内嵌一个 xc-card
    assert out.count('class="xc-bento-cell"') == 2
    assert out.count('class="xc-card"') == 2
    # 语义色 / 字段透传
    assert "A" in out and "1" in out and "B" in out and "2" in out


def test_xc_bento_kpi_empty_no_output(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "markdown", lambda html, *a, **k: calls.append(html))
    kit.xc_bento_kpi([])
    kit.xc_bento_kpi(None)
    # 空数据不应渲染任何 bento 网格（允许 CSS 注入，但不应有 .xc-bento 容器）
    assert all('class="xc-bento"' not in c for c in calls)


def test_css_exposes_bento_classes(monkeypatch):
    captured = []
    monkeypatch.setattr(st, "markdown", lambda html, *a, **k: captured.append(html))
    kit.inject_kit_css()
    out = captured[-1]
    assert ".xc-bento{" in out
    assert ".xc-bento-cell{" in out
    # 视觉与全站 xc-card 一致（令牌 + 圆角 + 悬浮抬升）
    assert "var(--ss-radius-card)" in out
    assert "var(--ss-shadow-lift)" in out


def test_public_api_has_bento():
    for name in ("xc_bento_grid", "xc_bento_kpi", "_bento_html"):
        assert hasattr(kit, name), f"missing public api: {name}"
