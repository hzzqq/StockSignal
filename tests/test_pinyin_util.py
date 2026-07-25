"""R15：backend.services.pinyin_util 空白修复 + 新能力。

- to_initials / to_full_pinyin 不再泄漏首尾/内嵌空格（破坏精确拼音匹配）；
- 新增 search_key() 归一化拼音键；
- 新增 matches() 统一「名称 or 拼音」包含匹配。
"""
import backend.services.pinyin_util as pu


def test_no_stray_spaces():
    assert pu.to_initials(" 平安银行 ") == "payh"
    assert pu.to_full_pinyin(" 平安银行 ") == "pinganyinhang"
    # 内嵌空格也应被剔除
    assert pu.to_initials("平安 银行") == "payh"
    assert pu.to_full_pinyin("平安 银行") == "pinganyinhang"


def test_basic_conversion():
    assert pu.to_initials("平安银行") == "payh"
    assert pu.to_full_pinyin("平安银行") == "pinganyinhang"


def test_search_key_format():
    assert pu.search_key("平安银行") == "pinganyinhang|payh"


def test_matches_by_name_and_pinyin():
    assert pu.matches("平安银行", "平安") is True
    assert pu.matches("平安银行", "pinganyinhang") is True
    assert pu.matches("平安银行", "payh") is True
    assert pu.matches("平安银行", "PAYH") is True  # 大小写无关
    assert pu.matches("平安银行", "招商") is False


def test_none_and_empty_safe():
    assert pu.to_initials("") == ""
    assert pu.to_initials(None) == ""
    assert pu.search_key("") == ""
    assert pu.matches("", "x") is False
    assert pu.matches("平安银行", "") is False
    assert pu.matches("平安银行", None) is False


def test_degrade_without_pypinyin(monkeypatch):
    monkeypatch.setattr(pu, "_HAS_PYPINYIN", False)
    assert pu.to_initials("平安银行") == ""
    assert pu.to_full_pinyin("平安银行") == ""
    assert pu.search_key("平安银行") == ""
    # 无 pypinyin 时仅能按原始名匹配
    assert pu.matches("平安银行", "平安") is True
    assert pu.matches("平安银行", "payy") is False
