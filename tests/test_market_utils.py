"""
tests/test_market_utils.py
==========================
校验 modules.market_utils 统一的交易所/板块判定，并锁定与历史实现一致
（search_ui._derive_tag / _guess_market、analysis_engine._board 委托后行为不变）。
"""
from __future__ import annotations

from modules.market_utils import guess_exchange, short_tag, board_name


def test_guess_exchange():
    assert guess_exchange("600519") == "SH"
    assert guess_exchange("000858") == "SZ"
    assert guess_exchange("300750") == "SZ"
    assert guess_exchange("899999") == ""
    assert guess_exchange("") == ""
    assert guess_exchange(None) == ""
    assert guess_exchange("abc") == ""


def test_short_tag():
    assert short_tag("688981") == "科创板"
    assert short_tag("689009") == "科创板"
    assert short_tag("830799") == "北交所"
    assert short_tag("430047") == "北交所"
    assert short_tag("900901") == "沪B"
    assert short_tag("200011") == "深B"
    assert short_tag("300750") == "创业板"
    assert short_tag("600519") == "沪A"
    assert short_tag("000858") == "深A"
    assert short_tag("") == "—"
    assert short_tag("abc") == "—"


def test_board_name_matches_legacy():
    # 与 analysis_engine._board 历史输出逐一对齐
    assert board_name("600519") == "沪市主板"
    assert board_name("601088") == "沪市主板"
    assert board_name("000858") == "深市主板"
    assert board_name("002415") == "深市主板"
    assert board_name("300750") == "创业板"
    assert board_name("688981") == "科创板"
    assert board_name("830799") == "北交所"
    assert board_name("430047") == "北交所"
    assert board_name("900901") == "A股"   # B股在旧实现落到 A股 兜底
    assert board_name("999999") == "A股"


def test_delegation_consistency():
    """委托后 search_ui / analysis_engine 的封装函数与统一实现一致。"""
    from modules.search_ui import _derive_tag, _guess_market
    from modules.analysis_engine import _board
    for c in ["600519", "000858", "300750", "688981", "830799", "900901", "abc"]:
        assert _derive_tag(c) == short_tag(c)
        assert _board(c) == board_name(c)
    for c in ["600519", "000858", "300750", "899999"]:
        assert _guess_market(c) == guess_exchange(c)
