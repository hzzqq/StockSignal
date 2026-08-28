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
                 "stat_row", "chart_card", "table_wrap", "xc_error_box",
                 "xc_empty_box", "xc_section_header", "xc_subheader", "xc_info_banner"):
        assert hasattr(kit, name), f"missing public api: {name}"


def test_xc_error_box_renders_friendly_and_no_leak(monkeypatch):
    import streamlit as st
    captured = []
    monkeypatch.setattr(st, "markdown", lambda html, *a, **k: captured.append(html))
    kit.xc_error_box("获取板块数据失败", hint="请稍后重试")
    out = captured[-1]  # 最后一个是错误卡 HTML（前一个是注入的 CSS）
    assert "获取板块数据失败" in out
    assert "请稍后重试" in out
    assert "xc-error-box" in out
    assert "xc-err-hint" in out


def test_xc_empty_box_renders(monkeypatch):
    import streamlit as st
    captured = []
    monkeypatch.setattr(st, "markdown", lambda html, *a, **k: captured.append(html))
    kit.xc_empty_box("暂无自选股数据", hint="去添加几只股票吧")
    out = captured[-1]
    assert "暂无自选股数据" in out
    assert "去添加几只股票吧" in out
    assert "xc-empty-box" in out


def test_xc_handle_error_logs_and_does_not_leak(monkeypatch):
    import streamlit as st
    import logging
    captured = []
    monkeypatch.setattr(st, "markdown", lambda html, *a, **k: captured.append(html))
    logs = []
    monkeypatch.setattr(logging.Logger, "warning",
                       lambda self, msg, *a, **k: logs.append((msg % a) if a else msg))
    class _Boom(Exception):
        pass
    exc = _Boom("internal_detail_xyz")
    kit.xc_handle_error("北向资金加载失败", exc, hint="请稍后重试")
    out = captured[-1]
    # 异常细节必须进日志，绝不进用户可见的 HTML
    assert any("internal_detail_xyz" in str(m) for m in logs)
    assert "北向资金加载失败" in out
    assert "internal_detail_xyz" not in out
    assert "xc-error-box" in out
