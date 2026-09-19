# -*- coding: utf-8 -*-
"""tests/test_ui_kit_tokens.py — ui_kit 设计令牌层守卫（T-145 批1）。

spec：``.workbuddy/specs/t145_ui_upgrade_contract.md``（A1 token 基座 / A2 暗色修复 / A3 metric 皮肤）。

锁四条不变量：
1. token 表必须存在，且同时接入 _KIT_CSS 与 _HERO_FALLBACK_CSS 两条注入通道
   （冷启动首帧兜底不丢 token，var() 不落空）；
2. A 股红涨绿跌语义 token --ss-up/--ss-down 必须与 modules/colors 的
   UP_COLOR/DOWN_COLOR 同值（语义不可反转）；
3. 基元必须读 token：.xc-card/.ss-stat 的圆角/阴影/表面/强调边，delta 语义色
   不得再散落硬编码 hex（token 定义行除外）；
4. AC1：pages/ 源码禁止硬编码浅色底（行业卡 #fde8e6/#e8f9ef 曾在暗色主题下违和）。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _kit():
    import modules.ui_kit as kit
    return kit


def test_token_layer_defined_and_wired():
    """A1：token 表存在，且两条 CSS 注入通道（主样式 + 首帧兜底）都带 token 层。"""
    kit = _kit()
    css = kit._KIT_CSS
    required = (
        "--ss-up:#ff4d4f", "--ss-down:#00d486",
        "--ss-radius:12px", "--ss-radius-card:16px", "--ss-radius-pill:999px",
        "--ss-space-1:4px", "--ss-space-3:12px", "--ss-space-5:20px",
        "--ss-shadow-card:", "--ss-shadow-lift:", "--ss-shadow-hero:",
        "--ss-font-num:",
        "--ss-accent:var(--acc1", "--ss-accent2:var(--acc2",
        "--ss-surface:var(--card", "--ss-surface-2:var(--card2",
        "--ss-text:var(--txt", "--ss-text-muted:var(--txt2", "--ss-line:var(--border",
    )
    missing = [t for t in required if t not in css]
    assert not missing, f"ui_kit token 层缺失: {missing}"
    # 首帧兜底通道也必须带 token（page_hero 每帧注入，var() 不落空）
    assert "--ss-radius-card:16px" in kit._HERO_FALLBACK_CSS
    assert "--ss-up:#ff4d4f" in kit._HERO_FALLBACK_CSS


def test_updown_tokens_match_a_share_semantics():
    """红涨绿跌语义 token 必须与 colors.py 单一来源同值，语义不可反转。"""
    from modules.colors import UP_COLOR, DOWN_COLOR
    css = _kit()._KIT_CSS
    assert UP_COLOR == "#ff4d4f" and DOWN_COLOR == "#00d486", (
        "colors.py A 股基线漂移？先复核单一来源再谈 token"
    )
    assert f"--ss-up:{UP_COLOR}" in css, "涨色 token 必须等于 UP_COLOR（红涨）"
    assert f"--ss-down:{DOWN_COLOR}" in css, "跌色 token 必须等于 DOWN_COLOR（绿跌）"


def test_primitives_read_tokens_no_stray_hex():
    """A1/A3：基元读 token；涨跌语义 hex 只允许出现在 token 定义行各 1 次。"""
    css = _kit()._KIT_CSS
    assert css.count("#ff4d4f") == 1 and css.count("#00d486") == 1, (
        "涨跌语义 hex 只应在 token 定义出现一次，其余必须走 var(--ss-up/--ss-down)"
    )
    assert "color:var(--ss-up)" in css and "color:var(--ss-down)" in css
    m = re.search(r"\.xc-card\{([^}]*)\}", css)
    assert m, "缺少 .xc-card 规则"
    xc = m.group(1)
    for frag in ("var(--ss-surface)", "var(--ss-radius-card)",
                 "var(--ss-shadow-card)", "var(--ss-accent)"):
        assert frag in xc, f".xc-card 未读 token {frag}"
    m2 = re.search(r"\.ss-stat\{([^}]*)\}", css)
    assert m2, "缺少 .ss-stat 规则"
    assert "var(--ss-radius-card)" in m2.group(1) and "var(--ss-shadow-card)" in m2.group(1)


def test_pages_no_hardcoded_light_bg():
    """AC1：暗色主题页面不得硬编码浅色底（行业卡 #fde8e6/#e8f9ef 曾违和）。"""
    banned = ("#fde8e6", "#e8f9ef")
    offenders = []
    for p in sorted((ROOT / "pages").rglob("*.py")):
        low = p.read_text(encoding="utf-8", errors="replace").lower()
        hit = [b for b in banned if b in low]
        if hit:
            offenders.append(f"{p.name}: {hit}")
    assert not offenders, f"pages 存在硬编码浅色底，应改走 ui_kit token: {offenders}"


def test_stmetric_skin_shares_token_vars(monkeypatch):
    """A3：stMetric 皮肤与 .xc-card 共享同一组 token 变量（token 层随 dashboard_sf_css 注入）。"""
    import modules.ui_theme as ui_theme
    monkeypatch.setattr(ui_theme, "_theme_is_dark", lambda: False)
    ui_theme._DASHBOARD_SF_CSS_CACHE.clear()
    css = ui_theme.dashboard_sf_css()
    assert "--ss-radius-card:16px" in css, "dashboard_sf_css 未注入 ui_kit token 层"
    assert "border-radius:var(--ss-radius-card)!important" in css
    assert "box-shadow:var(--ss-shadow-card)!important" in css
    assert "color-mix(in srgb,var(--ss-accent) 22%,var(--ss-line))!important" in css
