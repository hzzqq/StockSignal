"""事件因子适配器单元测试（离线、零网络）。

验证 get_event_factor 仅返回真实信号、取不到时优雅降级（绝不返回合成/假值）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules import event_factor as _ef
from modules.p1_signal import P1SignalLoader


@pytest.fixture
def sig_dir(tmp_path: Path) -> Path:
    d = tmp_path / "signals"
    d.mkdir()
    payload = {
        "model": "ev", "latest_date": "2026-08-14", "horizon": 10,
        "top_long": [
            {"symbol": "sh600869", "pred": 0.0298, "rank": 1.0},
            {"symbol": "sh600001", "pred": 0.0100, "rank": 0.9},
        ],
        "top_short": [{"symbol": "sh603118", "pred": -0.0545, "rank": 0.0007}],
        "daily": [
            {"date": "2026-08-14", "symbol": "sh600000", "score": 0.021, "signal": "看多"},
            {"date": "2026-08-13", "symbol": "sh600000", "score": -0.005, "signal": "中性"},
        ],
    }
    (d / "signal_ev_h10.json").write_text(json.dumps(payload), encoding="utf-8")
    return d


@pytest.fixture
def loader(sig_dir: Path) -> P1SignalLoader:
    return P1SignalLoader(source_dirs=[str(sig_dir)], ttl=10_000)


def test_long_hit(loader):
    r = _ef.get_event_factor("sh600869", loader=loader)
    assert r["available"] is True
    assert r["signal"] == "看多"
    assert r["score"] == 0.0298
    assert r["source"] == "P1-ev-top_long"


def test_short_hit(loader):
    r = _ef.get_event_factor("sh603118", loader=loader)
    assert r["available"] is True
    assert r["signal"] == "看空"
    assert r["score"] == -0.0545


def test_daily_precise_fallback(loader):
    """不在榜单、但在 daily 里的标的，应返回精确逐日得分（取最新日期）。"""
    r = _ef.get_event_factor("sh600000", loader=loader)
    assert r["available"] is True
    assert r["score"] == 0.021  # 2026-08-14 最新
    assert r["signal"] == "看多"
    assert r["source"] == "P1-ev-daily"


def test_absent_symbol_unavailable(loader, monkeypatch):
    # P1 miss 后会依次兜底到新闻/龙虎榜（均触网），注入 unavailable 保持离线确定性
    monkeypatch.setattr(_ef, "news_event_signal",
                        lambda t, lookback_days=10: {"available": False, "symbol": t, "reason": "offline"})
    monkeypatch.setattr(_ef, "lhb_event_signal",
                        lambda t, lookback_days=10: {"available": False, "symbol": t, "reason": "近 10 日未上龙虎榜"})
    r = _ef.get_event_factor("sh999999", loader=loader)
    assert r["available"] is False
    assert "reason" in r


def test_empty_loader_unavailable():
    """无任何信号文件时，应明确 unavailable，而非编造数据。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ld = P1SignalLoader(source_dirs=[td], ttl=10_000)
        r = _ef.get_event_factor("sh600000", loader=ld)
        assert r["available"] is False


def test_blank_symbol_unavailable():
    assert _ef.get_event_factor("").get("available") is False


# ── 诚实红线守卫（2026-11-20）：缺数据不得补 0 冒充真实值 ──────────────────

def _write_signals(d: Path, payload: dict) -> Path:
    (d / "signal_ev_h10.json").write_text(json.dumps(payload), encoding="utf-8")
    return d


class TestNumOrNone:
    """_num_or_none：缺失/非法 → None，绝不补 0。"""

    def test_none_and_missing(self):
        assert _ef._num_or_none(None) is None
        assert _ef._num_or_none("") is None

    def test_nan_inf_and_str(self):
        assert _ef._num_or_none(float("nan")) is None
        assert _ef._num_or_none(float("inf")) is None
        assert _ef._num_or_none("0.5") is None  # 字符串不算真实数值

    def test_valid_numbers_and_bool_excluded(self):
        assert _ef._num_or_none(0.0) == 0.0  # 真实 0 是合法值
        assert _ef._num_or_none(0.0298) == 0.0298
        assert _ef._num_or_none(True) is None  # bool 不是业务数值


class TestMissingFieldsStayNone:
    """榜单/逐日行缺 pred/rank/score 键 → 字段 None 且 available=True（在榜是真实事实），
    与 event_driven_long_list 的 None 口径一致；不得伪装成 0 分信号。"""

    def _loader(self, tmp_path: Path, payload: dict) -> P1SignalLoader:
        d = tmp_path / "sig"
        d.mkdir(parents=True, exist_ok=True)
        _write_signals(d, payload)
        return P1SignalLoader(source_dirs=[str(d)], ttl=10_000)

    def test_long_row_missing_pred_rank(self, tmp_path: Path):
        payload = {
            "model": "ev", "latest_date": "2026-08-14", "horizon": 10,
            "top_long": [{"symbol": "sh600869"}],  # pred/rank 键整体缺失
            "top_short": [{"symbol": "sh603118", "pred": -0.0545, "rank": 0.0007}],
            "daily": [],
        }
        r = _ef.get_event_factor("sh600869", loader=self._loader(tmp_path, payload))
        assert r["available"] is True, "标的在榜上是真实事实，不得因缺值降为 unavailable"
        assert r["signal"] == "看多"
        assert r["score"] is None and r["rank"] is None

    def test_short_row_missing_pred_rank(self, tmp_path: Path):
        payload = {
            "model": "ev", "latest_date": "2026-08-14", "horizon": 10,
            "top_long": [{"symbol": "sh600869", "pred": 0.0298, "rank": 1.0}],
            "top_short": [{"symbol": "sh603118"}],  # pred/rank 键整体缺失
            "daily": [],
        }
        r = _ef.get_event_factor("sh603118", loader=self._loader(tmp_path, payload))
        assert r["available"] is True
        assert r["signal"] == "看空"
        assert r["score"] is None and r["rank"] is None

    def test_daily_row_missing_score(self, tmp_path: Path):
        payload = {
            "model": "ev", "latest_date": "2026-08-14", "horizon": 10,
            "top_long": [], "top_short": [],
            "daily": [{"date": "2026-08-14", "symbol": "sh600000", "signal": "看多"}],  # 缺 score
        }
        r = _ef.get_event_factor("sh600000", loader=self._loader(tmp_path, payload))
        assert r["available"] is True
        assert r["score"] is None

    def test_real_zero_still_real_zero(self, tmp_path: Path):
        """真实 0.0 是合法业务值，必须保留 0 而非被误判为缺失。"""
        payload = {
            "model": "ev", "latest_date": "2026-08-14", "horizon": 10,
            "top_long": [{"symbol": "sh600869", "pred": 0.0, "rank": 0.0}],
            "top_short": [], "daily": [],
        }
        r = _ef.get_event_factor("sh600869", loader=self._loader(tmp_path, payload))
        assert r["available"] is True
        assert r["score"] == 0.0 and r["rank"] == 0.0
