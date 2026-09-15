"""G12 回测任务持久化守卫：注册表读写/清洗 + 页面接入契约。"""
from __future__ import annotations

import os

from modules.backtest_runs import (
    clear_runs, get_run, list_runs, new_run_id, record_run, sanitize,
)

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def test_new_run_id_unique():
    ids = {new_run_id() for _ in range(30)}
    assert len(ids) == 30


def test_record_get_list(tmp_path):
    p = str(tmp_path / "runs.json")
    r1 = record_run({"ticker": "600519"}, status="success",
                    summary={"total_return_pct": 5.0}, path=p)
    assert r1 and r1["run_id"]
    got = get_run(r1["run_id"], path=p)
    assert got["params"]["ticker"] == "600519"
    assert got["summary"]["total_return_pct"] == 5.0
    r2 = record_run({"ticker": "000001"}, path=p)
    runs = list_runs(limit=10, path=p)
    assert len(runs) == 2
    assert {r["run_id"] for r in runs} == {r1["run_id"], r2["run_id"]}


def test_sanitize_nan_and_numpy():
    import numpy as np
    out = sanitize({"a": np.int64(3), "b": float("nan"), "c": np.float64(1.5),
                    "d": [np.float64(2.0)]})
    assert out["a"] == 3
    assert out["b"] is None
    assert abs(out["c"] - 1.5) < 1e-9
    assert out["d"] == [2.0]


def test_get_run_missing(tmp_path):
    assert get_run("nope", path=str(tmp_path / "runs.json")) is None


def test_clear_runs(tmp_path):
    p = str(tmp_path / "runs.json")
    record_run({"ticker": "x"}, path=p)
    assert clear_runs(path=p) is True
    assert list_runs(path=p) == []


def test_page30_integrates_registry():
    """页面 30 必须接入注册表（记录 run + 展示历史），防被回退。"""
    src_path = os.path.join(_PROJECT_ROOT, "pages", "30_策略回测.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "backtest_runs" in src, "30 页必须引用 backtest_runs 注册表"
    assert "record_run(" in src, "回测完成后必须记录 run"
    assert "fragment_run_history" in src, "必须渲染历史回测记录"
