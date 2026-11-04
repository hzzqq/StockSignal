# -*- coding: utf-8 -*-
"""tests/test_a11y_contrast.py — P2-2 无障碍对比度守卫（WCAG 2.1 AA，hard fail）。

锁定 modules/ui_theme.py 七风格令牌的对比度下限，防止后续新增/调整风格时
静默引入不达标组合。口径（与 WCAG 2.1 SC 1.4.3 对齐）：

- 正文与辅助文字（``--txt`` / ``--txt2``）对背景与卡片：≥ 4.5:1
- accent（``--acc1`` / ``--acc2``，用于强调文字/边框/链接）：≥ 3.0:1
- 登录 CTA 文字（``--ss-login-btn-text``，默认 #fff）对其按钮底色
  （默认 ``linear-gradient(90deg, var(--acc1), var(--acc2))`` 两端，
  以及 extra 中显式覆盖的渐变 stops / 纯色背景）：≥ 4.5:1
- ink 风格 extra 中 ``.stMetric label`` 硬编码色对 ink 卡片：≥ 4.5:1

数据源为 ui_theme.py 源码级解析（AST 提取 STYLE_PRESETS / _DARK_CSS，
正则提取 classic 双主题基座 root），不 import 运行时模块，避免样式副作用。

背景：P2-2 勘查发现 5 处不达标并已修正令牌值（微调亮度保风格气质）：
  classic 暗基座 acc1 #4f46e5→#5b53f0；aurora acc1 #8b7cff→#6c5ce7（渐变
  高亮 stop #2dd4ff→#0c74b3）；ink txt2 #7a7263→#756d5e（+ acc2
  #1e7f6b→#1e7762，守卫落地时新发现的第 6 处 CTA 端点不达标）；
  cyber txt2 #5c7a9e→#6d8db4；finpro acc1 #2f81f7→#2170ec。
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
THEME_SRC = (ROOT / "modules" / "ui_theme.py").read_text(encoding="utf-8")

# ════════ WCAG 2.1 相对亮度与对比度 ════════


def _lin(c: float) -> float:
    """sRGB 通道线性化：c≤0.03928 → c/12.92，否则 ((c+0.055)/1.055)^2.4。"""
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(hex6: str) -> float:
    """WCAG 相对亮度 L = 0.2126R + 0.7152G + 0.0722B。"""
    h = hex6.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(fg: str, bg: str) -> float:
    l1, l2 = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


# ════════ 令牌解析（源码级，零运行时副作用） ════════


def _parse_vars(s: str) -> dict:
    """提取 ``--name:#hex`` 令牌对（3/6 位均支持，统一扩为 6 位）。"""
    out = {}
    for name, hx in re.findall(r"(--[a-z0-9-]+):#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", s):
        h = hx.lstrip("#")
        out[name] = "".join(ch * 2 for ch in h) if len(h) == 3 else h.lower()
    return out


def _style_presets() -> dict:
    """AST 提取 STYLE_PRESETS 字面量 dict（ui_theme.py 无运行时依赖可安全求值）。"""
    for node in ast.walk(ast.parse(THEME_SRC)):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "STYLE_PRESETS" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("ui_theme.py 中未找到 STYLE_PRESETS 定义")


def _classic_bases() -> dict:
    """classic 风格无自带 vars，令牌继承 modules/ui_theme._THEME_ROOT_VARS 暗/亮两份基座 root。"""
    for node in ast.walk(ast.parse(THEME_SRC)):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_THEME_ROOT_VARS" for t in node.targets
        ):
            d = ast.literal_eval(node.value)
            bases = {}
            if "--bg:#0f0f23" in d.get("dark", ""):
                bases["dark"] = _parse_vars(d["dark"])
            if "--bg:#ffffff" in d.get("light", ""):
                bases["light"] = _parse_vars(d["light"])
            assert set(bases) == {"dark", "light"}, f"classic 基座解析异常：{list(bases)}"
            return bases
    raise AssertionError("ui_theme.py 中未找到 _THEME_ROOT_VARS 定义")


_PRESETS = _style_presets()
_BASES = _classic_bases()


def _login_text(extra: str) -> str:
    m = re.search(r"--ss-login-btn-text:#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", extra or "")
    if not m:
        return "ffffff"  # session.py .ss-login-btn 的 fallback：var(--ss-login-btn-text, #fff)
    h = m.group(1).lstrip("#")
    return "".join(ch * 2 for ch in h) if len(h) == 3 else h.lower()


def _login_overrides(extra: str):
    """提取 extra 中 .ss-login-btn 显式覆盖：渐变 stops 列表 + 纯色背景（若有）。"""
    stops, solid = [], None
    for blk in re.findall(r"\.ss-login-btn\{[^}]*\}", extra or ""):
        for grad in re.findall(r"linear-gradient\([^)]*\)", blk):
            stops += re.findall(r"#([0-9a-fA-F]{6})\b", grad)
        m = re.search(r"(?<!-)background:#([0-9a-fA-F]{6})\b", blk)
        if m and not stops:
            solid = m.group(1)
    return stops, solid


# ════════ hard fail 断言 ════════


def _check_pair(style: str, token: str, fg: str, bg_name: str, bg: str, minimum: float):
    r = _ratio(fg, bg)
    assert r >= minimum, (
        f"[{style}] {token} #{fg} on {bg_name} #{bg} = {r:.2f} < {minimum}（WCAG 不达标）"
    )


@pytest.mark.parametrize("style", sorted(_PRESETS))
def test_core_text_contrast(style):
    """每风格正文/辅助文字对 bg 与 card ≥ 4.5（classic 无 vars，由基座用例覆盖）。"""
    p = _PRESETS[style]
    if not (p.get("vars") or "").strip():
        pytest.skip("classic 无自带 vars，令牌继承基座（见 test_classic_base_contrast）")
    v = _parse_vars(p["vars"])
    for token in ("--txt", "--txt2"):
        for bg_name in ("--bg", "--card"):
            _check_pair(style, token, v[token], bg_name, v[bg_name], 4.5)


@pytest.mark.parametrize("style", sorted(_PRESETS))
def test_accent_contrast(style):
    """每风格 accent 对 bg 与 card ≥ 3.0（强调文字/链接/边框的 WCAG 大字阈值）。"""
    p = _PRESETS[style]
    if not (p.get("vars") or "").strip():
        pytest.skip("classic 无自带 vars，令牌继承基座（见 test_classic_base_contrast）")
    v = _parse_vars(p["vars"])
    for token in ("--acc1", "--acc2"):
        for bg_name in ("--bg", "--card"):
            _check_pair(style, token, v[token], bg_name, v[bg_name], 3.0)


@pytest.mark.parametrize("style", sorted(_PRESETS))
def test_login_cta_contrast(style):
    """登录 CTA 文字对按钮底色（默认 acc1→acc2 渐变两端 + extra 显式覆盖）≥ 4.5。"""
    p = _PRESETS[style]
    v = _parse_vars(p.get("vars") or "")
    extra = p.get("extra") or ""
    if not v:
        # classic：CTA 底色继承当前主题基座 acc1/acc2，两端各测一遍
        for base_name, base in _BASES.items():
            fg = _login_text(extra)
            _check_pair(f"{style}/{base_name}", "login-text on --acc1", fg, "--acc1", base["--acc1"], 4.5)
            _check_pair(f"{style}/{base_name}", "login-text on --acc2", fg, "--acc2", base["--acc2"], 4.5)
        return
    fg = _login_text(extra)
    _check_pair(style, "login-text on --acc1", fg, "--acc1", v["--acc1"], 4.5)
    _check_pair(style, "login-text on --acc2", fg, "--acc2", v["--acc2"], 4.5)
    stops, solid = _login_overrides(extra)
    for i, stop in enumerate(stops):
        _check_pair(style, f"login-text on 渐变stop{i}", fg, f"stop{i} #{stop}", stop, 4.5)
    if solid:
        _check_pair(style, "login-text on 显式背景", fg, "bg", solid, 4.5)


@pytest.mark.parametrize("base_name", ["dark", "light"])
def test_classic_base_contrast(base_name):
    """classic 双主题基座（dashboard_sf_css root + _DARK_CSS 拷贝）六对全测。"""
    base = _BASES[base_name]
    for token in ("--txt", "--txt2"):
        for bg_name in ("--bg", "--card"):
            _check_pair(f"classic/{base_name}", token, base[token], bg_name, base[bg_name], 4.5)
    for token in ("--acc1", "--acc2"):
        for bg_name in ("--bg", "--card"):
            _check_pair(f"classic/{base_name}", token, base[token], bg_name, base[bg_name], 3.0)


def test_dark_css_root_copy_consistent():
    """_DARK_CSS 内 :root 基座令牌拷贝与 dark 基座同口径达标（防两处拷贝漂移）。"""
    dark_css = None
    for node in ast.walk(ast.parse(THEME_SRC)):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_DARK_CSS" for t in node.targets
        ):
            dark_css = ast.literal_eval(node.value)
            break
    assert dark_css, "未找到 _DARK_CSS 定义"
    blocks = [b for b in re.findall(r":root\{([^}]*)\}", dark_css) if "--txt" in b]
    assert blocks, "_DARK_CSS 未提取到含 --txt 的 :root 令牌块"
    v = _parse_vars(blocks[0])
    for token in ("--txt", "--txt2"):
        for bg_name in ("--bg", "--card"):
            _check_pair("classic/_DARK_CSS", token, v[token], bg_name, v[bg_name], 4.5)
    for token in ("--acc1", "--acc2"):
        for bg_name in ("--bg", "--card"):
            _check_pair("classic/_DARK_CSS", token, v[token], bg_name, v[bg_name], 3.0)


def test_ink_metric_label_hardcoded():
    """ink extra 中 .stMetric label 硬编码色对 ink 卡片 ≥4.5（防硬编码绕过 vars 守卫）。"""
    ink = _PRESETS["ink"]
    m = re.search(r"\.stMetric\ label\{[^}]*color:#([0-9a-fA-F]{6})", ink["extra"])
    assert m, "ink extra 中未找到 .stMetric label 硬编码色（结构变更请同步本守卫）"
    v = _parse_vars(ink["vars"])
    _check_pair("ink", ".stMetric label 硬编码", m.group(1), "--card", v["--card"], 4.5)
