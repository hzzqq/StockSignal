# -*- coding: utf-8 -*-
"""tests/test_event_factor_e2e.py — 五源全链路「诚实降级」端到端守卫（③）。

用完全离线的 stub 把五个真实源全部打空，验证：
1. get_event_factor 返回 available=False，reason 如实列出五源均已尝试；
2. 全程不返回任何合成/占位分数（无 score / signal / rank 键）；
3. include_macro=True 且宏观取数失败时，macro 也如实 unavailable，绝不塞假评分；
4. 五源兜底序：逐源放行验证优先级（P1 > 新闻 > 龙虎榜 > 主表 > 语音）；
5. 任一源抛异常不阻断后续源（降级链继续），最终仍诚实 available=False。
诚实红线：零网络、零真实数据文件、零合成造数，全部 monkeypatch 隔离。
"""
import pytest

from modules import event_factor as ef


class _EmptyP1:
    source_dirs = ["<e2e>"]

    def available_models(self):
        return ["ev"]

    def top_long(self, *a, **k):
        return []

    def top_short(self, *a, **k):
        return []

    def daily_df(self, *a, **k):
        return None

    def load(self, *a, **k):
        return {}


_UNAVAILABLE = {"available": False, "reason": "<stub 无数据>"}


@pytest.fixture
def all_empty(monkeypatch):
    """五源全部打空（P1 用空 loader，其余四源 monkeypatch 成 unavailable）。"""
    monkeypatch.setattr(ef, "news_event_signal", lambda *a, **k: dict(_UNAVAILABLE))
    monkeypatch.setattr(ef, "lhb_event_signal", lambda *a, **k: dict(_UNAVAILABLE))
    monkeypatch.setattr(ef, "tracked_event_signal", lambda *a, **k: dict(_UNAVAILABLE))
    monkeypatch.setattr("modules.voice_event.load_voice_events", lambda *a, **k: [])
    monkeypatch.setattr("modules.macro_data.global_regime_score", lambda: None)


def test_all_five_sources_empty_is_honest_unavailable(all_empty):
    """五源全空 → available=False，且绝不返回任何合成分数键。"""
    r = ef.get_event_factor("601088", loader=_EmptyP1(), voice_user="alice",
                            include_macro=True)
    assert r["available"] is False
    assert "score" not in r and "rank" not in r and "signal" not in r
    # reason 如实覆盖四个兜底方向（不谎称「已查全部真实源」）
    for kw in ("新闻", "龙虎榜", "本地事件主表", "语音转写"):
        assert kw in r["reason"]
    assert r["macro"]["available"] is False
    assert "regime_score" not in r["macro"]


def test_default_path_never_touches_macro_or_voice(all_empty, monkeypatch):
    """默认（无 voice_user / include_macro）既不读语音桶也不取宏观（零网络）。"""
    seen = {"voice": 0, "macro": 0}

    def v(*a, **k):
        seen["voice"] += 1
        return []

    def m():
        seen["macro"] += 1
        return None

    monkeypatch.setattr("modules.voice_event.load_voice_events", v)
    monkeypatch.setattr("modules.macro_data.global_regime_score", m)
    r = ef.get_event_factor("601088", loader=_EmptyP1())
    assert r["available"] is False
    assert seen == {"voice": 0, "macro": 0}
    assert "macro" not in r


@pytest.mark.parametrize("winner,source", [
    ("news", "eastmoney-news"),
    ("lhb", "eastmoney-lhb"),
    ("tracked", "tracked-events"),
    ("voice", "voice-event"),
])
def test_fallback_priority_each_source_can_win(all_empty, monkeypatch, winner, source):
    """兜底序：让某一源命中，其后的源不再被调用；命中源如实返回。"""
    hit = {"available": True, "score": 60.0, "rank": 0.6,
           "signal": "看多", "source": source}
    order = []

    def make(name):
        def f(*a, **k):
            order.append(name)
            return dict(hit) if name == winner else dict(_UNAVAILABLE)
        return f

    monkeypatch.setattr(ef, "news_event_signal", make("news"))
    monkeypatch.setattr(ef, "lhb_event_signal", make("lhb"))
    monkeypatch.setattr(ef, "tracked_event_signal", make("tracked"))
    # 语音源：命中则给一条近期利好
    from datetime import datetime, timedelta
    if winner == "voice":
        items = [{"ts": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                  "text": "公司中标大额合同", "sentiment": "利好", "urgency": "笼统"}]
    else:
        items = []

    def v(*a, **k):
        order.append("voice")
        return items

    monkeypatch.setattr("modules.voice_event.load_voice_events", v)
    expected_order = ["news", "lhb", "tracked", "voice"]
    r = ef.get_event_factor("601088", loader=_EmptyP1(), voice_user="alice")
    assert r["available"] is True
    assert r["source"] == source
    assert order == expected_order[:expected_order.index(winner) + 1], (
        f"命中 {winner} 后不应继续调用后续源：{order}"
    )


def test_one_source_exception_does_not_break_chain(all_empty, monkeypatch):
    """任一源抛异常 → 记录告警并继续后续源，最终诚实降级而非崩或造数。"""
    def boom(*a, **k):
        raise RuntimeError("source down")

    monkeypatch.setattr(ef, "news_event_signal", boom)
    monkeypatch.setattr(ef, "lhb_event_signal", boom)
    monkeypatch.setattr(ef, "tracked_event_signal", boom)
    monkeypatch.setattr("modules.voice_event.load_voice_events", boom)
    r = ef.get_event_factor("601088", loader=_EmptyP1(), voice_user="alice")
    assert r["available"] is False
    assert "score" not in r


def test_macro_exception_does_not_break_event_factor(all_empty, monkeypatch):
    """宏观取数异常被隔离在 macro 字段，不影响事件因子主返回值。"""
    def boom():
        raise RuntimeError("akshare down")

    monkeypatch.setattr("modules.macro_data.global_regime_score", boom)
    r = ef.get_event_factor("601088", loader=_EmptyP1(), include_macro=True)
    assert r["available"] is False
    assert r["macro"]["available"] is False
    assert "取数失败" in r["macro"]["reason"]
