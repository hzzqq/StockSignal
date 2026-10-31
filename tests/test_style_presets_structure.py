# -*- coding: utf-8 -*-
"""tests/test_style_presets_structure.py — 七风格「换风格不换布局」结构守卫（G3）
+ A11y 对比度报告模式（ui-ds 设计系统 Phase2 §3.1 / Phase3 §2.2）。

G3 布局禁覆盖（Phase1 §3.2 结构不变量）：
  1. STYLE_PRESETS extra 中出现 ``grid-template`` 即 fail——布局结构只允许
     存在于 ui_kit 组件层（.xc-bento 等），风格层只许换色相/材质。
     现存量：七风格 extra 均为 0（P0 落码前实测）。
  2. extra 中 ``display:<value>`` 必须命中该风格白名单——白名单即 P0 时点
     存量（装饰性 ::before/::after 的 display:block / display:none /
     徽记的 inline-block / ink 印章的 flex），新增结构性 display（grid/flex
     作用于主容器等）须人审后在此登记，防止风格层偷偷改布局。

A11y 对比度报告模式（不 hard fail）：
  Phase3 §2.2 裁定——cyber txt2 #5c7a9e vs card2 #0c111d 现值大概率 <4.5:1，
  若 P0 就挂 hard 会把守卫染红打乱分批纪律。故本批只输出七风格五对色值
  的 WCAG 对比度报告（pytest -s 可见），待视觉阶段修值后再升级为查表断言。
  报告仍带最小断言：vars 必须可解析出报告所需变量（防格式漂移后报告空转）。
"""
from __future__ import annotations

import re

from modules.ui_theme import STYLE_PRESETS, SF_ACC1, SF_BG, SF_CARD, SF_TXT, SF_TXT2, UP, DOWN

# ── G3 白名单：display 声明值（按风格登记，= P0 时点存量）──────────────
_DISPLAY_WHITELIST: dict[str, set[str]] = {
    "classic": set(),  # classic 契约 = 零注入（test_ui_theme_styles.test_classic_default_noop）
    "terminal": {"display:block", "display:none"},
    "swiss": {"display:block", "display:inline-block", "display:none"},
    "aurora": {"display:block"},
    "ink": {"display:flex", "display:inline-block", "display:none"},
    "cyber": {"display:block", "display:none"},
    "finpro": {"display:none"},
}

_DISPLAY_RE = re.compile(r"display:\s*[\w-]+")
_GRID_RE = re.compile(r"grid-template[a-z-]*\s*:")


def test_extra_never_touches_grid_layout():
    """G3-1：任何风格的 extra 不得出现 grid-template（布局结构禁覆盖）。"""
    offenders = []
    for k, p in STYLE_PRESETS.items():
        extra = p.get("extra", "")
        for m in _GRID_RE.finditer(extra):
            offenders.append(f"{k}: {m.group(0)!r}")
    assert not offenders, (
        "风格 extra 出现 grid-template（布局结构只属于 ui_kit 组件层，七风格只换色相材质）:\n  "
        + "\n  ".join(offenders)
    )


def test_extra_display_values_within_whitelist():
    """G3-2：extra 的 display 声明值必须命中该风格白名单（防新增结构性 display）。

    白名单 = P0 时点存量（装饰条 display:block / 装饰隐藏 display:none /
    swiss 红方块 inline-block / ink 印章 flex）。新增值 → 先人审是否真的
    不改布局，再登记白名单；禁止直接放宽正则。
    """
    offenders = []
    for k, p in STYLE_PRESETS.items():
        allow = _DISPLAY_WHITELIST[k]
        extra = p.get("extra", "")
        for m in _DISPLAY_RE.finditer(extra):
            val = re.sub(r"\s+", "", m.group(0))
            if val not in allow:
                offenders.append(f"{k}: {val!r}（白名单: {sorted(allow)}）")
    assert not offenders, (
        "风格 extra 出现白名单外的 display 值（疑似布局结构覆盖，人审后登记）:\n  "
        + "\n  ".join(offenders)
    )


def test_whitelist_covers_all_registered_styles():
    """G3-3：白名单必须覆盖全部已注册风格（新风格注册时强制表态）。"""
    missing = set(STYLE_PRESETS) - set(_DISPLAY_WHITELIST)
    assert not missing, f"新风格未登记 display 白名单: {sorted(missing)}"
    extra_keys = set(_DISPLAY_WHITELIST) - set(STYLE_PRESETS)
    assert not extra_keys, f"白名单含已注销风格（清理）: {sorted(extra_keys)}"


# ── A11y 对比度报告模式（Phase3 §2.2：先报告，修值后再 hard fail）────────

def _lum(hex_color: str) -> float:
    """WCAG 相对亮度（sRGB 线性化）。"""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _parse_vars(vars_str: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in vars_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_a11y_contrast_report_mode():
    """七风格五对色值 WCAG 对比度报告（报告模式，不 hard fail）。

    升级为查表断言的前置：视觉阶段按报告修值（cyber txt2 优先复测），
    然后把本测试尾部改为逐对 ≥ 阈值断言（正文 4.5:1 / 大号数值 3:1）。
    """
    # classic 无 vars（零注入契约），基线取 ui_theme 单一来源常量
    baselines = {
        "classic": {"card": SF_CARD, "card2": SF_CARD, "txt": SF_TXT,
                    "txt2": SF_TXT2, "acc1": SF_ACC1, "up": UP, "down": DOWN},
    }
    lines = [f"{'style':10s} {'txt/card':>9s} {'txt2/card2':>10s} {'txt2/card':>9s} "
             f"{'up/card':>8s} {'down/card':>9s} {'acc1/card':>9s}"]
    problems = []
    for k, p in STYLE_PRESETS.items():
        base = baselines.get(k)
        if base is None:
            v = _parse_vars(p.get("vars", ""))
            # finpro 不覆盖语义色（守卫钉死）→ 回落全局 :root 值（ui_kit _TOKEN_CSS）
            required = ("--card", "--card2", "--txt", "--txt2", "--acc1")
            miss = [r for r in required if r not in v]
            assert not miss, f"{k} vars 缺报告所需变量 {miss}（格式漂移？报告将空转）"
            base = {
                "card": v["--card"], "card2": v["--card2"], "txt": v["--txt"],
                "txt2": v["--txt2"], "acc1": v["--acc1"],
                "up": v.get("--ss-up", UP), "down": v.get("--ss-down", DOWN),
            }
        row = (
            _contrast(base["txt"], base["card"]),
            _contrast(base["txt2"], base["card2"]),
            _contrast(base["txt2"], base["card"]),
            _contrast(base["up"], base["card"]),
            _contrast(base["down"], base["card"]),
            _contrast(base["acc1"], base["card"]),
        )
        # 报告模式：只标记疑似不达标（正文 4.5 / 语义大数值 3.0），不断言
        checks = [("txt/card", row[0], 4.5), ("txt2/card2", row[1], 4.5),
                  ("up/card", row[3], 3.0), ("down/card", row[4], 3.0)]
        for name, ratio, need in checks:
            if ratio < need:
                problems.append(f"{k} {name}={ratio:.2f} < {need}")
        lines.append(f"{k:10s} " + " ".join(f"{r:9.2f}" for r in row))
    print("\n[a11y 对比度报告 · 报告模式] WCAG contrast ratio")
    print("\n".join(lines))
    if problems:
        print("[待修值] 以下对子未达阈值（视觉阶段修值后升级 hard fail）:\n  "
              + "\n  ".join(problems))
    # 报告模式唯一硬断言：classic 基线（单一来源常量）必须可达标——
    # 这对值此前已被多个守卫侧相关联，若跌破说明基线被人改动。
    assert _contrast(SF_TXT, SF_CARD) >= 4.5, "classic 基线 txt/card 对比度跌破 4.5（基线被改？）"
