"""回测任务持久化（G12）：run ID 注册表，跨刷新 / 切页 / 重启可回溯。

对标 tick-stock-panel 的「回测 run 持久化」：给每次回测分配 run_id，把参数 / 状态 / 摘要
落盘，页面可列出历史运行并回填——**切页或刷新后不丢**（session_state 刷新即失，本模块补上）。

存储：``data/backtest_runs.json``（data/ 已 gitignore，属运行时数据，不进库）。
写入失败静默降级（返回 None/False），**绝不影响回测主流程**。
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

_RUNS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "backtest_runs.json"
)
MAX_KEEP = 100


def new_run_id() -> str:
    """生成可读且唯一的 run ID（时间戳 + 随机后缀）。"""
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:12]


def sanitize(obj):
    """把 numpy 标量 / NaN / 非 JSON 类型降级为可 JSON 序列化的原生类型。"""
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        np = None  # type: ignore
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if np is not None:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            f = float(obj)
            return f if f == f else None
    if isinstance(obj, float):
        return obj if obj == obj else None
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


def _load_all(path: str | None = None) -> list:
    p = path or _RUNS_PATH
    try:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            runs = d.get("runs") if isinstance(d, dict) else d
            if isinstance(runs, list):
                return runs
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[backtest-runs] 读取失败: {e}")
    return []


def _save_all(runs: list, path: str | None = None) -> bool:
    p = path or _RUNS_PATH
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"runs": list(runs)[:MAX_KEEP]}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[backtest-runs] 保存失败: {e}")
        return False


def record_run(params: dict, status: str = "success", summary: dict | None = None,
               run_id: str | None = None, path: str | None = None):
    """记录一次回测运行。成功返回记录 dict，失败返回 None（静默降级）。"""
    rid = run_id or new_run_id()
    rec = {
        "run_id": rid,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "params": sanitize(params or {}),
        "summary": sanitize(summary or {}),
    }
    runs = [r for r in _load_all(path) if r.get("run_id") != rid] + [rec]
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rec if _save_all(runs, path) else None


def list_runs(limit: int = 20, path: str | None = None) -> list:
    """按时间倒序返回最近运行记录。"""
    runs = _load_all(path)
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[: max(0, int(limit))]


def get_run(run_id: str, path: str | None = None):
    for r in _load_all(path):
        if r.get("run_id") == run_id:
            return r
    return None


def clear_runs(path: str | None = None) -> bool:
    return _save_all([], path)
