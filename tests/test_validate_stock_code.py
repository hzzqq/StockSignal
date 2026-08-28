"""backend/utils/params.validate_stock_code 单元测试。"""
import pytest

from backend.utils.params import validate_stock_code


@pytest.mark.parametrize("inp,expect_ok,expect_norm", [
    ("600000", True, "600000"),
    (" 000001 ", True, "000001"),
    ("688001", True, "688001"),
    ("12345", False, ""),       # 不足 6 位
    ("1234567", False, ""),     # 超过 6 位
    ("AB1234", False, ""),      # 含字母
    ("60000X", False, ""),      # 末位非数字
    ("", False, ""),            # 空
    (None, False, ""),          # 非字符串
    (123456, False, ""),        # 非字符串(int)
])
def test_validate_stock_code(inp, expect_ok, expect_norm):
    ok, norm = validate_stock_code(inp)
    assert ok is expect_ok
    assert norm == expect_norm
