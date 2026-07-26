"""R1/R2/R3/R5/R6：backend.services.stock_service 纯逻辑辅助函数的离线单测。

仅覆盖无 DB / 无网络依赖的纯函数：
  - normalize_symbol   代码 -> 带市场前缀的完整符号
  - filter_by_market   按市场过滤（None/空/缺键安全）
  - compute_match_score 名称/拼音匹配打分（None 安全）
  - rank_and_dedup     去重 + 排序 + 截断（None/空/缺键安全）

不构造任何 Stock / db 对象，不涉及任何网络或数据库调用。
"""
from backend.services.stock_service import (
    normalize_symbol,
    filter_by_market,
    compute_match_score,
    rank_and_dedup,
)


# --------------------------------------------------------------------------- normalize_symbol
def test_normalize_symbol_shanghai():
    assert normalize_symbol("600519") == "sh600519"
    assert normalize_symbol("688001") == "sh688001"


def test_normalize_symbol_shenzhen():
    assert normalize_symbol("000001") == "sz000001"
    assert normalize_symbol("300750") == "sz300750"


def test_normalize_symbol_beijing():
    assert normalize_symbol("830799") == "bj830799"
    assert normalize_symbol("400000") == "bj400000"


def test_normalize_symbol_already_prefixed():
    assert normalize_symbol("SH600519") == "sh600519"
    assert normalize_symbol("sz000001") == "sz000001"


def test_normalize_symbol_empty_and_none():
    assert normalize_symbol(None) == ""
    assert normalize_symbol("") == ""
    assert normalize_symbol("   ") == ""
    assert normalize_symbol(600519) == "sh600519"  # 非字符串也安全


# --------------------------------------------------------------------------- filter_by_market
def test_filter_by_market_empty():
    assert filter_by_market([], "sh") == []
    assert filter_by_market(None, "sh") == []


def test_filter_by_market_no_market_returns_all():
    items = [{"code": "600519", "market": "sh"}, {"code": "000001", "market": "sz"}]
    assert filter_by_market(items, "") == items
    assert filter_by_market(items, None) == items


def test_filter_by_market_normal():
    items = [
        {"code": "600519", "market": "sh"},
        {"code": "000001", "market": "sz"},
        {"code": "688001", "market": "sh"},
    ]
    out = filter_by_market(items, "sh")
    assert [i["code"] for i in out] == ["600519", "688001"]


def test_filter_by_market_missing_key_safe():
    items = [{"code": "600519"}, {"code": "000001", "market": "sz"}]
    # 缺 'market' 键的记录不会匹配任何具体市场，且不抛 KeyError
    assert filter_by_market(items, "sz") == [{"code": "000001", "market": "sz"}]


# --------------------------------------------------------------------------- compute_match_score
def test_compute_match_score_name_exact():
    assert compute_match_score("贵州茅台", "", "", "贵州茅台") == 900


def test_compute_match_score_name_prefix():
    assert compute_match_score("贵州茅台酒", "", "", "贵州茅台") == 700


def test_compute_match_score_pinyin_initials():
    assert compute_match_score("", "gzm", "", "gzm") == 600
    assert compute_match_score("", "gzm", "", "gz") == 550


def test_compute_match_score_pinyin_full():
    assert compute_match_score("", "", "guizhoumaotai", "guizhoumaotai") == 500


def test_compute_match_score_contains():
    assert compute_match_score("xx贵州yy", "", "", "贵州") == 400
    assert compute_match_score("", "xxgzm", "", "gzm") == 300


def test_compute_match_score_single_char_prefix_uses_prefix_score():
    # 单字查询命中名称前缀时，优先级表规定取 700（首字模糊 100 分支在其后，
    # 按原逻辑不可达，此处仅验证原行为未被改变）。
    assert compute_match_score("茅 xyz", "", "", "茅") == 700


def test_compute_match_score_no_match():
    assert compute_match_score("贵州茅台", "", "", "五粮液") == 0


def test_compute_match_score_none_and_empty_safe():
    assert compute_match_score(None, None, None, None) == 0
    assert compute_match_score("贵州茅台", None, None, "") == 0
    assert compute_match_score(None, None, None, "茅台") == 0
    # None 字段不抛异常，视为空串
    assert compute_match_score(None, "gzm", None, "gzm") == 600


# --------------------------------------------------------------------------- rank_and_dedup
def test_rank_and_dedup_empty():
    assert rank_and_dedup([]) == []
    assert rank_and_dedup(None) == []


def test_rank_and_dedup_dedup_keeps_highest_score():
    results = [
        {"code": "600519", "score": 400, "name": "a"},
        {"code": "600519", "score": 900, "name": "b"},
        {"code": "000001", "score": 700, "name": "c"},
    ]
    out = rank_and_dedup(results)
    codes = [i["code"] for i in out]
    assert codes.count("600519") == 1
    top = [i for i in out if i["code"] == "600519"][0]
    assert top["score"] == 900 and top["name"] == "b"


def test_rank_and_dedup_sorted_by_score_desc():
    results = [
        {"code": "a", "score": 100},
        {"code": "b", "score": 900},
        {"code": "c", "score": 500},
    ]
    out = rank_and_dedup(results)
    scores = [i["score"] for i in out]
    assert scores == [900, 500, 100]


def test_rank_and_dedup_respects_limit():
    results = [{"code": str(i), "score": i} for i in range(20)]
    out = rank_and_dedup(results, limit=5)
    assert len(out) == 5


def test_rank_and_dedup_skips_missing_code_and_score():
    results = [
        {"score": 900},                 # 缺 code -> 跳过
        {"code": "600519", "score": 100},
        {"code": None, "score": 999},   # code 为 None -> 跳过
        None,                           # 非 dict -> 跳过
    ]
    out = rank_and_dedup(results)
    assert [i["code"] for i in out] == ["600519"]


def test_rank_and_dedup_missing_score_defaults_zero():
    results = [
        {"code": "a"},        # 缺 score -> 视为 0
        {"code": "b", "score": 0},
    ]
    out = rank_and_dedup(results, limit=1)
    # 两条 score 都视为 0，按 code 升序截断取 1 条
    assert len(out) == 1
