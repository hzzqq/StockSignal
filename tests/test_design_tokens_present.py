# -*- coding: utf-8 -*-
"""design_system.md 第5章D阶段：圆角/字体/对比度收口守卫（hard fail）。

锁定 C 阶段新增的语义别名令牌存在且绑定现有 --ss-*/--acc*（或 colors.* 既有值），
断言数字等宽已落到 KPI 组件、圆角令牌派生正确。对比度 WCAG 下限由
test_a11y_contrast 负责，本文件只锁「别名层」不漂移。

圆角全量归一（Phase 6-2，2026-11-03）：299 处裸单值 px 已吸附到 --ss-radius* 五档
（xs=3 / sm=8 / --ss-radius=12 / lg=14 / card=16 / pill=999，就近映射漂移<=3px），
本文件同时锁死「裸单值 px 不回潮」；多值角形态（Npx Mpx ...）、0（直角）、50%（圆）
语义特殊，明确豁免。
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


_RADIUS_SCALE = (
    "--ss-radius-xs:3px", "--ss-radius-sm:8px", "--ss-radius:12px",
    "--ss-radius-lg:14px", "--ss-radius-card:16px", "--ss-radius-pill:999px",
)


def test_radius_scale_tokens_complete():
    """圆角五档令牌齐备（Phase 6-2 归一的吸附目标，缺一档则归一映射落空）。"""
    css = _kit()._TOKEN_CSS
    for tok in _RADIUS_SCALE:
        assert tok in css, f"缺失圆角档位令牌：{tok.split(':')[0]}"


def test_no_bare_border_radius_px():
    """圆角归一守卫：modules/pages/backend 禁止裸单值 px（须走 var(--ss-radius*)）。

    豁免：多值角形态（如 border-radius:14px 4px 14px 14px）、0（直角）、50%（圆）、
    var(...) 引用、token 定义行本身（--ss-radius:12px 等，无 border-radius: 前缀）。
    """
    bare = re.compile(r"border-radius:\s*\d+px(?!\s*[\d.])")
    roots = [ROOT / "modules", ROOT / "pages", ROOT / "backend"]
    offenders = []
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            if "__pycache__" in str(f):
                continue
            for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if ln.strip().startswith("#"):
                    continue
                if bare.search(ln):
                    offenders.append(f"{f.relative_to(ROOT)}:{i}")
    assert offenders == [], (
        f"border-radius 裸单值 px 回潮（应改 var(--ss-radius-xs/sm//lg/card/pill)）：{offenders}"
    )
