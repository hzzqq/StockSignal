# -*- coding: utf-8 -*-
"""tests/test_ui_design_system.py — 全站设计系统「防回退」守卫（AST 源码级）。

锁定三条设计系统不变量，防止后续改动静默回退：
1. ``st.metric(delta=...)`` 必须显式传 ``delta_color``：Streamlit 默认「涨绿跌红」，
   与 A 股「红涨绿跌」相反；漏传即回退成错误语义色（全站 12 处曾受影响）。
2. ``page_widgets._section_title_html`` 竖条必须用设计令牌 ``var(--acc1)``，
   不得硬编码 hex（去彩虹：曾各页自取 accent 形成 9 处「彩虹标题」）。
3. KPI 卡必须走 canonical ``.xc-card``：``_xc_card_html`` / ``_stat_tile_html`` 输出
   同为 ``.xc-card``（消除 ``.ss-stat`` 重复视觉）。
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
