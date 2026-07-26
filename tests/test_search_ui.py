"""
tests/test_search_ui.py
=======================
校验 modules.search_ui 的纯逻辑与匹配结果下拉的安全渲染：
- _derive_tag：由代码前缀推导市场/板块标签（含科创板/北交所/沪深A/B股）；
- _guess_market：SH/SZ 推导；
- _render_match_dropdown：HTML 转义防御（股票名含 < & " 不破坏下拉标记）。
"""
from __future__ import annotations

from modules import search_ui
from modules.search_ui import _derive_tag, _guess_market


def test_derive_tag_boards():
    assert _derive_tag("688981") == "科创板"
    assert _derive_tag("689009") == "科创板"   # CDR
    assert _derive_tag("600519") == "沪A"
    assert _derive_tag("000858") == "深A"
    assert _derive_tag("300750") == "创业板"
    assert _derive_tag("830799") == "北交所"
    assert _derive_tag("430047") == "北交所"
    assert _derive_tag("900901") == "沪B"
    assert _derive_tag("200011") == "深B"


def test_derive_tag_invalid():
    assert _derive_tag("") == "—"
    assert _derive_tag(None) == "—"      # type: ignore[arg-type]
    assert _derive_tag("abc") == "—"
    assert _derive_tag("60051x") == "—"


def test_guess_market():
    assert _guess_market("600519") == "SH"
    assert _guess_market("000858") == "SZ"
    assert _guess_market("300750") == "SZ"
    assert _guess_market("899999") == ""


def test_render_match_dropdown_escapes_html(monkeypatch):
    """恶意/异常股票名含 HTML 特殊字符时必须被转义，不能原样进入下拉标记。"""
    captured = {}

    def fake_html(html, height=None, key=None):
        captured["html"] = html
        captured["height"] = height
        captured["key"] = key
        return None

    monkeypatch.setattr(search_ui.components, "html", fake_html)

    results = [
        ("600519", '<script>alert(1)</script>', "SH"),
        ("000858", "五 & 粮\"液", "SZ"),
    ]
    search_ui._render_match_dropdown("k", "茅台", results, "600519", dark=False)

    out = captured["html"]
    # 原始危险串不得原样出现
    assert "<script>alert(1)</script>" not in out
    # 转义后的形式应出现
    assert "&lt;script&gt;" in out
    assert "&amp;" in out
    # 结构性标记仍在
    assert 'class="mk-wrap"' in out
    assert "匹配结果 (2 条)" in out
    # 高度受上限约束
    assert captured["height"] <= 460
