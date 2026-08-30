"""PURE offline tests for `_safe_video_markdown` (stored-XSS fix, R1/R2/R5).

The page module (pages/20_个股分析.py) executes heavy Streamlit/network top-level
code, so we do NOT import it. We stub `streamlit` to keep things offline and load
the pure helper in isolation via AST extraction, then exercise it directly.
"""
import sys
import types
import ast
import os

# STUB streamlit before touching anything page-related (keeps tests offline).
sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "pages", "20_个股分析.py")


def _load_pure_func(name):
    """Extract a module-level function def from the page file and exec it alone."""
    with open(PAGE, "r", encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = src.splitlines()
            block = "\n".join(lines[node.lineno - 1: node.end_lineno])
            ns = {}
            exec(compile(block, PAGE, "exec"), ns)
            return ns[name]
    raise AttributeError(name)


_safe_video_markdown = _load_pure_func("_safe_video_markdown")
_video_embed_url = _load_pure_func("_video_embed_url")


def test_safe_http_url_renders_escaped_link():
    v = {"raw": "https://www.bilibili.com/video/BV1xx"}
    out = _safe_video_markdown(v)
    assert out.startswith("<a href=")
    assert 'href="https://www.bilibili.com/video/BV1xx"' in out
    assert "target=\"_blank\"" in out
    # the URL text is escaped (no raw injection possible)
    assert out.count("https://www.bilibili.com/video/BV1xx") == 2


def test_javascript_scheme_has_no_href():
    v = {"raw": "javascript:alert(1)"}
    out = _safe_video_markdown(v)
    assert "<a " not in out
    assert "href=" not in out
    # plain text only — scheme is not presented as a clickable link
    assert "javascript:alert(1)" in out


def test_script_tag_in_url_is_escaped():
    v = {"raw": 'https://example.com/<script>alert(1)</script>'}
    out = _safe_video_markdown(v)
    # no live <script> tag survives
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    # https scheme -> still rendered as a (safe, escaped) link
    assert "<a href=" in out


def test_none_raw_is_safe_and_empty():
    assert _safe_video_markdown({"raw": None}) == ""
    assert _safe_video_markdown({}) == ""
    assert _safe_video_markdown({"raw": ""}) == ""


def test_video_embed_url_logic_untouched():
    # sanity: embedding logic is unchanged and independent of the render fix
    assert _video_embed_url("https://www.youtube.com/watch?v=abcd123") == \
        "https://www.youtube.com/embed/abcd123"
    assert _video_embed_url("not a url") is None
