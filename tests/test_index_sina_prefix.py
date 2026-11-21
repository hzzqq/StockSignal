# -*- coding: utf-8 -*-  # noqa: UP009
"""指数新浪前缀映射守卫（2026-11-21 缺陷修复回归）。

旧映射「6 开头 -> sh，其余 -> sz」是个股口径，用在指数上会把上证指数 000001
错映成 sz000001（平安银行）——登录页/v1 widgets 的「上证分时」实际是平安银行
的 12 元级个股分时。修复后：399 开头 -> sz（深市指数），其余 -> sh（沪/中证指数）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 先建完整 fetcher 类体系（fetcher_realtime 单独先导入会触发与 fetcher.py 的循环引用）
import modules.fetcher  # noqa: F401, E402
from modules.fetcher_realtime import _index_sina_prefix  # noqa: E402


def test_sh_index_prefix():
    assert _index_sina_prefix("000001") == "sh", "上证指数必须映射 sh000001"
    assert _index_sina_prefix("000300") == "sh", "沪深300 -> sh000300"
    assert _index_sina_prefix("000905") == "sh", "中证500 -> sh000905"


def test_sz_index_prefix():
    assert _index_sina_prefix("399001") == "sz", "深证成指 -> sz399001"
    assert _index_sina_prefix("399006") == "sz", "创业板指 -> sz399006"


def test_edge_inputs():
    assert _index_sina_prefix("") == "sh"
    assert _index_sina_prefix(None) == "sh"  # type: ignore[arg-type]
