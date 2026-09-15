# -*- coding: utf-8 -*-
"""自然语言选股解析器（仿 i问财，取长补短）回归测试。

锁死的核心契约：
- parse_query 是纯函数、确定性、不触网；把口语解析成结构化条件。
- 填充词（"的票""我想"）不得被当概念误杀候选池（静默错误=最危险）。
- apply_filters 取不到字段→不匹配（不臆造通过）；概念不匹配→诚实排除（可返回空集）。
- 排序/数量/板块前缀判定正确。

全部离线、确定性，不依赖 akshare/网络。
"""
import modules.nl_screen as ns


def test_parse_board_and_filters_and_sort_and_limit():
    spec = ns.parse_query("创业板 市盈率小于30 且 营收增长大于20% 的票，按营收增长排序，取前10")
    assert "cyb" in spec.boards
    assert any(f["field"] == "pe" and f["op"] == "lt" and f["value"] == 30 for f in spec.filters)
    assert any(f["field"] == "rev_growth" and f["op"] == "gt" and f["value"] == 20 for f in spec.filters)
    assert spec.sort == "rev_growth" and spec.sort_dir == "desc"
    assert spec.limit == 10


def test_parse_filler_not_treated_as_concept():
    """「的票」这类填充词必须被剔除，不能误当成概念把候选池清空。"""
    spec = ns.parse_query("创业板 市盈率小于30 且 营收增长大于20% 的票")
    assert "的票" not in spec.concepts, "填充词被误当概念"
    assert spec.concepts == [], f"不应残留概念，实际：{spec.concepts}"


def test_parse_number_units():
    spec = ns.parse_query("总市值小于100亿 且 净利润增长>30%")
    mkt = next(f for f in spec.filters if f["field"] == "mktcap")
    prof = next(f for f in spec.filters if f["field"] == "profit_growth")
    assert mkt["value"] == 1e10, "100亿 应展开为 1e10（亿元单位）"
    assert prof["value"] == 30.0, "30% 脱去百分号"


def test_parse_stopword_concepts_dropped():
    """纯口语填充（"我想找"）不产生伪概念。"""
    spec = ns.parse_query("我想找市盈率低于20的")
    assert "我想找" not in spec.concepts
    assert any(f["field"] == "pe" and f["op"] == "lt" and f["value"] == 20 for f in spec.filters)


def test_apply_filters_board_prefix_excludes_wrong_board():
    uni = [
        {"code": "300750", "name": "A", "pe": 25, "rev_growth": 25, "concepts": ["新能源"]},
        {"code": "600519", "name": "B", "pe": 18, "rev_growth": 30, "concepts": ["白酒"]},
    ]
    spec = ns.parse_query("主板 市盈率<30")
    res = ns.apply_filters(uni, spec)
    # 300xxx 非主板 → 排除；600519 是主板且 pe<30 → 命中
    assert [r["code"] for r in res] == ["600519"], res


def test_apply_filters_concept_honest_empty():
    """指定概念但候选池无人匹配 → 诚实返回空集，绝不编造。"""
    uni = [{"code": "600519", "name": "B", "pe": 18, "concepts": ["白酒"]}]
    spec = ns.parse_query("新能源 市盈率<50")
    res = ns.apply_filters(uni, spec)
    assert res == [], "概念不匹配应返回空（诚实），而非塞入无关票"


def test_apply_filters_sort_desc_and_limit():
    uni = [
        {"code": "300750", "name": "A", "pe": 25, "rev_growth": 10, "concepts": []},
        {"code": "300014", "name": "C", "pe": 25, "rev_growth": 40, "concepts": []},
        {"code": "300999", "name": "D", "pe": 25, "rev_growth": 25, "concepts": []},
    ]
    spec = ns.parse_query("创业板 市盈率<60 且 营收增长>5% 按营收增长排序 取前2")
    res = ns.apply_filters(uni, spec)
    assert [r["code"] for r in res] == ["300014", "300999"], res
    assert len(res) == 2


def test_apply_filters_missing_field_not_matched():
    """记录缺某字段 → 该过滤条件不匹配（不臆造通过）。"""
    uni = [{"code": "300750", "name": "A", "pe": 25, "concepts": []}]  # 无 rev_growth
    spec = ns.parse_query("营收增长>20%")
    res = ns.apply_filters(uni, spec)
    assert res == [], "缺字段应不匹配"
