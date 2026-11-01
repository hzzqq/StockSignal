# -*- coding: utf-8 -*-
"""tests/test_plotly_skin_matches.py — P1-4a 图表皮肤守卫（hard fail）。

锁定 dashboard_sf_css 中 [data-testid=stPlotlyChart] 皮肤必须走共享令牌引用
（与 test_metric_skin_matches_canonical_xc_card 同手法：锁皮肤引用令牌而非字面量），
防止图表容器视觉与 canonical .xc-card 漂移出两种卡外观，或回退为硬编码 hex。

口径（phase3 §1.4 替代方案 a）：
- background  → var(--ss-surface)
- border      → var(--ss-card-border)（强调色 22% 混 --ss-line，与 .xc-card 同源）
- border-radius → var(--ss-radius-card)（与 .xc-card 同圆角档）
- box-shadow  → var(--ss-shadow-card)
- 亮色全局通道 _LIGHT_CSS 的同目标规则同样禁止硬编码 hex（防特异性压制皮肤）
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _sf_css(monkeypatch, dark: bool) -> str:
    import modules.ui_theme as ui_theme
    monkeypatch.setattr(ui_theme, "_theme_is_dark", lambda: dark)
    ui_theme._DASHBOARD_SF_CSS_CACHE.clear()
    return ui_theme.dashboard_sf_css()


def _plotly_decl(css: str) -> dict:
    m = re.search(r'\[data-testid="stPlotlyChart"\]\{([^}]*)\}', css)
    assert m, "dashboard_sf_css 缺少 [data-testid=stPlotlyChart] 皮肤规则"
    out = {}
    for d in m.group(1).split(";"):
        if ":" in d:
            k, v = d.split(":", 1)
            out[k.strip()] = v.strip().replace("!important", "").strip()
    return out


@pytest.mark.parametrize("dark", [False, True])
def test_plotly_skin_reads_shared_tokens(monkeypatch, dark):
    """图表容器皮肤四属性必须引用共享令牌（禁硬编码 hex/rgba），两主题分支同检。"""
    decl = _plotly_decl(_sf_css(monkeypatch, dark))
    assert decl.get("background") == "var(--ss-surface)", (
        f"图表底须走 var(--ss-surface)（暗下不再裸透明底）：{decl.get('background')!r}")
    border = decl.get("border", "")
    assert "var(--ss-card-border)" in border, (
        f"图表边框须走 var(--ss-card-border)（与 .xc-card 同源强调混色）：{border!r}")
    assert decl.get("border-radius") == "var(--ss-radius-card)", (
        f"图表圆角须走 var(--ss-radius-card)：{decl.get('border-radius')!r}")
    assert "var(--ss-shadow-card)" in decl.get("box-shadow", ""), (
        f"图表阴影须走 var(--ss-shadow-card)：{decl.get('box-shadow')!r}")


def test_plotly_radius_matches_canonical_xc_card(monkeypatch):
    """图表卡圆角与 canonical .xc-card 同档（同一「卡」的视觉源）。"""
    import modules.ui_kit as kit
    decl = _plotly_decl(_sf_css(monkeypatch, dark=True))
    m = re.search(r"\.xc-card\{([^}]*)\}", kit._KIT_CSS)
    assert m, "ui_kit._KIT_CSS 缺少 .xc-card 基础规则"
    xc_radius = re.search(r"border-radius:([^;]+)", m.group(1)).group(1).strip()
    assert decl["border-radius"] == xc_radius, (
        f"stPlotlyChart 圆角 {decl['border-radius']!r} 与 .xc-card {xc_radius!r} 不一致")


def test_light_css_plotly_block_no_stray_hex():
    """_LIGHT_CSS 的 div[data-testid=stPlotlyChart] 规则禁止硬编码 hex/rgba 底色
    （特异性高于皮肤选择器，硬编码会压制 dark 同源令牌；须走带 fallback 的 var）。"""
    src = (_ROOT / "modules" / "ui_theme.py").read_text(encoding="utf-8")
    m = re.search(r'div\[data-testid="stPlotlyChart"\] \{([^}]*)\}', src)
    assert m, "_LIGHT_CSS 未找到 div[data-testid=stPlotlyChart] 规则（结构变更请同步本守卫）"
    blk = m.group(1)
    for line in blk.split("\\n"):
        if "background:" in line or "border-radius:" in line:
            assert "var(--ss-" in line, (
                f"_LIGHT_CSS 图表容器规则须引用 --ss-* 令牌（可带 fallback）：{line.strip()!r}")
