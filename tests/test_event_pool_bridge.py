"""事件池实时桥接测试：P1 信号 → event_pool_brief 变换 + 优雅降级。

不依赖联网或 P1 真实产物；用临时目录构造最小 P1 信号文件验证变换正确性，
并验证「无产物 / 空 top_long」时拒绝覆盖既有快照。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import shepherd_ladder as sl  # noqa: E402


def _write_p1_signal(d: Path, *, top_long, latest_date="2026-09-10", model="gru"):
    d.mkdir(parents=True, exist_ok=True)
    sig = {
        "generated_at": "2026-09-10T15:00:00",
        "horizon": 10,
        "model": model,
        "latest_date": latest_date,
        "top_long": top_long,
        "top_short": [],
        "daily": [],
    }
    p = d / "signal_gru_h10.json"
    p.write_text(json.dumps(sig, ensure_ascii=False), encoding="utf-8")
    return p


def test_refresh_from_valid_p1_signal(tmp_path, monkeypatch):
    sig_dir = tmp_path / "signals"
    out = tmp_path / "event_pool_brief.json"
    _write_p1_signal(sig_dir, top_long=[
        {"symbol": "sh600000", "score": 0.031, "rank": 1.0},
        {"symbol": "sz000001", "score": 0.028, "rank": 0.95},
        {"symbol": "sh601318", "score": 0.025, "rank": 0.90},
    ])
    # 既有离线快照不应被无效数据覆盖——先放一个占位，验证仅有效刷新才写
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")

    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(sig_dir),
                                      out_path=str(out), max_age_days=30)
    assert st["refreshed"] is True
    assert st["live"] is True
    assert st["count"] == 3
    assert st["date"] == "2026-09-10"
    assert st["source"].startswith("P1-QuantFactor gru")

    brief = json.loads(out.read_text(encoding="utf-8"))
    assert brief["live"] is True
    assert len(brief["pool"]) == 3
    # 变换正确性：pct rank → 0-100 显示分；第一名应 100.0
    assert brief["pool"][0]["rank"] == 1
    assert brief["pool"][0]["symbol"] == "sh600000"
    assert brief["pool"][0]["score"] == 100.0
    assert brief["pool"][0]["raw_pred"] == 0.031
    assert brief["pool"][0]["signal"] == "看多"
    assert brief["pool"][0]["source"] == "P1-gru-top_long"
    # load_event_pool 能识别 live
    ep = sl.load_event_pool(path=str(out))
    assert ep["available"] is True
    assert ep["live"] is True
    assert ep["date"] == "2026-09-10"


def test_no_p1_signals_dir(tmp_path, monkeypatch):
    out = tmp_path / "event_pool_brief.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(tmp_path / "nope"),
                                      out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "no_p1_signals_dir"
    # 既有快照未被改动
    assert json.loads(out.read_text(encoding="utf-8"))["date"] == "2026-09-03"


def test_no_p1_signal_file(tmp_path, monkeypatch):
    sig_dir = tmp_path / "signals"
    sig_dir.mkdir()
    out = tmp_path / "event_pool_brief.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(sig_dir), out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "no_p1_signal"


def test_empty_top_long_refused(tmp_path, monkeypatch):
    sig_dir = tmp_path / "signals"
    out = tmp_path / "event_pool_brief.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")
    _write_p1_signal(sig_dir, top_long=[])  # 空 top_long
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(sig_dir), out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "p1_signal_empty"
    assert json.loads(out.read_text(encoding="utf-8"))["date"] == "2026-09-03"


def test_load_event_pool_offline_snapshot_no_live_flag(tmp_path):
    p = tmp_path / "event_pool_brief.json"
    p.write_text(json.dumps({
        "date": "2026-09-03", "model": "ev",
        "source": "P1-QuantFactor EV 事件因子",
        "pool": [{"rank": 1, "symbol": "sh600869", "score": 100.0,
                  "raw_rank": 1.0, "raw_pred": 0.029, "signal": "看多",
                  "source": "P1-ev-top_long"}],
    }), encoding="utf-8")
    ep = sl.load_event_pool(path=str(p))
    assert ep["available"] is True
    assert ep["live"] is False
    assert ep["date"] == "2026-09-03"
    assert ep["source"] == "P1-QuantFactor EV 事件因子"
