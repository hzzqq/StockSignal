"""tests/test_component_vocabulary.py — 组件词汇统一守卫（P2）。

锁死「sf_card → xc_content_card」迁移结果：
1. pages/ 中不得再出现 sf_card( 调用（统一到 xc_* 词汇）。
2. ui_theme.sf_card 本体必须保留（test_page91_prefs_slim 契约依赖其空 body 分支）。
3. xc_content_card 为 canonical 内容卡，pages/ 中确有使用。
4. xc_content_card 复刻 sf_card 的 T-266 空间治理：空 body → 紧凑节标题（不渲染大卡片）。
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
UI_THEME = ROOT / "modules" / "ui_theme.py"
UI_KIT = ROOT / "modules" / "ui_kit.py"

_SRC_CACHE = {}


def _src(p: pathlib.Path) -> str:
    if p not in _SRC_CACHE:
        _SRC_CACHE[p] = p.read_text(encoding="utf-8")
    return _SRC_CACHE[p]


def test_no_sf_card_calls_in_pages():
    """pages/ 不得再有 sf_card( 调用（已统一为 xc_content_card）。"""
    offenders = []
    for f in sorted(PAGES.glob("*.py")):
        src = _src(f)
        # 跳过注释行中的偶然提及；调用点 sf_card( 必出现在非注释上下文
        for ln in src.splitlines():
            stripped = ln.strip()
            if stripped.startswith("#"):
                continue
            if "sf_card(" in ln:
                offenders.append(f.name)
                break
    assert offenders == [], f"以下页面仍调用 sf_card：{offenders}"


def test_sf_card_body_kept_in_ui_theme():
    """ui_theme.sf_card 本体保留（契约依赖），且仍含空 body 紧凑分支。"""
    src = _src(UI_THEME)
    assert "def sf_card(" in src
    assert "if not str(body).strip():" in src  # 空 body → .sf-section-title 分支仍在


def test_xc_content_card_is_canonical_and_used():
    """xc_content_card 已落地 ui_kit，且 pages/ 中确有使用。"""
    kit_src = _src(UI_KIT)
    assert "def xc_content_card(" in kit_src
    assert ".xc-content-card" in kit_src
    used = [f.name for f in sorted(PAGES.glob("*.py")) if "xc_content_card(" in _src(f)]
    assert len(used) >= 25, f"xc_content_card 使用面过窄（疑似回归）：{len(used)} 页"


def test_xc_content_card_compact_when_empty():
    """xc_content_card 复刻 T-266：空 body 走紧凑节标题（不渲染 .xc-content-card 大卡片）。"""
    import streamlit as st
    from modules import ui_kit as kit

    captured = []
    monkeypatch_markdown = lambda html, *a, **k: captured.append(html)  # noqa: E731
    orig = st.markdown
    st.markdown = monkeypatch_markdown
    try:
        kit.xc_content_card("仅标题")
        empty_out = captured[-1]
        assert "xc-content-card" not in empty_out, "空 body 不应渲染大卡片"
        assert "xc-section-h" in empty_out, "空 body 应降级为紧凑节标题"

        kit.xc_content_card("有正文", "说明文字")
        body_out = captured[-1]
        assert "xc-content-card" in body_out, "非空 body 应渲染内容卡"
        assert "说明文字" in body_out
    finally:
        st.markdown = orig


def test_no_legacy_info_banner_calls():
    """B 阶段守卫：legacy info_banner( 调用全仓清零（统一为 xc_info_banner）。

    modules/ui_kit.py 例外（deprecated 定义 + 兼容委托本体所在）。
    """
    import re
    legacy = re.compile(r"(?<![\w.])info_banner\(")
    roots = [ROOT / "pages", ROOT / "modules", ROOT / "backend", ROOT / "scripts"]
    offenders = []
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            if "__pycache__" in str(f) or f == UI_KIT:
                continue
            for i, ln in enumerate(_src(f).splitlines(), 1):
                if ln.strip().startswith("#"):
                    continue
                if legacy.search(ln):
                    offenders.append(f"{f.relative_to(ROOT)}:{i}")
    assert offenders == [], f"仍调用 legacy info_banner（应改 xc_info_banner）：{offenders}"


def test_info_banner_deprecated_delegate_and_xc_canonical():
    """info_banner 已标 Deprecated 薄委托；xc_info_banner 为 canonical 且走
    _info_banner_html 渲染（T-277 长文案折叠语义保留）。"""
    kit_src = _src(UI_KIT)
    assert "def xc_info_banner(" in kit_src
    assert "def info_banner(" in kit_src
    # xc 版渲染走 canonical _info_banner_html（含 T-277 折叠），不允许另起炉灶
    xc_start = kit_src.index("def xc_info_banner(")
    nxt = kit_src.find("\ndef ", xc_start + 1)
    xc_body = kit_src[xc_start:nxt if nxt > 0 else len(kit_src)]
    assert "_info_banner_html" in xc_body, "xc_info_banner 必须复用 _info_banner_html（T-277 折叠）"
    # legacy 名标 Deprecated 且为薄委托
    legacy_start = kit_src.index("def info_banner(")
    legacy_body = kit_src[legacy_start:legacy_start + 400]
    assert "Deprecated" in legacy_body, "info_banner 未标 Deprecated"
    assert "xc_info_banner(text, kind, icon)" in legacy_body, "info_banner 应薄委托 xc_info_banner"


def test_no_legacy_section_header_calls():
    """C 收官守卫：legacy section_header( 调用全仓清零（统一为 xc_section_header）。

    modules/ui_theme.py 例外（deprecated 定义 + 兼容委托本体所在）。
    同时锁「调用了 xc_section_header 的文件必须从 modules.ui_kit 导入它」，
    防迁移后出现 NameError。
    """
    import re
    legacy = re.compile(r"(?<![\w.])section_header\(")
    xc_call = re.compile(r"(?<![\w.])xc_section_header\(")
    xc_import = re.compile(
        r"from modules\.ui_kit import\s*(?:\([^)]*\)|[^\n]*)", re.S
    )  # 兼容单行与括号多行 import 块
    roots = [ROOT / "pages", ROOT / "modules", ROOT / "backend", ROOT / "scripts"]
    offenders = []
    undefined = []
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            if "__pycache__" in str(f) or f == UI_THEME:
                continue
            src = _src(f)
            if "def xc_section_header(" in src or "def section_header(" in src:
                continue  # 定义文件（ui_kit）自洽
            for i, ln in enumerate(src.splitlines(), 1):
                if ln.strip().startswith("#"):
                    continue
                if legacy.search(ln):
                    offenders.append(f"{f.relative_to(ROOT)}:{i}")
            if xc_call.search(src) and not xc_import.search(src):
                undefined.append(str(f.relative_to(ROOT)))
    assert offenders == [], f"仍调用 legacy section_header（应改 xc_section_header）：{offenders}"
    assert undefined == [], f"调用 xc_section_header 但未从 modules.ui_kit 导入：{undefined}"


def test_section_header_deprecated_delegate_and_xc_contract():
    """ui_theme.section_header 已标 Deprecated 薄委托（惰性导入防循环）；
    xc_section_header 为 canonical：render=True 默认直接渲染（兼容 legacy 即渲染契约）、
    render=False 返回 HTML 片段（供 _hero / widgets 嵌入），支持 subtitle/icon/xtra。"""
    theme_src = _src(UI_THEME)
    assert "def section_header(" in theme_src
    legacy_start = theme_src.index("def section_header(")
    legacy_body = theme_src[legacy_start:legacy_start + 900]
    assert "deprecated" in legacy_body.lower(), "section_header 未标 deprecated"
    assert "xc_section_header(title, subtitle=subtitle, icon=icon)" in legacy_body, (
        "section_header 应薄委托 xc_section_header"
    )
    assert "#4f46e5" not in legacy_body, "legacy 本体不应再含硬编码 hex（已收敛到 token）"

    kit_src = _src(UI_KIT)
    assert "def xc_section_header(" in kit_src
    xc_start = kit_src.index("def xc_section_header(")
    nxt = kit_src.find("\ndef ", xc_start + 1)
    xc_body = kit_src[xc_start:nxt if nxt > 0 else len(kit_src)]
    assert "render: bool = True" in xc_body, "xc_section_header 默认必须渲染（legacy 契约）"
    assert "subtitle" in xc_body and "icon" in xc_body and "xtra" in xc_body, (
        "xc_section_header 须支持 subtitle/icon/xtra 三要素"
    )
    assert "return html_out" in xc_body, "render=False 路径须返回 HTML 片段"
