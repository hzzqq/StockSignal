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


def test_absent_symbol_unavailable(loader):
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
