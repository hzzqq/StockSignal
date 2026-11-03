# -*- coding: utf-8 -*-
"""design_system.md 第5章D阶段：圆角/字体/对比度收口守卫（hard fail）。

锁定 C 阶段新增的语义别名令牌存在且绑定现有 --ss-*/--acc*（或 colors.* 既有值），
断言数字等宽已落到 KPI 组件、圆角令牌派生正确。对比度 WCAG 下限由
test_a11y_contrast 负责，本文件只锁「别名层」不漂移。

诚实范围说明：圆角「全量归一（10/8/12/14/3/2px 散点共 200+ 行跨 15 文件）」
属高风险动作（批量改 CSS 易引发暗/亮主题视觉回潮），本阶段只建别名令牌 +
守卫，为未来专项归一铺路；不作为本 commit 的改动范围。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_KNOWN_HEX = {
    "ff4d4f", "00d486", "ffa502", "f59e0b", "ef4444", "3b82f6", "16a34a",
}


def _kit():
    import modules.ui_kit as kit
    return kit


def test_semantic_aliases_present():
    """C 阶段新增别名令牌必须全部存在（供未来 page 迁移复用，零影响现有消费者）。"""
    css = _kit()._KIT_CSS
    required = (
        "--brand-1", "--brand-2",
        "--c-up", "--c-down", "--c-hold", "--c-warn", "--c-danger", "--c-info", "--c-ok",
        "--radius-card", "--radius-btn", "--radius-input", "--radius-pill",
        "--font-num", "--font-cjk",
    )
    for tok in required:
        assert f"{tok}:" in css, f"缺失语义别名令牌：{tok}"


def test_aliases_bind_to_existing_tokens():
    """别名不得臆造独立色相：值须绑定 --ss-*/--acc* 或等价 colors.* 既有 hex。"""
    css = _kit()._KIT_CSS
    for m in re.finditer(r"(--(?:brand|c)-[a-z]+):([^;]+);", css):
        name, val = m.group(1), m.group(2).strip()
        is_bound = val.startswith("var(--ss-") or val.startswith("var(--acc")
        is_known_hex = val.lstrip("#").lower() in _KNOWN_HEX
        assert is_bound or is_known_hex, \
            f"{name} 别名值未绑定现有令牌或既有色值（禁止臆造独立色相）：{val}"


def test_kpi_components_use_monospace():
    """数字等宽量化：KPI/统计卡数值必须挂 --ss-font-num（等宽数位对齐，防视觉错位）。"""
    css = _kit()._KIT_CSS
    assert ".ss-stat .value{" in css, "缺少 .ss-stat .value 规则"
    assert ".xc-card .value{" in css, "缺少 .xc-card .value 规则"
    assert "font-family:var(--ss-font-num)" in css, "ss-stat/xc-card 数值未挂等宽字体"
    assert "font-family: var(--ss-font-num) !important" in css, "code/pre 等宽兜底缺失"


def test_radius_aliases_derive_from_tokens():
    """圆角令牌存在且由 --ss-radius* 派生（统一口径，防散点回归）。"""
    css = _kit()._KIT_CSS
    assert "--radius-card:var(--ss-radius-card,16px)" in css, "卡片圆角别名未派生自 --ss-radius-card"
    assert "--radius-pill:var(--ss-radius-pill,999px)" in css, "胶囊圆角别名未派生自 --ss-radius-pill"


def test_alias_semantics_match_locked_tokens():
    """别名语义与锁定 --ss-* 同值（确保涨跌语义/对比度不因别名漂移）。"""
    css = _kit()._KIT_CSS
    assert "--c-up:var(--ss-up,#ff4d4f)" in css, "--c-up 未绑定 --ss-up/#ff4d4f（红涨）"
    assert "--c-down:var(--ss-down,#00d486)" in css, "--c-down 未绑定 --ss-down/#00d486（绿跌）"
