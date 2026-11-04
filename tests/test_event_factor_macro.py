# -*- coding: utf-8 -*-
"""tests/test_event_factor_macro.py — ② 全球宏观上下文守卫。

锁死宏观耦合的诚实行为：
1. 有数据 → available=True，regime_score/liquidity/components/dates/date 齐备；
2. date 取各分项**最旧**真实数据日，绝不用 now() 冒充；
3. liquidity 为透明确定性阈值（>=60 宽松 / <=40 收紧 / 其余中性），非模型生成；
4. 取不到（None）/ 取数异常 → available=False，绝不填充合成值；
5. include_macro 默认 False → 返回值不含 macro 键，且完全不触发宏观取数（向后兼容）；
6. include_macro=True → 附加 macro，但**绝不改事件因子 score**（未回测耦合红线）。
诚实红线：本文件任何用例不得依赖网络（monkeypatch 隔离 global_regime_score）。
"""
import pytest

from modules.event_factor import get_event_factor, macro_event_context


def _reg(score=72, dates=None):
    if dates is None:
        dates = {"dxy": "2026-11-01", "us_treasury_10y": "2026-10-28",
                 "us_cpi": "2026-10-15", "usd_cny": "2026-11-02"}
    return {
        "score": score,
        "sub": {"dxy": 60.0, "us_treasury_10y": 70.0},
        "parts": {"dxy": 97.0, "us_treasury_10y": 3.6,
                  "us_cpi": 2.4, "usd_cny": 7.05},
        "yield_curve": 0.4,
        "cn_us_spread": -1.2,
        "dates": dates,
    }


def _patch_reg(monkeypatch, value, seen=None):
    def fake():
        if seen is not None:
            seen.append(1)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr("modules.macro_data.global_regime_score", fake)


class _HitLoader:
    """P1 快路径直接命中，避开后续所有兜底源（不触网）。"""
    source_dirs = ["<test>"]

    def available_models(self):
        return ["ev"]

    def top_long(self, *a, **k):
        return [{"symbol": "601088", "pred": 0.031, "rank": 0.88}]

    def top_short(self, *a, **k):
        return []

    def daily_df(self, *a, **k):
        return None

    def load(self, *a, **k):
        return {"horizon": 10}


# ── 1. 有数据 ──────────────────────────────────────────────────────────────
def test_available_context_full(monkeypatch):
    _patch_reg(monkeypatch, _reg())
    r = macro_event_context()
    assert r["available"] is True
    assert r["regime_score"] == 72
    assert r["liquidity"] == "宽松"
    assert r["source"] == "akshare-macro_data"
    assert r["components"]["dxy"] == 97.0
    assert r["yield_curve"] == 0.4
    assert r["cn_us_spread"] == -1.2
    assert "确定性规则" in r["note"]


# ── 2. date = 最旧真实数据日，非 now() ──────────────────────────────────────
def test_date_is_oldest_real_data_day(monkeypatch):
    _patch_reg(monkeypatch, _reg())
    r = macro_event_context()
    assert r["date"] == "2026-10-15", "整体时效须取最旧分项数据日"
    assert r["dates"]["dxy"] == "2026-11-01"


def test_no_dates_means_none_not_now(monkeypatch):
    """全部分项无日期 → date=None，绝不拿当前时间冒充数据日。"""
    _patch_reg(monkeypatch, _reg(dates={}))
    assert macro_event_context()["date"] is None


# ── 3. liquidity 透明阈值 ───────────────────────────────────────────────────
@pytest.mark.parametrize("score,expect", [(60, "宽松"), (39, "收紧"), (50, "中性")])
def test_liquidity_thresholds(monkeypatch, score, expect):
    _patch_reg(monkeypatch, _reg(score=score))
    assert macro_event_context()["liquidity"] == expect


# ── 4. 取不到 / 异常 → 诚实降级 ─────────────────────────────────────────────
def test_none_returns_unavailable(monkeypatch):
    _patch_reg(monkeypatch, None)
    r = macro_event_context()
    assert r["available"] is False
    assert "不做合成填充" in r["reason"]
    assert "regime_score" not in r


def test_exception_returns_unavailable(monkeypatch):
    _patch_reg(monkeypatch, RuntimeError("akshare down"))
    r = macro_event_context()
    assert r["available"] is False
    assert "取数失败" in r["reason"]


# ── 5. include_macro 默认关闭（向后兼容 + 不触网）────────────────────────────
def test_default_does_not_attach_or_fetch_macro(monkeypatch):
    seen = []
    _patch_reg(monkeypatch, _reg(), seen)
    r = get_event_factor("601088", loader=_HitLoader())
    assert r["available"] is True
    assert "macro" not in r, "默认不得附加 macro 键"
    assert seen == [], "默认不得触发宏观取数"


# ── 6. include_macro=True 只加上下文、不改 score ─────────────────────────────
def test_include_macro_attaches_without_changing_score(monkeypatch):
    _patch_reg(monkeypatch, _reg())
    base = get_event_factor("601088", loader=_HitLoader())
    with_macro = get_event_factor("601088", loader=_HitLoader(), include_macro=True)
    assert with_macro["macro"]["available"] is True
    assert with_macro["macro"]["regime_score"] == 72
    # 宏观上下文绝不参与事件因子评分
    assert with_macro["score"] == base["score"]
    assert with_macro["signal"] == base["signal"]
    assert with_macro["source"] == base["source"]


def test_include_macro_unavailable_is_none_like_not_fabricated(monkeypatch):
    """宏观取不到时 macro 字段如实标 unavailable，绝不塞一个假评分。"""
    _patch_reg(monkeypatch, None)
    r = get_event_factor("601088", loader=_HitLoader(), include_macro=True)
    assert r["macro"]["available"] is False
    assert "regime_score" not in r["macro"]
