"""
每日快照离线兜底守卫：modules/shepherd.load_latest_snapshot

覆盖：
- 目录无快照文件 → 返回 None（优雅降级，不抛异常）
- 主快照 data/daily_snapshot.json 正常解析 → 返回该 dict
- 主快照缺失、snapshots/ 下有最新 json → 兜底返回
- 快照文件损坏（非法 JSON）→ 返回 None（异常被吞）

全程离线：用 tmp_path 隔离数据目录，monkeypatch _SHEPHERD_DATA_DIR。
"""
import json

import pytest

from modules import shepherd


def test_load_latest_snapshot_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(shepherd, "_SHEPHERD_DATA_DIR", str(tmp_path))
    assert shepherd.load_latest_snapshot() is None


def test_load_latest_snapshot_reads_main(tmp_path, monkeypatch):
    snap = {"date": "2026-09-10", "temperature": 21.4, "cycle": "修复试探",
            "bias": "中性", "confidence": 50}
    (tmp_path / "daily_snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr(shepherd, "_SHEPHERD_DATA_DIR", str(tmp_path))
    out = shepherd.load_latest_snapshot()
    assert out is not None
    assert out["temperature"] == pytest.approx(21.4)
    assert out["cycle"] == "修复试探"
    assert out["bias"] == "中性"


def test_load_latest_snapshot_falls_back_to_snapshots_dir(tmp_path, monkeypatch):
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    snap = {"date": "2026-09-01", "temperature": 30.0}
    (snap_dir / "2026-09-01.json").write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr(shepherd, "_SHEPHERD_DATA_DIR", str(tmp_path))
    out = shepherd.load_latest_snapshot()
    assert out is not None
    assert out["temperature"] == pytest.approx(30.0)


def test_load_latest_snapshot_corrupt_json_returns_none(tmp_path, monkeypatch):
    (tmp_path / "daily_snapshot.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(shepherd, "_SHEPHERD_DATA_DIR", str(tmp_path))
    assert shepherd.load_latest_snapshot() is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
