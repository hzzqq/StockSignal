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


def test_parse_technical_fields():
    """扩维：技术面/动量维度（换手率/量比/振幅/涨跌幅）应被解析为内部字段。"""
    spec = ns.parse_query("换手率大于5% 且 量比>2")
    assert any(f["field"] == "turnover" and f["op"] == "gt" and f["value"] == 5 for f in spec.filters)
    assert any(f["field"] == "volume_ratio" and f["op"] == "gt" and f["value"] == 2 for f in spec.filters)


def test_parse_exclude_board():
    """剔除/排除板块 → 落到 exclude_boards，不污染正向 boards。"""
    spec = ns.parse_query("主板 市盈率小于30 剔除创业板")
    assert "main" in spec.boards
    assert "cyb" in spec.exclude_boards
    assert "cyb" not in spec.boards


def test_parse_exclude_concept_st():
    """剔除ST → 落到 exclude_concepts（名字片段排除）。"""
    spec = ns.parse_query("剔除ST 市盈率小于20")
    assert "ST" in spec.exclude_concepts
    assert any(f["field"] == "pe" and f["op"] == "lt" and f["value"] == 20 for f in spec.filters)
    # 仅排除不应触发未理解
    assert spec.unparsed == []


def test_apply_filters_exclude_board():
    uni = [
        {"code": "300750", "name": "A", "pe": 18, "concepts": []},
        {"code": "600519", "name": "B", "pe": 18, "concepts": []},
    ]
    spec = ns.parse_query("市盈率<30 剔除创业板")
    res = ns.apply_filters(uni, spec)
    assert [r["code"] for r in res] == ["600519"], "创业板应被排除"


def test_apply_filters_exclude_concept():
    uni = [
        {"code": "600519", "name": "贵州茅台", "pe": 18, "concepts": ["白酒"]},
        {"code": "000858", "name": "五粮液", "pe": 18, "concepts": ["白酒"]},
        {"code": "300750", "name": "宁德时代", "pe": 18, "concepts": ["新能源"]},
    ]
    spec = ns.parse_query("市盈率<30 剔除白酒")
    res = ns.apply_filters(uni, spec)
    assert {r["code"] for r in res} == {"300750"}, "白酒概念应被排除"


def test_apply_filters_technical_field():
    uni = [
        {"code": "300750", "name": "A", "pe": 18, "chg_pct": 8.5, "concepts": []},
        {"code": "600519", "name": "B", "pe": 18, "chg_pct": 1.2, "concepts": []},
    ]
    spec = ns.parse_query("涨跌幅大于5%")
    res = ns.apply_filters(uni, spec)
    assert [r["code"] for r in res] == ["300750"], "技术面维度应正确过滤"


def test_parse_exclude_named_industry():
    """非 + 命名行业板块（如"非白酒板块"）→ 落到 exclude_concepts，且不得污染正向 concepts。

    修复前：命名行业不是 BOARD_ALIASES 别名，"非白酒板块" 不进排除，反而掉进 concepts 变成正向筛选。
    """
    spec = ns.parse_query("非白酒板块 流通市值大于50亿")
    assert "白酒" in spec.exclude_concepts, f"命名行业应被排除，实际：{spec.exclude_concepts}"
    assert spec.exclude_boards == [], "命名行业不应进 exclude_boards"
    assert spec.concepts == [], f"排除短语不得残留为正向概念，实际：{spec.concepts}"
    assert any(f["field"] == "float_mktcap" for f in spec.filters), "其余筛选条件不受影响"


def test_apply_filters_exclude_named_industry():
    """非白酒板块 → 白酒概念个股被排除（端到端，与"剔除白酒"等价）。"""
    uni = [
        {"code": "600519", "name": "贵州茅台", "pe": 18, "concepts": ["白酒"]},
        {"code": "000858", "name": "五粮液", "pe": 18, "concepts": ["白酒"]},
        {"code": "300750", "name": "宁德时代", "pe": 18, "concepts": ["新能源"]},
    ]
    spec = ns.parse_query("市盈率<30 非白酒板块")
    res = ns.apply_filters(uni, spec)
    assert {r["code"] for r in res} == {"300750"}, f"白酒概念应被排除，实际：{[r['code'] for r in res]}"


def test_industry_whitelist_long_name_exclude():
    """5 字以上行业名走白名单：整词排除，带/不带后缀均可，不再受通用规则 {1,5} 限制。"""
    spec = ns.parse_query("非电力设备新能源 市盈率<20")
    assert "电力设备新能源" in spec.exclude_concepts, f"7字行业应整词排除：{spec.exclude_concepts}"
    assert spec.exclude_boards == []
    assert "电力设备新能源" not in spec.concepts, "排除短语不得污染正向概念"
    assert any(f["field"] == "pe" and f["op"] == "lt" for f in spec.filters)
    # 带后缀写法等价
    spec2 = ns.parse_query("非电力设备新能源板块 市盈率<20")
    assert "电力设备新能源" in spec2.exclude_concepts
    assert "电力设备新能源" not in spec2.concepts


def test_industry_whitelist_positive_long_name():
    """7 字行业名正向筛选：白名单整词入 concepts（此前被 step5 的 2~6 字窗口漏掉）。"""
    spec = ns.parse_query("电力设备新能源 市盈率<20")
    assert "电力设备新能源" in spec.concepts, f"7字行业应整词入正向概念：{spec.concepts}"
    assert any(f["field"] == "pe" and f["op"] == "lt" for f in spec.filters)


def test_industry_whitelist_no_suffix_exclude():
    """白名单词省后缀：非白酒 → 排除白酒（此前必须写 非白酒板块）。"""
    spec = ns.parse_query("非白酒 市盈率<30")
    assert "白酒" in spec.exclude_concepts, f"省后缀排除应生效：{spec.exclude_concepts}"
    assert "白酒" not in spec.concepts
    assert any(f["field"] == "pe" and f["op"] == "lt" for f in spec.filters)


def test_industry_whitelist_prose_guard():
    """防误拆守卫：日常句「非常看好半导体板块」不得被拆成排除；半导体作为正向概念命中。"""
    spec = ns.parse_query("非常看好半导体板块 市盈率<20")
    assert spec.exclude_concepts == [], f"日常句不得误拆为排除：{spec.exclude_concepts}"
    assert "半导体" in spec.concepts, f"半导体应作为正向概念命中：{spec.concepts}"
    assert any(f["field"] == "pe" for f in spec.filters)


# ── 选股方案存档（2026-11-03）：roundtrip / 去重置顶 / 上限 / 损坏容错 / 诚实清空 ──
def test_query_presets_roundtrip(monkeypatch, tmp_path):
    """保存→读取一致，新的在前；文件缺失读 []。"""
    monkeypatch.setattr(ns, "_query_presets_path", lambda: str(tmp_path / "nl_presets.json"))
    assert ns.load_query_presets() == []
    assert ns.save_query_preset("创业板 市盈率<30") is True
    assert ns.save_query_preset("主板 换手率>5%") is True
    items = ns.load_query_presets()
    assert [it["query"] for it in items] == ["主板 换手率>5%", "创业板 市盈率<30"]
    assert all(it.get("ts") for it in items), "每条方案应带保存时间"


def test_query_presets_dedupe_moves_to_front(monkeypatch, tmp_path):
    """同文本去重且移到最前（复用 = 升温），不产生重复条目。"""
    monkeypatch.setattr(ns, "_query_presets_path", lambda: str(tmp_path / "nl_presets.json"))
    ns.save_query_preset("查询A")
    ns.save_query_preset("查询B")
    ns.save_query_preset("查询A")
    items = ns.load_query_presets()
    assert [it["query"] for it in items] == ["查询A", "查询B"], "去重并置顶"


def test_query_presets_cap_truncates(monkeypatch, tmp_path):
    """超过上限截断到 _QUERY_PRESETS_MAX，保留最新。"""
    monkeypatch.setattr(ns, "_query_presets_path", lambda: str(tmp_path / "nl_presets.json"))
    for i in range(ns._QUERY_PRESETS_MAX + 5):
        assert ns.save_query_preset(f"查询{i}") is True
    items = ns.load_query_presets(limit=0)
    assert len(items) == ns._QUERY_PRESETS_MAX
    assert items[0]["query"] == f"查询{ns._QUERY_PRESETS_MAX + 4}"


def test_query_presets_corrupt_and_empty_rejected(monkeypatch, tmp_path):
    """损坏文件读 [] 且可重建；空/空白查询拒绝写入（不臆造）。"""
    p = tmp_path / "nl_presets.json"
    p.write_text("{bad-json", encoding="utf-8")
    monkeypatch.setattr(ns, "_query_presets_path", lambda: str(p))
    assert ns.load_query_presets() == []
    assert ns.save_query_preset("重建后可写") is True
    assert ns.load_query_presets()[0]["query"] == "重建后可写"
    assert ns.save_query_preset("   ") is False
    assert ns.save_query_preset("") is False


def test_query_presets_clear_honest(monkeypatch, tmp_path):
    """清空返回真实条数：缺失 0、有 2 清 2、清后读 []。"""
    monkeypatch.setattr(ns, "_query_presets_path", lambda: str(tmp_path / "nl_presets.json"))
    assert ns.clear_query_presets() == 0
    ns.save_query_preset("A")
    ns.save_query_preset("B")
    assert ns.clear_query_presets() == 2
    assert ns.load_query_presets() == []
