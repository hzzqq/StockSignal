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
