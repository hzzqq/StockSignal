"""backend/utils/params.sanitize_text 单元测试（用户输入清洗）。"""
import pytest

from backend.utils.params import sanitize_text


def test_strips_nul_and_zero_width():
    dirty = "hello\x00world\u200bend"
    assert sanitize_text(dirty) == "helloworldend"


def test_preserves_newline_tab_cr():
    s = "a\nb\tc\rd"
    assert sanitize_text(s) == "a\nb\tc\rd"


def test_strips_other_control_chars():
    # 退格 \x08、换页 \x0c 等控制字符应被剔除
    s = "pre\x08post\x0cmid"
    assert "\x08" not in sanitize_text(s)
    assert "\x0c" not in sanitize_text(s)
    assert "pre" in sanitize_text(s) and "post" in sanitize_text(s)


def test_truncates_to_max_len():
    s = "x" * 5000
    assert len(sanitize_text(s, max_len=10)) == 10


def test_non_string_returns_empty():
    assert sanitize_text(None) == ""
    assert sanitize_text(123) == ""


def test_strips_surrounding_whitespace():
    assert sanitize_text("  hello  ") == "hello"
