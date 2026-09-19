# -*- coding: utf-8 -*-
"""tests/test_ui_design_system.py — 全站设计系统「防回退」守卫（AST 源码级）。

锁定三条设计系统不变量，防止后续改动静默回退：
1. ``st.metric(delta=...)`` 必须显式传 ``delta_color``：Streamlit 默认「涨绿跌红」，
   与 A 股「红涨绿跌」相反；漏传即回退成错误语义色（全站 12 处曾受影响）。
2. ``page_widgets._section_title_html`` 竖条必须用设计令牌 ``var(--acc1)``，
   不得硬编码 hex（去彩虹：曾各页自取 accent 形成 9 处「彩虹标题」）。
3. KPI 卡必须走 canonical ``.xc-card``：``_xc_card_html`` / ``_stat_tile_html`` 输出
   同为 ``.xc-card``（消除 ``.ss-stat`` 重复视觉）。
4. 全局 ``[data-testid=stMetric]`` 皮肤必须与 ``.xc-card`` 共享同一组卡 token
   （圆角/内边距/边框混色/阴影），防两处定义各自漂移出两种「同一个 KPI 卡」外观。
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 扫描范围：所有业务源码（含根目录 app.py 等），排除 tests / 缓存 / 虚拟环境
_SKIP = ("__pycache__", "/tests/", "\\tests\\", ".venv", "site-packages", "/node_modules/")


def _iter_sources():
    for p in ROOT.rglob("*.py"):
        s = str(p)
        if any(x in s for x in _SKIP):
            continue
        yield p


def _st_metric_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr == "metric"
                    and isinstance(f.value, ast.Name) and f.value.id == "st"):
                yield node


def test_st_metric_with_delta_must_set_delta_color():
    """带 delta 的 st.metric 必须显式传 delta_color（否则回退「涨绿跌红」，与 A 股相反）。"""
    offenders = []
    for p in _iter_sources():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for call in _st_metric_calls(tree):
            has_delta = any(k.arg == "delta" for k in call.keywords) or len(call.args) >= 3
            has_color = any(k.arg == "delta_color" for k in call.keywords)
            if has_delta and not has_color:
                offenders.append(f"{p.relative_to(ROOT)}:{call.lineno}")
    assert not offenders, (
        "以下 st.metric(delta=...) 未显式设置 delta_color（A 股应为 inverse / 文字信号用 off）：\n  "
        + "\n  ".join(offenders)
    )


def test_section_title_bar_uses_design_token_not_hex():
    """section 竖条统一走设计令牌 var(--acc1)，不得硬编码 hex（去彩虹不变量）。"""
    from modules.page_widgets import _section_title_html
    out = _section_title_html("测试标题", accent="#ff0000")  # 即便传入散色，也必须被忽略
    assert "var(--acc1)" in out, "section 竖条应使用设计令牌 var(--acc1)"
    assert not re.search(r"background:#[0-9a-fA-F]{3,8}", out), "section 竖条不得硬编码 hex 背景"


def test_kpi_cards_converge_to_canonical_xc_card():
    """KPI 卡收敛到 canonical .xc-card（_xc_card_html 与旧 _stat_tile_html 同视觉）。"""
    from modules import ui_kit as kit
    assert 'class="xc-card"' in kit._xc_card_html(label="a", value="1")
    assert 'class="xc-card"' in kit._stat_tile_html("涨家数", "1200", "+3.2%", "up")
    # sf_metric 亦收敛到 canonical（ui_theme 侧）
    import inspect
    from modules import ui_theme
    src = inspect.getsource(ui_theme.sf_metric)
    assert "_xc_card_html" in src, "sf_metric 应委托 ui_kit._xc_card_html（单一 KPI 卡视觉）"


def _decl(rule: str) -> dict:
    """把一段 CSS 声明解析为 {prop: value}，值去掉 !important 便于跨处比对。"""
    out = {}
    for part in rule.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip().replace("!important", "").strip()
    return out


def test_metric_skin_matches_canonical_xc_card(monkeypatch):
    """全局 [data-testid=stMetric] 皮肤必须与 canonical .xc-card 共享同一组卡 token。

    防漂移：KPI 卡的视觉曾分散在两处——``ui_kit._KIT_CSS`` 的 ``.xc-card`` 与
    ``ui_theme.dashboard_sf_css()`` 的 ``[data-testid=stMetric]``。任一处单独改动，
    同一个 KPI 卡就会出现两种外观（圆角/内边距/边框各说各话）。本守卫把两处的
    圆角 / 内边距 / 边框混色 / 阴影钉死为一致——单一视觉源。
    """
    import modules.ui_kit as kit
    import modules.ui_theme as ui_theme

    monkeypatch.setattr(ui_theme, "_theme_is_dark", lambda: False)
    ui_theme._DASHBOARD_SF_CSS_CACHE.clear()
    css = ui_theme.dashboard_sf_css()

    m = re.search(r'\[data-testid="stMetric"\]\{([^}]*)\}', css)
    assert m, "全局 CSS 缺少 [data-testid=stMetric] 卡容器规则"
    metric = _decl(m.group(1))

    m2 = re.search(r"\.xc-card\{([^}]*)\}", kit._KIT_CSS)
    assert m2, "ui_kit._KIT_CSS 缺少 .xc-card 基础规则"
    xc = _decl(m2.group(1))

    for key in ("border-radius", "padding"):
        assert metric.get(key) == xc.get(key), (
            f"stMetric 与 .xc-card 的 {key} 不一致：{metric.get(key)!r} vs {xc.get(key)!r}"
        )
    assert xc["border-radius"] == "var(--ss-radius-card)"  # canonical 卡圆角统一走 token（T-145 A3）
    for name, d in (("stMetric", metric), ("xc-card", xc)):
        b = d.get("border", "")
        assert ("color-mix(" in b and "--ss-accent" in b and "22%" in b), (
            f"{name} 边框须为主题强调色 22% 混色且走 --ss-accent token（禁裸 --border）：{b!r}"
        )
    assert metric.get("box-shadow") == xc.get("box-shadow"), "两处卡阴影须一致"
    assert "var(--ss-shadow-card)" in metric.get("box-shadow", ""), "卡阴影应统一走 --ss-shadow-card token"

