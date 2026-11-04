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


def _token_chain_css() -> str:
    """整条 token 注入链：组件层(_KIT_CSS + _HERO_FALLBACK_CSS) + 全局主题层(_DARK_CSS/_LIGHT_CSS)。

    C0-c 起 --ss-up/--ss-down 归**全局主题层**（_DARK_CSS/_LIGHT_CSS 的 :root，始终注入），
    组件层不再硬写——否则 _TOKEN_CSS 在 page_hero() 里最后注入会盖住 preset vars
    （6 套风格的次品牌色会全部退化成经典紫）。语义色因此仍不落空，只是换了层。
    """
    import modules.ui_kit as kit
    from modules import ui_theme as ut
    return (kit._KIT_CSS + kit._HERO_FALLBACK_CSS
            + getattr(ut, "_DARK_CSS", "") + getattr(ut, "_LIGHT_CSS", ""))


def test_token_layer_defined_and_wired():
    """A1：token 表存在，且两条 CSS 注入通道（主样式 + 首帧兜底）都带 token 层。"""
    kit = _kit()
    css = kit._KIT_CSS
    required = (   # 组件层专有 token（语义色不在组件层，见 _token_chain_css）
        "--ss-radius:12px", "--ss-radius-card:16px", "--ss-radius-pill:999px",
        "--ss-space-1:4px", "--ss-space-3:12px", "--ss-space-5:20px",
        "--ss-shadow-card:", "--ss-shadow-lift:", "--ss-shadow-hero:",
        "--ss-font-num:",
        "--ss-font-cjk:'Microsoft YaHei UI'", "'PingFang SC'",
        "--ss-accent:var(--brand-1", "--ss-accent2:var(--brand-2",
        "--ss-surface:var(--card", "--ss-surface-2:var(--card2",
        "--ss-text:var(--txt", "--ss-text-muted:var(--txt2", "--ss-line:var(--border",
    )
    missing = [t for t in required if t not in css]
    assert not missing, f"ui_kit token 层缺失: {missing}"
    # 首帧兜底通道也必须带 token（page_hero 每帧注入，var() 不落空）
    assert "--ss-radius-card:16px" in kit._HERO_FALLBACK_CSS
    # 语义色：整条注入链上必须存在（var() 不落空）——C0-c 起归全局主题层
    chain = _token_chain_css()
    assert "--ss-up:#ff4d4f" in chain, "语义色 --ss-up 在整条注入链上缺失（var() 会落空）"
    assert "--ss-down:#00d486" in chain, "语义色 --ss-down 在整条注入链上缺失（var() 会落空）"


def test_updown_tokens_match_a_share_semantics():
    """红涨绿跌语义 token 必须与 colors.py 单一来源同值，语义不可反转。"""
    from modules.colors import UP_COLOR, DOWN_COLOR
    css = _token_chain_css()   # C0-c 起语义色归全局主题层（见 _token_chain_css 注释）
    assert UP_COLOR == "#ff4d4f" and DOWN_COLOR == "#00d486", (
        "colors.py A 股基线漂移？先复核单一来源再谈 token"
    )
    assert f"--ss-up:{UP_COLOR}" in css, "涨色 token 必须等于 UP_COLOR（红涨）"
    assert f"--ss-down:{DOWN_COLOR}" in css, "跌色 token 必须等于 DOWN_COLOR（绿跌）"


def test_primitives_read_tokens_no_stray_hex():
    """A1/A3：基元读 token；涨跌语义 hex 只允许出现在 token 定义行。

    design_system.md 第5章C阶段新增 --c-up/--c-down 别名（兜底值 #ff4d4f/#00d486），
    属合法定义行；其余业务样式必须走 var(--ss-up/--ss-down)，不得直写 hex。
    """
    css = _kit()._KIT_CSS
    up_lines = [ln for ln in css.splitlines() if "#ff4d4f" in ln]
    down_lines = [ln for ln in css.splitlines() if "#00d486" in ln]
    _UP_DEF = ("--ss-up:#ff4d4f", "--c-up:var(--ss-up,#ff4d4f)")
    _DOWN_DEF = ("--ss-down:#00d486", "--c-down:var(--ss-down,#00d486)")
    for ln in up_lines:
        assert any(d in ln for d in _UP_DEF), f"#ff4d4f 出现在非定义行（须走 var(--ss-up)）：{ln.strip()}"
    for ln in down_lines:
        assert any(d in ln for d in _DOWN_DEF), f"#00d486 出现在非定义行（须走 var(--ss-down)）：{ln.strip()}"
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


def test_xc_hero_block_identical_across_two_channels():
    """G2（ui-ds Phase1 §2.2①痛4）：_KIT_CSS 与 _HERO_FALLBACK_CSS 的 .xc-hero 家族块
    必须逐字符一致——两通道现已是复制粘贴双写（维护漂移源），锁死后只允许改一处再同步。

    P1 增强版：比对范围从 `.xc-hero{` 主块扩到整个家族（主块 + ::before + -main/-icon/
    -title/-sub/-chips，即到 `.xc-hero-chips{…}` 为止）——P1-2 改 ::before 为
    --ss-hero-overlay 时若只改一条通道，此处立即红。

    Phase3 评审已实测现状逐字符一致，故直接 hard 上线，无过渡期。
    """
    css_main = _kit()._KIT_CSS
    css_fallback = _kit()._HERO_FALLBACK_CSS
    pat = re.compile(r"\.xc-hero\{.*?\.xc-hero-chips\{[^}]*\}", re.S)
    m_main = pat.search(css_main)
    m_fb = pat.search(css_fallback)
    assert m_main, "_KIT_CSS 缺少 .xc-hero 家族块"
    assert m_fb, "_HERO_FALLBACK_CSS 缺少 .xc-hero 家族块"
    assert m_main.group(0) == m_fb.group(0), (
        "两通道 .xc-hero 家族块漂移（双写不再一致）：\n"
        f"  _KIT_CSS:          {m_main.group(0)}\n"
        f"  _HERO_FALLBACK_CSS: {m_fb.group(0)}\n"
        "同步两处后此测试才会绿——禁止只改一条通道"
    )


def test_deprecated_ss_vocab_not_used_in_pages():
    """废弃标记配套禁令（ui-ds Phase1 §2.3）：.ss-stat/.ss-info/.ss-chart 旧词汇
    规则本体保留（兜底 + 存在性锁），但 pages/modules（ui_kit 自身除外）不得新增
    class="ss-stat"/"ss-info"/"ss-chart" 字面量——HTML 构建器已全部路由 xc_*。"""
    banned = ('class="ss-stat"', 'class="ss-info"', 'class="ss-chart"',
              "class='ss-stat'", "class='ss-info'", "class='ss-chart'")
    offenders = []
    targets = sorted((ROOT / "pages").rglob("*.py")) + [
        p for p in sorted((ROOT / "modules").rglob("*.py")) if p.name != "ui_kit.py"]
    for p in targets:
        src = p.read_text(encoding="utf-8", errors="replace")
        hit = [b for b in banned if b in src]
        if hit:
            offenders.append(f"{p.name}: {hit}")
    assert not offenders, f"出现废弃 ss-* 词汇字面量（应改走 xc_* 构建器）：{offenders}"


def test_info_box_success_decoupled_from_down():
    """P1-2d（ui-ds Phase1 §2.2④）：信息盒族 success 语义必须走 --ss-box-success
    （=var(--ss-ok) 功能绿），不得再引用 --ss-down（A 股跌价绿）——
    「信息盒绿色 ≠ 跌价」认知解耦；--ss-box-* 四别名必须在 _TOKEN_CSS 定义。"""
    css = _kit()._TOKEN_CSS
    for tok in ("--ss-box-info:var(--ss-accent)", "--ss-box-success:var(--ss-ok)",
                "--ss-box-warn:var(--ss-warn-strong)", "--ss-box-danger:var(--ss-danger)"):
        assert tok in css, f"信息盒语义别名缺失：{tok}"
    kit_css = _kit()._KIT_CSS
    m = re.search(r"\.xc-success-box\{([^}]*)\}", kit_css)
    assert m, "缺少 .xc-success-box 规则"
    assert "var(--ss-down)" not in m.group(1), (
        ".xc-success-box 仍引用 --ss-down（跌价绿兼任 success 的认知风险回归）")
    assert "var(--ss-box-success)" in m.group(1)
    m2 = re.search(r"\.xc-info\.success\{([^}]*)\}", kit_css)
    assert m2 and "var(--ss-box-success)" in m2.group(1)


def test_content_card_title_reads_fs_title_token():
    """P1-2c（ui-ds Phase1 §2.2③）：.xc-content-card 标题 15px → var(--ss-fs-title)，
    与 xc-section-h 16px / sf-card-title 16px 统一到 title 级字号阶梯。"""
    css = _kit()._KIT_CSS
    m = re.search(r"\.xc-content-card \.xc-cc-title\{([^}]*)\}", css)
    assert m, "缺少 .xc-content-card .xc-cc-title 规则"
    assert "font-size:var(--ss-fs-title)" in m.group(1), (
        ".xc-cc-title 未读 --ss-fs-title（字号阶梯收敛回潮）")
    assert "15px" not in m.group(1), ".xc-cc-title 仍有 15px 硬编码"


def test_hero_overlay_and_pill_tokens_wired():
    """P1-2（ui-ds Phase1 §2.2①）：page_hero 升级的令牌接线断言。

    ① .xc-hero::before 雷达光层必须读 --ss-hero-overlay（accent2 派生），
       不得回退为 --ss-glow-soft（accent 派生）或硬编码 rgba(124,92,255,*)；
    ② .ss-pill.theme-dark 不得再硬编码 indigo（#c7d2fe/#3b3b66/#1a1a2e），
       必须读 L3 --ss-pill-dark-fg/--ss-pill-dark-bg（P0 已落 _TOKEN_CSS）。
    """
    css = _kit()._KIT_CSS
    m = re.search(r"\.xc-hero::before\{([^}]*)\}", css)
    assert m, "缺少 .xc-hero::before 规则"
    assert "var(--ss-hero-overlay)" in m.group(1), (
        ".xc-hero::before 未读 --ss-hero-overlay（terminal/cyber 下紫光穿帮回归风险）")
    assert "--ss-glow-soft" not in m.group(1)
    m2 = re.search(r"\.ss-pill\.theme-dark\{([^}]*)\}", css)
    assert m2, "缺少 .ss-pill.theme-dark 规则"
    pill = m2.group(1)
    for frag in ("var(--ss-pill-dark-fg)", "var(--ss-pill-dark-bg)"):
        assert frag in pill, f".ss-pill.theme-dark 未读 L3 pill 令牌 {frag}"
    for banned in ("#c7d2fe", "#3b3b66", "#1a1a2e{"):
        assert banned not in pill, f".ss-pill.theme-dark 仍有 indigo 硬编码：{banned}"


def test_no_hardcoded_purple_rgba_in_kit_and_theme():
    """P0.5 紫光清零（G1 硬守卫）：ui_kit.py / ui_theme.py 源码不得再出现
    经典紫 rgba(102,126,234,*) / rgba(124,92,255,*) 硬编码——紫光穿帮根因。

    G1 扩展（2026-11-01）：覆盖面从 ui_kit/ui_theme 扩到共享组件 chrome 层
    （button_colors/widgets/_compare_render）。不锁 hex #667eea——它是
    --ss-accent 的合法回退默认值（starfield --brand-1 同理）；Plotly/echarts
    数据可视化序列色不属 chrome，不在本锁内。

    本守卫读取两文件原始文本，断言子串 ``rgba(102,126,234`` 与 ``rgba(124,92,255``
    各出现 0 次（含注释），证明紫 rgba 已全量清零为 L3 令牌引用。
    注：ui_theme.card() 内带空格的 ``rgba(102, 126, 234, 0.10)`` 不匹配本无空格子串，
    且属 _KIT_CSS / dashboard_sf_css 命名范围之外，留待后续专项，不在此锁。"""
    banned = ("rgba(102,126,234", "rgba(124,92,255")
    for mod in ("ui_kit", "ui_theme", "button_colors", "widgets", "_compare_render"):
        src = (ROOT / "modules" / f"{mod}.py").read_text(encoding="utf-8")
        for b in banned:
            assert src.count(b) == 0, f"{mod}.py 仍存在紫 rgba 硬编码：{b!r}"


def test_typography_contract_cjk_and_base_font_size():
    """T-261：全局排版契约——CJK 字体栈落 token、行高 1.65、等宽保护、
    config.toml baseFontSize=17（用户反馈默认字体小）。

    T-312 勘测纠偏：baseFontSize 必须写整型 17（Streamlit CustomTheme proto 的
    base_font_size 是 int 字段），旧写法 "17px" 字符串会让 NewSession 消息创建抛
    TypeError → 全站 run_every 轮询片段失联。类型守卫见 test_config_theme_types.py。
    """
    kit = _kit()
    css = kit._TOKEN_CSS + kit._KIT_CSS
    assert "font-family: var(--ss-font-cjk)" in css, "CJK 字体栈未落地"
    assert "Microsoft YaHei UI" in css and "PingFang SC" in css, "中文字体栈不完整"
    assert "line-height: 1.65" in css, "阅读行高缺失"
    assert "font-family: var(--ss-font-num) !important" in css,         "等宽保护缺失（code/pre 必须显式回落数字字体）"
    cfg = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "baseFontSize = 17" in cfg, "config.toml 全局基础字号 17（整型）缺失"
    assert 'baseFontSize = "17px"' not in cfg,         "baseFontSize 回潮为字符串（T-312：会绞杀全站轮询消息通道）"


def test_token_aliases_bound_to_existing():
    """design_system.md 第2章：--brand-1/--brand-2 为品牌令牌（具体 hex 单源，非 --acc 别名），不得臆造独立色相。"""
    css = _kit()._KIT_CSS
    required_aliases = (
        "--c-up:var(--ss-up,#ff4d4f)", "--c-down:var(--ss-down,#00d486)",
        "--c-ok:var(--ss-ok,#16a34a)",
        "--c-hold:#ffa502", "--c-warn:#f59e0b", "--c-danger:#ef4444", "--c-info:#3b82f6",
        "--radius-card:var(--ss-radius-card", "--font-num:var(--ss-font-num)",
    )
    for a in required_aliases:
        assert a in css, f"令牌别名缺失或值未绑定现有令牌：{a}"


def test_build_token_css_from_colors_single_source():
    """_build_token_css 须由 colors.* 派生（单一来源）且关键语义与 _TOKEN_CSS 别名同值。"""
    kit = _kit()
    from modules import colors
    gen = kit._build_token_css()
    assert f"--c-up:{colors.UP_COLOR}" in gen    # colors.UP_COLOR
    assert f"--c-down:{colors.DOWN_COLOR}" in gen  # colors.DOWN_COLOR
    assert f"--c-hold:{colors.HOLD_COLOR}" in gen  # colors.HOLD_COLOR
    # 与 _TOKEN_CSS 内联别名一致（解析 --c-up 取值为 #ff4d4f 等价）
    m = re.search(r"--c-up:(var\(--ss-up,#ff4d4f\)|#ff4d4f)", kit._KIT_CSS)
    assert m, "内联 --c-up 别名未绑定 #ff4d4f 等价"


def test_token_css_does_not_hardcode_theme_tokens():
    """C0-g 锁不越权：组件层(_TOKEN_CSS)不得硬写主题层令牌。

    背景（D4）：_TOKEN_CSS 的 :root 硬写 --brand-1/--brand-2 会盖住 preset vars，
    且它在 page_hero() 里【最后注入】⇒ 6 套风格的次品牌色全部退化成经典紫。
    此守卫用带冒号的精确形态（'--ss-up' 不带冒号会命中 var(--ss-up) 等用法而误报）。
    """
    css = _kit()._KIT_CSS
    for tok in ("--brand-1:#", "--brand-2:#", "--ss-up:#", "--ss-down:#"):
        assert tok not in css, (
            f"_TOKEN_CSS 不得硬写主题层令牌 {tok}（应归 _THEME_ROOT_VARS / preset vars）")


def test_theme_tokens_owned_by_theme_layer():
    """C0-g 锁归属：主题层令牌须由 _THEME_ROOT_VARS 提供（dark/light 值不同，必须分别断言）。"""
    from modules import ui_theme as ut
    assert "--brand-1:#4f46e5" in ut._THEME_ROOT_VARS["light"], "--brand-1 须由主题层提供(light)"
    assert "--brand-1:#5b53f0" in ut._THEME_ROOT_VARS["dark"], "--brand-1 须由主题层提供(dark)"
    assert "--doc-up:#009e60" in ut._THEME_ROOT_VARS["dark"], "价格域须由主题层提供(dark)"
    assert "--doc-up:#009e60" in ut._THEME_ROOT_VARS["light"], "价格域须由主题层提供(light)"
    assert "--buy:#ff4d4f" in ut._THEME_ROOT_VARS["light"], "classic 亮色须自带 --buy（C0-e）"
    assert "--sell:#00d486" in ut._THEME_ROOT_VARS["light"], "classic 亮色须自带 --sell（C0-e）"


def test_theme_cache_key_includes_style():
    """C0-f：缓存键必须含 style，否则切风格后仪表盘层静默返回上一个风格的 CSS（D6）。"""
    import inspect
    from modules import ui_theme as ut
    src = inspect.getsource(ut.dashboard_sf_css)
    assert "_DASHBOARD_SF_CSS_CACHE.get((dark, _style))" in src, "缓存读键未含 style"
    assert "_DASHBOARD_SF_CSS_CACHE[(dark, _style)] = _css" in src, "缓存写键未含 style"
    assert "STYLE_PRESETS.get(_style" in src, ":root 未合并 preset vars（C0-d 缺失）"
