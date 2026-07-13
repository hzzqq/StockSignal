"""
backend/tasks/worker.py
---------------------
后台任务工作器：让个股分析、多股对比、AI 咨询等耗时操作在后台运行，
即使用户切到其他页面也不中断。

- 多任务并发（ThreadPoolExecutor）
- 内存 + JSON 双缓存，任务可持久化 24h
- 任务类型：analysis / compare / ai_consult
"""
from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd


# 保证项目根目录在 sys.path，以便导入 modules/ 包
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


_TASK_STORE_DIR = _PROJECT_ROOT / "data"
_TASK_STORE_FILE = _TASK_STORE_DIR / "background_tasks.json"
_TASK_TTL_SECONDS = 24 * 3600
_MAX_WORKERS = 4


class Task:
    def __init__(self, task_id: str, task_type: str, payload: Dict[str, Any], created_at: float):
        self.task_id = task_id
        self.task_type = task_type
        self.payload = payload
        self.created_at = created_at
        self.updated_at = created_at
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.result: Any = None
        self.error: Optional[str] = None
        self._lock = threading.Lock()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "task_id": self.task_id,
                "task_type": self.task_type,
                "payload": self.payload,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "status": self.status.value,
                "progress": self.progress,
                "result": self.result,
                "error": self.error,
            }


class TaskWorker:
    """后台任务工作器（单例）。"""

    def __init__(self, max_workers: int = _MAX_WORKERS):
        self._tasks: Dict[str, Task] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="stocksignal_task")
        self._lock = threading.Lock()
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._started = False
        self._register_default_handlers()
        self._load_from_disk()

    def _register_default_handlers(self):
        self.register_handler("analysis", _handle_analysis)
        self.register_handler("compare", _handle_compare)
        self.register_handler("ai_consult", _handle_ai_consult)

    def register_handler(self, task_type: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self._handlers[task_type] = handler

    def submit(self, task_type: str, payload: Dict[str, Any]) -> str:
        task_id = str(uuid.uuid4())
        task = Task(task_id, task_type, payload, time.time())
        with self._lock:
            self._tasks[task_id] = task
        self._persist()
        self._executor.submit(self._run_task, task)
        return task_id

    def status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        return task.to_dict()

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)[:limit]
        return [t.to_dict() for t in tasks]

    def _run_task(self, task: Task) -> None:
        handler = self._handlers.get(task.task_type)
        if not handler:
            task.status = TaskStatus.ERROR
            task.error = f"未知任务类型: {task.task_type}"
            task.updated_at = time.time()
            self._persist()
            return

        with task._lock:
            task.status = TaskStatus.RUNNING
            task.updated_at = time.time()
        self._persist()

        try:
            result = handler(task.payload)
            with task._lock:
                task.status = TaskStatus.SUCCESS
                task.progress = 100
                task.result = _serialize_for_json(result)
                task.updated_at = time.time()
        except Exception as e:
            warnings.warn(f"Task {task.task_id} failed: {e}")
            with task._lock:
                task.status = TaskStatus.ERROR
                task.error = str(e)
                task.updated_at = time.time()
        finally:
            self._persist()

    def _persist(self) -> None:
        try:
            _TASK_STORE_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                # 清理过期任务
                now = time.time()
                expired = [
                    tid for tid, t in self._tasks.items()
                    if now - t.created_at > _TASK_TTL_SECONDS
                ]
                for tid in expired:
                    del self._tasks[tid]
                data = [t.to_dict() for t in self._tasks.values()]
            with open(_TASK_STORE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except Exception as e:
            warnings.warn(f"Task persistence failed: {e}")

    def _load_from_disk(self) -> None:
        if not _TASK_STORE_FILE.exists():
            return
        try:
            with open(_TASK_STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            for item in data:
                created_at = float(item.get("created_at", now))
                if now - created_at > _TASK_TTL_SECONDS:
                    continue
                task = Task(
                    task_id=item["task_id"],
                    task_type=item["task_type"],
                    payload=item.get("payload", {}),
                    created_at=created_at,
                )
                task.updated_at = float(item.get("updated_at", created_at))
                task.status = TaskStatus(item.get("status", "pending"))
                task.progress = int(item.get("progress", 0))
                task.result = item.get("result")
                task.error = item.get("error")
                self._tasks[task.task_id] = task
                # 如果加载时仍在 running，说明上次进程被中断，标记为 error
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.ERROR
                    task.error = "服务重启导致任务中断"
        except Exception as e:
            warnings.warn(f"Task load failed: {e}")


def _serialize_for_json(obj: Any) -> Any:
    """把 DataFrame / Timestamp / NaN 等转成严格 JSON 友好结构。"""
    if isinstance(obj, pd.DataFrame):
        return [_serialize_for_json(row) for row in obj.to_dict(orient="records")]
    if isinstance(obj, pd.Series):
        return _serialize_for_json(obj.to_dict())
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_json(v) for v in obj]
    if isinstance(obj, (datetime, pd.Timestamp)):
        return obj.isoformat()
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.generic):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj.item()
    return obj


def _handle_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    """执行个股分析。"""
    from modules.analysis_engine import run_analysis
    from modules.fetcher import StockFetcher

    ticker = payload.get("ticker", "")
    fetcher = StockFetcher()
    return run_analysis(ticker, fetcher=fetcher)


def _handle_compare(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """执行多股对比。"""
    from modules.compare import fetch_compare

    codes = payload.get("codes", [])
    period = payload.get("period", 120)
    if not codes:
        raise ValueError("codes 不能为空")
    return fetch_compare(codes, period)


def _handle_ai_consult(payload: Dict[str, Any]) -> Dict[str, Any]:
    """执行 AI 独立咨询。"""
    from modules.ai_engine import ai_answer

    question = payload.get("question", "")
    context = payload.get("context", {})
    return ai_answer(question, context)


# 全局单例
task_worker = TaskWorker()
