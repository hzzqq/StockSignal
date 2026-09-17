# -*- coding: utf-8 -*-
"""tests/test_event_graph.py — H3 事件传导图谱测试（纯计算，离线）。"""
import json

from modules import event_graph as eg


# ─────────────────────────── 方向判定 ───────────────────────────
def test_direction_bullish_and_bearish():
    # 词取自项目真实词库 modules._news_io.POSITIVE_WORDS / NEGATIVE_WORDS
    assert eg.event_direction("公司获得大单，产品涨价") == eg.BULLISH
    assert eg.event_direction("公司因违规被立案调查") == eg.BEARISH


def test_direction_neutral_on_tie_or_empty():
    assert eg.event_direction("公司召开股东大会") == eg.NEUTRAL
    assert eg.event_direction("") == eg.NEUTRAL
    assert eg.event_direction(None) == eg.NEUTRAL


def test_direction_tie_is_neutral_not_guessed():
    """利好词与利空词各 1 个 → 中性（不硬猜方向）。"""
    assert eg.event_direction("产品涨价后被处罚") == eg.NEUTRAL


# ─────────────────────────── 概念匹配 ───────────────────────────
def test_match_concepts_longest_first_no_double_count():
    names = ["半导体", "半导体设备", "芯片"]
    got = eg.match_concepts("半导体设备国产化加速", names)
    assert "半导体设备" in got
    assert "半导体" not in got        # 长串优先，同一片段不重复计


def test_match_concepts_multiple():
    got = eg.match_concepts("芯片与光伏同时受益", ["芯片", "光伏", "军工"])
    assert set(got) == {"芯片", "光伏"}


def test_match_concepts_ignores_single_char_and_empty():
    assert eg.match_concepts("", ["芯片"]) == []
    assert eg.match_concepts("芯片", []) == []
    assert eg.match_concepts("芯", ["芯"]) == []      # 单字概念不算命中


# ─────────────────────────── 传导编排 ───────────────────────────
_INDEX = {
    "芯片": [{"code": "600001", "name": "中芯国际"}, {"code": "600002", "name": "北方华创"}],
    "光伏": [{"code": "600003", "name": "隆基绿能"}],
}


def test_build_transmission_none_index_is_unavailable():
    r = eg.build_transmission(["芯片涨价"], {})
    assert r["status"] == "unavailable"
    assert r["entries"] == []


def test_build_transmission_no_titles_is_unavailable():
    assert eg.build_transmission([], _INDEX)["status"] == "unavailable"


def test_build_transmission_direct_hit_ranks_higher():
    titles = [("中芯国际芯片获得大单，行业景气回升", "2026-09-17")]
    r = eg.build_transmission(titles, _INDEX)
    assert r["status"] == "ok"
    top = r["entries"][0]
    assert top["code"] == "600001"
    assert top["score"] == 3              # 概念命中 + 个股点名
    assert top["direct"] is True
    assert top["direction"] == eg.BULLISH
    # 未点名的同概念股分数更低
    other = next(e for e in r["entries"] if e["code"] == "600002")
    assert other["score"] == 1 and other["direct"] is False


def test_build_transmission_accumulates_across_titles():
    titles = [("芯片板块大涨", ""), ("芯片再获政策支持", "")]
    r = eg.build_transmission(titles, _INDEX)
    a = next(e for e in r["entries"] if e["code"] == "600001")
    assert a["score"] == 2                # 两条标题各 +1
    assert len(a["evidence"]) == 2


def test_build_transmission_short_name_not_treated_as_direct_hit():
    """过短的个股名（<3 字）不做直接点名判定，避免子串假命中。"""
    idx = {"芯片": [{"code": "600009", "name": "东方"}]}
    r = eg.build_transmission([("东方财富发布芯片研报", "")], idx)
    e = r["entries"][0] if r["entries"] else None
    assert e is not None
    assert e["direct"] is False and e["score"] == 1


def test_build_transmission_reports_concepts_without_members():
    idx = {"芯片": [{"code": "1", "name": "甲股份"}], "光伏": []}
    r = eg.build_transmission([("芯片与光伏齐涨", "")], idx)
    assert "光伏" in r["members_unavailable"]
    assert "芯片" in r["concepts_hit"]


def test_build_transmission_no_concept_hit_is_empty_not_ok():
    r = eg.build_transmission([("公司发布年度报告", "")], _INDEX)
    assert r["status"] == "empty"
    assert "没有命中" in r["reason"]


def test_build_transmission_always_carries_basis_and_disclaimer():
    r = eg.build_transmission([("芯片涨价", "")], _INDEX)
    assert r["basis"] and "共现" in r["basis"]
    assert r["disclaimer"] and "不代表" in r["disclaimer"]


def test_build_transmission_accepts_plain_string_titles():
    r = eg.build_transmission(["芯片涨价"], _INDEX)
    assert r["status"] == "ok" and r["n_titles"] == 1


# ─────────────────────────── 取数层 ───────────────────────────
def test_fetch_concept_names_none_without_fetcher(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "modules.fetcher", None)
    assert eg.fetch_concept_names() is None
    assert eg.fetch_concept_members("芯片") is None


def test_build_index_for_titles_only_fetches_hit_concepts(monkeypatch):
    calls = []

    def _names():
        return ["芯片", "光伏", "军工", "白酒"]

    def _members(c):
        calls.append(c)
        return [{"code": "600001", "name": "中芯国际"}]

    monkeypatch.setattr(eg, "fetch_concept_names", _names)
    idx = eg.build_index_for_titles([("芯片板块大涨", "")], fetch_members=_members)
    assert list(idx.keys()) == ["芯片"]
    assert calls == ["芯片"]           # 只拉了命中的概念，不是全部 4 个


def test_build_index_returns_empty_when_names_unavailable(monkeypatch):
    monkeypatch.setattr(eg, "fetch_concept_names", lambda: None)
    assert eg.build_index_for_titles([("芯片", "")], fetch_members=lambda c: []) == {}

def test_word_lists_prefer_project_lexicon():
    """有项目词库时必须用它（而非内置兜底），保证与全站情绪口径一致。"""
    pos, neg = eg._word_lists()
    assert "获得大单" in pos and "处罚" in neg
    assert len(pos) > 50 and len(neg) > 50

# ─────────────────────────── 展示层（配色 / 截断，纯函数） ───────────────────────────
def test_dir_color_follows_a_share_convention():
    """A 股习惯：利好=红、利空=绿、中性=灰（写反即为配色回退，本断言锁死）。"""
    assert eg.dir_color(eg.BULLISH) == "#dc2626"
    assert eg.dir_color(eg.BEARISH) == "#16a34a"
    assert eg.dir_color(eg.NEUTRAL) == "#94a3b8"
    assert eg.dir_color("未知方向") == "#94a3b8"


def test_display_rows_maps_fields_and_color():
    res = eg.build_transmission([("中芯国际芯片获得大单", "2026-09-17")], _INDEX)
    rows = eg.display_rows(res)
    assert rows and rows[0]["code"] == "600001"
    assert rows[0]["name"] == "中芯国际"
    assert rows[0]["direct"] is True
    assert rows[0]["dir_color"] == "#dc2626"          # 利好 → 红
    assert "芯片" in rows[0]["concepts"]
    assert rows[0]["evidence"]


def test_display_rows_truncates_evidence_and_respects_limit():
    res = {"entries": [{"code": f"{i:06d}", "name": f"股{i}", "score": 1,
                        "direction": eg.NEUTRAL, "concepts": [],
                        "evidence": ["标题" * 200], "direct": False}
                       for i in range(50)]}
    rows = eg.display_rows(res, limit=5, evidence_len=10)
    assert len(rows) == 5
    assert len(rows[0]["evidence"]) == 10
    assert rows[0]["concepts"] == "—"                  # 空概念给占位，不留空串


def test_display_rows_survives_missing_and_bad_entries():
    """缺字段 / 非 dict 行不得抛异常，也不得凭空造标的。"""
    res = {"entries": [None, "坏行", {"code": "600001"}, {}]}
    rows = eg.display_rows(res)
    assert [r["code"] for r in rows] == ["600001", ""]  # 只留 dict 行，不编造代码
    assert rows[0]["name"] == "600001"                  # 无名时回退到代码
    assert rows[0]["direction"] == eg.NEUTRAL
    assert rows[0]["evidence"] == ""
    assert eg.display_rows(None) == []
    assert eg.display_rows({}) == []


def test_display_rows_does_not_mutate_input():
    """展示层不得改动上游结果（防「渲染顺手改分数」这类静默失真）。"""
    res = eg.build_transmission([("芯片涨价", "")], _INDEX)
    before = json.loads(json.dumps(res, ensure_ascii=False, default=str))
    eg.display_rows(res)
    assert json.loads(json.dumps(res, ensure_ascii=False, default=str)) == before
