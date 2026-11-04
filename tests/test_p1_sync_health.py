"""P1 同步日常化闭环守卫（modules.p1_sync_health + backend.p1_sync_scheduler）。

钉住五类不变量：
  1. 无副本 → dead（绝不把「没同步过」报成 ok）
  2. 同步成功 → 副本落盘 + 状态快照落盘 + ok
  3. 幂等：第二轮 written 为空、unchanged 计数 ≥1（不重复写副本）
  4. dry-run 不写副本、不写快照（观测不产生副作用）
  5. 全部候选无效 → 拒绝写入（目标目录不出现副本），且 ok=False 如实上报
另加：新鲜度滞后判 warn（不误判成结构损坏）、调度器在测试环境不启动。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
import sys  # noqa: E402

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.p1_sync_scheduler import start_p1_sync_scheduler  # noqa: E402
from modules.p1_sync_health import (  # noqa: E402
    assess_p1_sync_health,
    run_sync_cycle,
    status_path,
)

NOW = datetime(2026, 11, 4, 21, 0, 0)
TODAY = date(2026, 11, 4)


def _payload(model: str, latest_date: str) -> dict:
    """结构合法（键齐全 / symbol 合法 / rank 单调）的信号体。"""
    return {
        "model": model,
        "latest_date": latest_date,
        "horizon": 10,
        "top_long": [{"symbol": "sh600519", "rank": 1.0},
                     {"symbol": "sz300750", "rank": 0.9}],
        "top_short": [{"symbol": "sz000001", "rank": 0.001},
                      {"symbol": "sh601318", "rank": 0.002}],
        "daily": [],
        "generated_at": f"{latest_date}T16:00:00",
    }


def _write(d: Path, name: str, payload: dict) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def _paths(tmp_path: Path):
    src = tmp_path / "src"
    tgt = tmp_path / "data" / "p1_signals"
    sp = status_path(tgt)
    return src, tgt, sp


# ── 1. 无副本 → dead ──────────────────────────────────────────────
def test_health_dead_when_target_missing(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    h = assess_p1_sync_health(now=NOW, target_dir=tgt, status_file=sp)
    assert h["status"] == "dead"
    assert h["rows"] == []
    assert "不存在" in h["message"] or "为空" in h["message"]


def test_health_dead_when_target_empty(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    tgt.mkdir(parents=True)
    h = assess_p1_sync_health(now=NOW, target_dir=tgt, status_file=sp)
    assert h["status"] == "dead"
    assert "为空" in h["message"]


# ── 2. 同步成功 → 副本 + 快照 + ok ────────────────────────────────
def test_cycle_syncs_and_writes_status(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-11-04"))
    snap = run_sync_cycle(source_dirs=[str(src)], target_dir=tgt, today=TODAY,
                          status_file=sp, now=NOW)
    assert snap["ok"] is True
    assert len(snap["written"]) == 1
    assert (tgt / "signal_gru_h10.json").is_file()
    assert sp.is_file()
    saved = json.loads(sp.read_text(encoding="utf-8"))
    assert saved["health"]["status"] == "ok"
    assert saved["health"]["latest"] == "2026-11-04"


# ── 3. 幂等：第二轮不重复写 ───────────────────────────────────────
def test_cycle_idempotent(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-11-04"))
    first = run_sync_cycle(source_dirs=[str(src)], target_dir=tgt, today=TODAY,
                           status_file=sp, now=NOW)
    second = run_sync_cycle(source_dirs=[str(src)], target_dir=tgt, today=TODAY,
                            status_file=sp, now=NOW)
    assert len(first["written"]) == 1
    assert second["written"] == []
    assert second["counts"]["unchanged"] >= 1
    assert second["ok"] is True


# ── 4. dry-run 无副作用 ───────────────────────────────────────────
def test_cycle_dry_run_writes_nothing(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-11-04"))
    snap = run_sync_cycle(source_dirs=[str(src)], target_dir=tgt, today=TODAY,
                          status_file=sp, dry_run=True, now=NOW)
    assert snap["dry_run"] is True
    assert snap["written"] == []
    assert not (tgt / "signal_gru_h10.json").exists()
    assert not sp.exists()


# ── 5. 全部候选无效 → 拒绝写入，且如实报错 ────────────────────────
def test_all_invalid_refuses_write(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    src.mkdir(parents=True)
    (src / "signal_gru_h10.json").write_text("{not json", encoding="utf-8")
    snap = run_sync_cycle(source_dirs=[str(src)], target_dir=tgt, today=TODAY,
                          status_file=sp, now=NOW)
    assert snap["all_invalid"] is True
    assert snap["ok"] is False
    assert snap["written"] == []
    assert snap["errors"]
    assert not list(tgt.glob("signal_*.json")) if tgt.is_dir() else True


# ── 6. 新鲜度滞后 → warn（不误判成结构损坏）───────────────────────
def test_health_warn_when_stale(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-10-01"))
    run_sync_cycle(source_dirs=[str(src)], target_dir=tgt, today=TODAY,
                   status_file=sp, now=NOW)
    h = assess_p1_sync_health(now=datetime(2026, 11, 20, 9, 0, 0),
                              target_dir=tgt, status_file=sp)
    assert h["status"] == "warn"
    assert h["stale"] == ["signal_gru_h10.json"]
    assert h["rows"][0]["structural_ok"] is True


# ── 7. 部分副本结构损坏 → warn（全坏才是 dead）────────────────────
def test_health_warn_on_partial_structural_break(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-11-04"))
    run_sync_cycle(source_dirs=[str(src)], target_dir=tgt, today=TODAY,
                   status_file=sp, now=NOW)
    (tgt / "signal_ev_h10.json").write_text("{broken", encoding="utf-8")
    h = assess_p1_sync_health(now=NOW, target_dir=tgt, status_file=sp)
    assert h["status"] == "warn"
    assert "signal_ev_h10.json" in h["structural_bad"]


def test_health_dead_when_all_structural_broken(tmp_path):
    src, tgt, sp = _paths(tmp_path)
    tgt.mkdir(parents=True)
    (tgt / "signal_gru_h10.json").write_text("{broken", encoding="utf-8")
    h = assess_p1_sync_health(now=NOW, target_dir=tgt, status_file=sp)
    assert h["status"] == "dead"
    assert "结构不合格" in h["message"]


# ── 8. 调度器在测试环境不启动 ─────────────────────────────────────
def test_scheduler_skipped_in_testing_env():
    class _App:
        config = {"TESTING": True}

    start_p1_sync_scheduler(_App())
    names = [t.name for t in threading.enumerate()]
    assert "p1-sync-scheduler" not in names