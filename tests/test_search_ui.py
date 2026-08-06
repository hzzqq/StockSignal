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
    """股票名含 HTML 特殊字符时：下拉改用 st.radio 文本标签渲染，Streamlit 将其作为
    字面文本显示（结构性 XSS 防护，危险串不会被执行），同时正确回传 active code。

    注：旧实现用 components.html 注入带 JS 的 iframe，曾导致「点击无响应」且需手动转义；
    现改为 st.radio（见 modules/search_ui.py _render_match_dropdown 注释），转义由 Streamlit
    在渲染标签时保证，无需手动 &lt; &gt; 替换。
    """
    captured = {}

    def fake_radio(label, options=None, index=0, key=None, **kwargs):
        captured["options"] = list(options)
        captured["key"] = key
        # 模拟用户选中默认（active）项
        return options[index] if options else None

    monkeypatch.setattr(search_ui.st, "radio", fake_radio)

    results = [
        ("600519", '<script>alert(1)</script>', "SH"),
        ("000858", "五 & 粮\"液", "SZ"),
    ]
    picked = search_ui._render_match_dropdown("k", "茅台", results, "600519", dark=False)

    labels = " ".join(captured["options"])
    # 危险串作为字面量出现在某条 label（证明未被丢弃，也未被当 HTML 执行）
    assert "<script>alert(1)</script>" in labels
    assert "五 & 粮" in labels
    # 标签含代码与标签（科创板/沪A 等），证明下拉结构完整
    assert "600519" in labels
    assert "000858" in labels
    # 函数正确回传 active code（点击即选中逻辑不变）
    assert picked == "600519"
