"""modules._search_utils 纯函数单测（R95 从 fetcher 拆出）。

验证：拼音首字母/全拼/多音字变体/分词 token —— 不构造 StockFetcher 实例、不触网。
"""
import pytest

from modules._search_utils import (
    name_tokens,
    pinyin_full,
    pinyin_initials_static,
    pinyin_initials_variants,
)


def test_pinyin_initials_static():
    assert pinyin_initials_static("招商银行") == "ZSYH"
    assert pinyin_initials_static("贵州茅台") == "GZMT"


def test_pinyin_full():
    assert pinyin_full("贵州茅台") == "guizhoumaotai"


def test_pinyin_initials_variants_handles_polyphone():
    # 长电科技：长 多音 (C/Z)，应有 CDKJ 与 ZDKJ 两种变体
    variants = pinyin_initials_variants("长电科技")
    assert "CDKJ" in variants
    assert "ZDKJ" in variants


def test_name_tokens_covers_common_abbrev():
    toks = name_tokens("招商银行")
    assert "招商银行" in toks      # 全称
    assert "招行" in toks          # 首+尾 简称
    assert "招商" in toks          # 2-gram
    assert "银行" in toks
    assert "商银" in toks          # 2-gram 中间


def test_search_utils_robust_to_bad_input():
    # 非中文 / 空串 不应抛异常
    assert pinyin_initials_static("") == ""
    assert name_tokens("") == {""}
    assert pinyin_full("ABC") == "abc"  # 无拼音时原样小写
