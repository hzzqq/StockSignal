# -*- coding: utf-8 -*-
"""
tests/test_event_annotation.py
==============================
T-332 R9「A4 标注层」守卫：事件因子输出补 hard_logic / horizon 两字段。

契约（spec 冻结 2026-10-26，benchmark 采纳清单 R9）：

- ``annotate_hard_logic(texts)`` 纯函数：对事件文本（如新闻标题）做
  「硬逻辑（产业/政策/供需可验证事件）vs 题材炒作（传闻/概念追逐）」分类：
  * 词表命中计数：硬逻辑词 > 题材词 → ``hard_logic="硬逻辑"``；反之 ``"题材炒作"``；
  * 平票 / 双零 / 空文本 → ``status="unavailable"``（不编造分类）；
  * 证据字段 ``evidence`` 返回命中词（≤5 个，可溯源）。
- ``annotate_horizon(model_horizon)`` 纯函数：把 P1 信号 json 自带的 ``horizon``
  （交易日数）如实映射为兑现窗口标签（10→"1-2 周（10 交易日）"、20→"波段…"、
  1→"当天"、3→"1-3 天"、5→"1 周"）；非 int / 未知值 → ``status="unavailable"``
  （不默认、不编造窗口）。
- 接线（additive-only，不动既有字段）：
  * ``get_event_factor``：P1 路径输出带 ``horizon``（ok，源自信号 json）与
    ``hard_logic``（unavailable：P1 信号路径无事件文本，如实说明）；
  * ``event_driven_long_list``：每行带 ``horizon`` + ``hard_logic``（同上）；
  * ``news_event_signal``：新闻标题喂 ``annotate_hard_logic``（真实文本可分类）。

mutation：词表分类被短路成恒「硬逻辑」/ 未知 horizon 被编造 / 接线丢字段 → 对应用例变红。
"""
import inspect

from modules import event_factor as ef


class TestAnnotateHardLogic:
    def test_hard_logic_positive_with_evidence(self):
        r = ef.annotate_hard_logic(["公司中标海外大单", "三季度业绩预增"])
        assert r["status"] == "ok"
        assert r["hard_logic"] == "硬逻辑"
        assert "中标" in r["evidence"] and "预增" in r["evidence"]

    def test_speculation_positive(self):
        r = ef.annotate_hard_logic(["市场传闻公司将蹭热点概念"])
        assert r["status"] == "ok"
        assert r["hard_logic"] == "题材炒作"
        assert r["evidence"], "题材判定也须给证据词"

    def test_tie_or_empty_unavailable(self):
        tie = ef.annotate_hard_logic(["公司中标项目，另有市场传闻终止"])  # 中标 vs 传闻 平票
        # 平票或无命中都必须 unavailable，绝不编造
        for r in (tie, ef.annotate_hard_logic([]), ef.annotate_hard_logic(["", None])):
            assert r["status"] == "unavailable"
            assert r["hard_logic"] is None


class TestAnnotateHorizon:
    def test_known_mappings(self):
        assert ef.annotate_horizon(10)["horizon"] == "1-2 周（10 交易日）"
        assert ef.annotate_horizon(20)["horizon"] == "波段（20 交易日）"
        assert ef.annotate_horizon(1)["horizon"] == "当天"
        assert ef.annotate_horizon(3)["horizon"] == "1-3 天"
        assert ef.annotate_horizon(5)["horizon"] == "1 周"

    def test_unknown_or_bad_unavailable(self):
        for bad in (None, 7, "10", True, 10.5):
            r = ef.annotate_horizon(bad)
            assert r["status"] == "unavailable", f"输入 {bad!r} 应 unavailable"
            assert r["horizon"] is None, f"输入 {bad!r} 不得编造窗口"


class _FakeLoader:
    """注入用假加载器：快路径命中 top_long，horizon=10。"""

    def available_models(self):
        return ["ev"]

    def top_long(self, model, n=None):
        return [{"symbol": "sh600000", "pred": 0.03, "rank": 0.99}]

    def top_short(self, model, n=None):
        return []

    def load(self, model):
        return {"horizon": 10, "latest_date": "2026-09-17", "top_long": self.top_long(model)}


class TestWiring:
    def test_get_event_factor_carries_annotation(self):
        r = ef.get_event_factor("sh600000", model="ev", loader=_FakeLoader())
        assert r["available"] is True
        assert r["horizon"]["status"] == "ok"
        assert r["horizon"]["model_horizon"] == 10
        assert r["hard_logic"]["status"] == "unavailable"
        assert r["hard_logic"]["reason"], "unavailable 必须给原因"

    def test_event_driven_long_list_rows_carried(self):
        rows = ef.event_driven_long_list(top_n=5, model="ev", loader=_FakeLoader())
        assert rows, "假 loader 应产出非空榜"
        for row in rows:
            assert row["horizon"]["status"] == "ok"
            assert row["horizon"]["horizon"] == "1-2 周（10 交易日）"
            assert row["hard_logic"]["status"] == "unavailable"

    def test_news_signal_annotates_titles(self):
        src = inspect.getsource(ef.news_event_signal)
        assert "annotate_hard_logic" in src, "新闻路径未接 hard_logic 标注"
