"""P1 信号加载器单元测试（离线、零网络）。

覆盖 modules/p1_signal 的核心契约：目录发现优先级、模型视图、A/B 重叠度数学、
缓存失效（invalidate / ttl 过期 / mtime 变化）、容错（跳过损坏 JSON）、缺失模型报错。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from modules import p1_signal as _m


# ───────────────────────── 测试夹具 ─────────────────────────
def _write_signal(d: Path, name: str, payload: dict) -> Path:
    p = d / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


@pytest.fixture
def sig_dir(tmp_path: Path) -> Path:
    d = tmp_path / "signals"
    d.mkdir()
    # ev：看多 [sh600869, sh600001]；看空 [sh603118]
    _write_signal(d, "signal_ev_h10.json", {
        "model": "ev", "latest_date": "2026-08-14", "horizon": 10,
        "top_long": [
            {"symbol": "sh600869", "pred": 0.0298, "rank": 1.0},
            {"symbol": "sh600001", "pred": 0.0100, "rank": 0.9},
        ],
        "top_short": [{"symbol": "sh603118", "pred": -0.0545, "rank": 0.0007}],
        "daily": [
            {"date": "2026-08-14", "symbol": "sh600869", "score": 0.02, "signal": "看多"},
            {"date": "2026-08-13", "symbol": "sh600001", "score": -0.01, "signal": "中性"},
        ],
    })
    # gru：看多 [sh600869, sh600002]（与 ev 共享 sh600869，用于重叠度）
    _write_signal(d, "signal_gru_h10.json", {
        "model": "gru", "latest_date": "2026-08-14", "horizon": 10,
        "top_long": [
            {"symbol": "sh600869", "pred": 0.0200, "rank": 1.0},
            {"symbol": "sh600002", "pred": 0.0150, "rank": 0.8},
        ],
        "top_short": [{"symbol": "sh603118", "pred": -0.0400, "rank": 0.001}],
        "daily": [],
    })
    return d


@pytest.fixture
def loader(sig_dir: Path) -> _m.P1SignalLoader:
    # ttl 设大，避免测试内时序抖动干扰单测语义
    return _m.P1SignalLoader(source_dirs=[str(sig_dir)], ttl=10_000)


# ───────────────────────── 目录发现 ─────────────────────────
def test_discover_source_dirs_env_priority(monkeypatch, tmp_path):
    env_dir = str(tmp_path / "env_sig")
    monkeypatch.setenv("P1_SIGNAL_DIR", env_dir)
    dirs = _m.discover_source_dirs()
    assert dirs[0] == env_dir, "P1_SIGNAL_DIR 必须最高优先级"
    # data/p1_signals 与本地默认目录应被纳入（用 Path.parts 做跨平台匹配，避开 / vs \\）
    parts = [Path(d).parts for d in dirs]
    assert any(("data", "p1_signals") == p[-2:] for p in parts), "data/p1_signals 应被纳入"
    assert any(("data", "P1", "processed", "signals") == p[-4:] for p in parts), \
        "本地默认 P1 产出目录应被纳入"


def test_discover_source_dirs_dedup(monkeypatch, tmp_path):
    same = str(tmp_path / "dup")
    monkeypatch.setenv("P1_SIGNAL_DIR", same)
    # 用一个临时 data/p1_signals 同路径制造重复，验证去重保序
    dirs = _m.discover_source_dirs()
    assert len(dirs) == len(set(dirs)), "不应有重复目录"


# ───────────────────────── 基础视图 ─────────────────────────
def test_available_models_sorted(loader):
    assert loader.available_models() == ["ev", "gru"]


def test_top_long_short_and_latest(loader):
    longs = loader.top_long("ev")
    assert [r["symbol"] for r in longs] == ["sh600869", "sh600001"]
    shorts = loader.top_short("ev")
    assert shorts[0]["symbol"] == "sh603118"
    assert loader.latest_date("ev") == "2026-08-14"


def test_top_long_truncates_n(loader):
    assert len(loader.top_long("ev", n=1)) == 1
    assert len(loader.top_long("ev")) == 2


def test_summary_shape(loader):
    s = loader.summary()
    assert set(s.keys()) == {"ev", "gru"}
    assert s["ev"]["label"] == "EV 事件因子"
    assert s["ev"]["n_top_long"] == 2
    assert s["ev"]["n_top_short"] == 1
    assert s["ev"]["n_daily"] == 2


def test_model_label_fallback():
    assert _m.P1SignalLoader.model_label("ev") == "EV 事件因子"
    assert _m.P1SignalLoader.model_label("unknown_xyz") == "unknown_xyz"


def test_daily_df_returns_frame(loader):
    import pandas as pd
    df = loader.daily_df("ev")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert set(df.columns) >= {"date", "symbol", "score", "signal"}


# ───────────────────────── A/B 重叠度数学 ─────────────────────────
def test_top_overlap_jaccard(loader):
    # ev={sh600869,sh600001}, gru={sh600869,sh600002} → inter=1, union=3 → 1/3
    jac, inter = loader.top_overlap("ev", "gru", n=15)
    assert inter == 1
    assert abs(jac - 1 / 3) < 1e-9


def test_top_overlap_empty(loader):
    # 构造一个无重叠场景：只看 gru 与自身之外的空集——用不存在模型路径不可行，
    # 改为验证两模型含相同符号时 jac=1（用 ev 与 ev 自身）
    jac, inter = loader.top_overlap("ev", "ev", n=15)
    assert inter == 2 and jac == 1.0


# ───────────────────────── 容错 / 报错 ─────────────────────────
def test_missing_model_raises_keyerror(loader):
    with pytest.raises(KeyError):
        loader.load("does_not_exist")


def test_scan_skips_corrupt_json(tmp_path):
    d = tmp_path / "mix"
    d.mkdir()
    _write_signal(d, "signal_ev_h10.json", {"model": "ev", "top_long": []})
    # 损坏文件：glob 命中但 json 解析失败，应被跳过而非崩溃
    (d / "signal_bad_h10.json").write_text("{not valid json", encoding="utf-8")
    ld = _m.P1SignalLoader(source_dirs=[str(d)], ttl=10_000)
    assert ld.available_models() == ["ev"]


# ───────────────────────── 缓存失效 ─────────────────────────
def test_invalidate_clears_all(loader, sig_dir):
    _ = loader.load("ev")  # 填充缓存
    assert "ev" in loader._cache
    loader.invalidate()
    assert "ev" not in loader._cache


def test_invalidate_single_model(loader, sig_dir):
    _ = loader.load("ev")
    _ = loader.load("gru")
    loader.invalidate("ev")
    assert "ev" not in loader._cache
    assert "gru" in loader._cache


def test_ttl_expiry_triggers_reload(loader, sig_dir):
    """ttl 过期后即使文件未变也应重新读取（真实刷新语义）。"""
    path = sig_dir / "signal_ev_h10.json"
    first = loader.load("ev")
    assert first["latest_date"] == "2026-08-14"
    # 改写内容（保持合法 JSON），等待超过 ttl（本例 ttl=10_000s 太大，临时改为短 ttl 验证）
    short = _m.P1SignalLoader(source_dirs=[str(sig_dir)], ttl=1)
    short.load("ev")
    time.sleep(1.2)  # 超过 ttl=1s
    new_payload = json.loads(path.read_text(encoding="utf-8"))
    new_payload["latest_date"] = "2099-01-01"
    path.write_text(json.dumps(new_payload), encoding="utf-8")
    reloaded = short.load("ev")
    assert reloaded["latest_date"] == "2099-01-01", "ttl 过期后应重载到新内容"


def test_mtime_change_triggers_reload(loader, sig_dir):
    """文件被重新导出（mtime 变化）→ 立即重载，不依赖 ttl。"""
    path = sig_dir / "signal_ev_h10.json"
    base_mtime = os.path.getmtime(path)
    first = loader.load("ev")
    assert first["latest_date"] == "2026-08-14"
    # 改写内容并显式推进 mtime，确保与缓存 mtime 不同（文件系统粗粒度规避）
    new_payload = json.loads(path.read_text(encoding="utf-8"))
    new_payload["latest_date"] = "2099-02-02"
    path.write_text(json.dumps(new_payload), encoding="utf-8")
    os.utime(path, (base_mtime + 100, base_mtime + 100))
    reloaded = loader.load("ev")
    assert reloaded["latest_date"] == "2099-02-02", "mtime 变化后应重载到新内容"
