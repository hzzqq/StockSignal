"""tests/test_ui_kit.py — ui_kit 纯函数构建器单测（不依赖 Streamlit 运行时）。

覆盖：HTML 转义（XSS 防护）、主题变量占位、各组件返回预期结构。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import ui_kit as kit


def test_hero_escapes_xss():
    out = kit._hero_html("<script>alert(1)</script>", icon="<b>x</b>", subtitle="<img src=x>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    # 默认 style='xc' → 输出 .xc-hero-* 类
    assert "xc-hero-title" in out
    assert "xc-hero-icon" in out
    # 显式 style='sf' → 走原 .ss-hero-* fallback（保证旧路径仍能渲）
    sf = kit._hero_html("行情看板", icon="📈", subtitle="XSS 测试", style="sf")
    assert "ss-hero-title" in sf
    assert "ss-hero-icon" in sf


def test_hero_style_param_branches():
    """2026-08-28 接入新城风格后，page_hero 默认走 xc（page_hero/_hero_html），
    显式 style='sf' 走 .ss-hero fallback 仍能渲染。"""
    # 默认：xc
    assert "xc-hero" in kit._hero_html("A")
    # 显式 sf
    assert "ss-hero" in kit._hero_html("A", style="sf")
    # 未知 style → 仍降级到 .ss-hero（保持旧行为兼容）
    assert "ss-hero" in kit._hero_html("A", style="bogus")


def test_hero_defaults():
    out = kit._hero_html("行情看板")
    assert "行情看板" in out
    assert "📊" in out  # 默认图标


def test_info_banner_kinds():
    for kind in ("info", "success", "warning", "danger"):
        out = kit._info_banner_html("提示", kind=kind)
        assert f"ss-info {kind}" in out
        assert "提示" in out
    # 非法 kind 回落 info
    assert "ss-info info" in kit._info_banner_html("x", kind="bogus")


def test_info_banner_escapes():
    out = kit._info_banner_html("<script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_stat_tile_directions():
    for d in ("up", "down", "flat"):
        out = kit._stat_tile_html("涨家数", "1200", "+3.2%", d)
        assert f"delta {d}" in out
        assert "1200" in out
    # 非法方向回落 flat（仅当 delta 非空时渲染 delta div）
    assert "delta flat" in kit._stat_tile_html("x", "1", "0.0%", "weird")


def test_stat_tile_escapes_and_accent():
    out = kit._stat_tile_html("<b>label</b>", "<i>v</i>", None, "flat", "#ff0000")
    assert "&lt;b&gt;label&lt;/b&gt;" in out
    assert "border-top:3px solid #ff0000" in out


def test_chart_card_and_table_wrap():
    c = kit._chart_card_html("K线", "<div>plot</div>")
    assert "ss-chart" in c and "K线" in c and "<div>plot</div>" in c
    t = kit._table_wrap_html("<table></table>")
    assert "ss-table-wrap" in t


def test_module_imports_and_has_public_api():
    for name in ("inject_kit_css", "page_hero", "info_banner", "stat_tile",
                 "stat_row", "chart_card", "table_wrap"):
        assert hasattr(kit, name), f"missing public api: {name}"
