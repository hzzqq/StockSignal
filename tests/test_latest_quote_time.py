"""锐评 R11 守卫：自选股监控页"行情更新于"必须取最新报价时间，而非最早。

同一函数内 line 278 的 data_time 已用 max（最新），line 210 的"行情更新于"
曾用 min（最早），前后矛盾且系统性低估数据新鲜度。修复后两处统一走
modules.page_utils.latest_quote_time（取 max）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.page_utils import latest_quote_time


def test_latest_quote_time_returns_newest():
    q = [
        "2024-01-01 09:31:00",
        "2024-01-01 09:35:00",
        "2024-01-01 09:40:00",
    ]
    # 最新报价应为 09:40，而非 09:31（旧 min 行为）
    assert latest_quote_time(q) == "2024-01-01 09:40:00"
    assert latest_quote_time(q) != min(q), "绝不能取最早时间"


def test_latest_quote_time_empty_returns_dash():
    assert latest_quote_time([]) == "—"
    assert latest_quote_time(None) == "—"


def test_latest_quote_time_single():
    assert latest_quote_time(["2024-01-01 10:00:00"]) == "2024-01-01 10:00:00"


def test_latest_quote_time_is_max_not_min():
    """核心不变量：最新 = max，绝不能是 min。"""
    q = ["2024-01-01 09:31:00", "2024-01-01 09:45:00"]
    assert latest_quote_time(q) == max(q)
    assert latest_quote_time(q) != min(q)


def test_page_46_no_longer_uses_min_of_quote_times():
    """源码守卫：页面不得再出现 min(quote_times) 的"更新于"逻辑。"""
    page = os.path.join(os.path.dirname(__file__), "..", "pages", "46_自选股监控.py")
    src = open(page, encoding="utf-8").read()
    assert "min(quote_times)" not in src, "page 46 仍存在 min(quote_times)（应改 latest_quote_time）"
    assert "latest_quote_time(quote_times)" in src, "page 46 未接入 latest_quote_time 单一真理源"
