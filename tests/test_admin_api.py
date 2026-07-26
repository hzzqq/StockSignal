"""
tests/test_admin_api.py
-----------------------
PURE offline tests for ``build_query`` (modules/admin_api.py).

No network access: ``build_query`` only uses ``urllib.parse.urlencode`` and
skips ``None`` / empty-string params. We also make ``modules`` importable from
this test without altering repo layout (no conftest/__init__ changes).
"""
import os
import sys

# Ensure the project root (containing the ``modules`` package) is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.admin_api import build_query  # noqa: E402


def test_build_query_skips_none_and_empty():
    """None / '' params are dropped; only a=1 survives.

    Note: build_query prepends a leading '?' (relied on by its callers that
    concatenate it onto a path, e.g. get_users), so the actual return is
    '?a=1' rather than the bare 'a=1' described in the task spec.
    """
    result = build_query(a=1, b=None, c="")
    assert result == "?a=1"
    # b and c must be fully absent, not emitted as empty values.
    assert "b=" not in result
    assert "c=" not in result


def test_build_query_percent_encodes_chinese_and_equals():
    """Chinese and '=' in values are percent-encoded; no raw '=' breaks it."""
    result = build_query(name="中国", x="a=b")
    # The VALUE 'a=b' must be encoded -> raw 'a=b' must NOT appear, only 'a%3Db'.
    assert "a=b" not in result
    assert "a%3Db" in result
    # 中国 -> UTF-8 percent encoding.
    assert "%E4%B8%AD%E5%9B%BD" in result


def test_build_query_encodes_ampersand_and_space():
    """'&' and spaces in values are encoded so they don't break the query."""
    r_amp = build_query(q="a&b")
    assert "&" not in r_amp  # raw '&' would split into an extra param
    assert "a%26b" in r_amp

    r_space = build_query(q="a b")
    # quote_plus encodes space as '+'
    assert r_space == "?q=a+b"


def test_build_query_empty_returns_empty_string():
    """No params -> empty string (no leading '?')."""
    assert build_query() == ""
    assert build_query(page=None, keyword="") == ""
