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
import logging
import math
import sys
import threading

logger = logging.getLogger(__name__)
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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


def _parse_task_status(raw: Any) -> TaskStatus:
    """把磁盘上读取的原始 status 安全地转成 TaskStatus。

    若原始值为非法/未知/类型错误，回退到 TaskStatus.ERROR，避免加载时崩溃。
    """
    try:
        return TaskStatus(raw)
    except (ValueError, TypeError):
        return TaskStatus.ERROR


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
        # 实时进度（多智能体协作）
        self.stage: str = ""                 # 当前正在跑的 agent stage key
        self.logs: List[Dict[str, Any]] = []  # [{stage, message, ts}]
        self._last_persist = 0.0
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
                "stage": self.stage,
                "logs": self.logs,
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
        self.register_handler("quant_research", _handle_quant_research)
        self.register_handler("ai_research", _handle_ai_research)

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

    def cancel(self, task_id: str) -> Optional[bool]:
        """取消任务（T-315 停止生成）。

        返回：
          - True  : 本次成功标记为 CANCELLED（pending/running 可取消）
          - False : 任务已终态（success/error/cancelled），不重复取消、不回退状态
          - None  : 任务不存在

        诚实语义：Python 线程无法强杀，正在执行的 handler 仍会跑完；取消只保证
        「状态不再被结果覆盖」（_run_task 写结果前检查取消态），前端不再展示结果。
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        with task._lock:
            if task.status in (TaskStatus.SUCCESS, TaskStatus.ERROR, TaskStatus.CANCELLED):
                return False
            task.status = TaskStatus.CANCELLED
            task.error = "用户已停止生成"
            task.updated_at = time.time()
        self._persist()
        return True

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
            if task.status is TaskStatus.CANCELLED:
                # T-315：排队期间已被用户取消 → 不再执行 handler
                return
            task.status = TaskStatus.RUNNING
            task.updated_at = time.time()

        # 注册实时进度上报：编排器内部回调 → 写入 task.stage / logs / progress（节流持久化）
        from backend.tasks.progress_bus import register, unregister
        from modules.quantagent.progress import percent_for

        def _reporter(stage_key: str, message) -> None:
            """批次9：内存 logs + SQLite  timeline 持久化（尽力而为，失败静默跳过）。"""
            with task._lock:
                task.stage = stage_key
                task.progress = max(task.progress, percent_for(stage_key))
                if isinstance(message, dict):
                    _msg = message.get("_fmt", str(message))
                    task.logs.append({"stage": stage_key, "message": _msg, "event": message, "ts": time.time()})
                else:
                    task.logs.append({"stage": stage_key, "message": message, "ts": time.time()})
                task.updated_at = time.time()
                now = time.time()
                thrift = now - task._last_persist > 1.0
                if thrift:
                    task._last_persist = now
            if thrift:
                self._persist()
            # 批次9：dict event 同时写 SQLite timeline（在 Flask app context 下自然生效）
            if isinstance(message, dict):
                try:
                    _persist_timeline_event(task.task_id, stage_key, message)
                except Exception:
                    logger.debug("timeline 事件持久化失败（不中断主流程）", exc_info=True)

        register(task.task_id, _reporter)
        # 把 task_id 注入 payload 副本，供 handler 取用
        payload = dict(task.payload)
        payload["__task_id__"] = task.task_id
        self._persist()

        try:
            result = handler(payload)
            with task._lock:
                if task.status is TaskStatus.CANCELLED:
                    # T-315：用户已停止生成——不覆盖取消态、不发布结果（线程无法强杀，
                    # 但结果对用户不可见，避免「点了停止还突然弹出回答」）
                    task.updated_at = time.time()
                else:
                    task.status = TaskStatus.SUCCESS
                    task.progress = 100
                    task.result = _serialize_for_json(result)
                    task.updated_at = time.time()
        except Exception as e:
            warnings.warn(f"Task {task.task_id} failed: {e}")
            with task._lock:
                if task.status is not TaskStatus.CANCELLED:
                    task.status = TaskStatus.ERROR
                    task.error = str(e)
                    task.updated_at = time.time()
        finally:
            unregister(task.task_id)
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
                task.status = _parse_task_status(item.get("status", "pending"))
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
    """执行 AI 独立咨询（T-308 透传回应方式 style；T-314 透传用户选择的模型）。

    payload:
      - question: 用户问题
      - context:  页面上下文（含 history）
      - style:    回应方式 quick/report/debate/teach（非法值由 ai_engine 兜底 quick）
      - model:    用户在前端选择的模型名（可空；ai_engine 经 resolve_model 做
                  provider 感知校验，非法/跨 provider 时回落 style 分层默认）
    """
    from modules.ai_engine import ai_answer

    question = payload.get("question", "")
    context = payload.get("context", {})
    style = str(payload.get("style") or "quick")
    model = str(payload.get("model") or "").strip() or None
    return ai_answer(question, context, style=style, model=model)


def _handle_ai_research(payload: Dict[str, Any]) -> Dict[str, Any]:
    """执行 H1 AI 研究智能体（多步工具调用 + 引用溯源）。

    payload:
      - question: 用户问题（必填）
      - max_steps: 最大工具调用步数（可选，默认 8，上限 8；T-308 研报扩大上调）
      - history: 最近对话（可选，[{role, content}]，≤8 条；非法整体忽略，降级单轮）
      - style: 回应方式（可选，T-308：report=研报结构合成 / 其他=简洁；仅影响合成 prompt）
    每步经 progress_bus 上报（stage="research"），前端任务轮询可见过程。
    契约见 .workbuddy/specs/ai_research_agent_contract.md。
    """
    import modules.research_agent as ra
    from backend.tasks.progress_bus import report

    question = str(payload.get("question", "")).strip()
    if not question:
        raise ValueError("question 不能为空")
    task_id = payload.get("__task_id__")
    try:
        max_steps = int(payload.get("max_steps") or 8)
    except (TypeError, ValueError):
        max_steps = 8

    def _on_step(message):
        """批次8：同时接受 str（旧）和 dict（新结构化 timeline event）——
        dict event 只加 _fmt 格式化字符串后直接 report（progress_bus 现在接受 dict）。
        这样 task.logs 条目同时含可读 message 字段 + 原始 event 字段，前端可按需取用。"""
        if not task_id:
            return
        try:
            if isinstance(message, dict):
                # 批次8：格式化字符串（▶ tool_start / ⚡ tool_end），挂 _fmt 字段
                _type = message.get("type", "event")
                _tool = message.get("tool", "?")
                _idx = message.get("idx", "?")
                _total = message.get("total", "?")
                if _type == "tool_start":
                    _fmt = f"▶ [{_idx}/{_total}] 调 {_tool}…"
                elif _type == "tool_end":
                    _elapsed = message.get("elapsed_s", 0)
                    _status = message.get("status", "?")
                    _summary = str(message.get("summary") or message.get("reason") or "")[:80]
                    _fmt = f"⚡ [{_idx}/{_total}] {_tool} → {_status} · {_elapsed:.1f}s{(': ' + _summary) if _summary else ''}"
                else:
                    _fmt = f"[{_type}] {message}"
                enriched = dict(message)
                enriched["_fmt"] = _fmt
                report(task_id, "research", enriched)
            else:
                report(task_id, "research", message)
        except Exception as e:  # noqa: BLE001 - 进度上报失败不影响研究主流程
            logger.debug("research 进度上报失败(task=%s): %s", task_id, e)

    # T-138 M4：可选 history（多轮记忆）——list 且 ≤8 条、每项为 dict 才放行；
    # 不合法 → 丢弃并照旧单轮执行（不报错不中断）；条目级规范化由 research_agent 负责。
    history = payload.get("history")
    extra: Dict[str, Any] = {}
    if isinstance(history, list) and len(history) <= 8 \
            and all(isinstance(h, dict) for h in history):
        extra["history"] = history

    return ra.run_research(question, max_steps=max_steps, on_step=_on_step,
                           style=str(payload.get("style") or "report"), **extra)


def _handle_quant_research(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行 QuantAgent 多智能体投研（异步后台任务）。

    payload:
      - ticker: 6 位 A股代码
      - use_browser / use_rag: 是否启用 FinBrowser / FinRAG（默认 True）
      - engine: "auto" | "langgraph" | "simple" | "crewai"
      - human_approval_enabled / force_human_review: 人工复核开关（后台无人值守时自动批准）
      - __task_id__: 由工作器注入，用于实时进度回传（前端轮询 task.stage/logs/progress）
    返回 ResearchState 的 JSON 安全字典（已剔除 DataFrame / reporter）。
    """
    from modules.quantagent import run_research
    from backend.tasks.progress_bus import report

    ticker = str(payload.get("ticker", "")).strip().zfill(6)
    if not ticker:
        raise ValueError("ticker 不能为空")

    task_id = payload.get("__task_id__")

    def _cb(stage_key: str, message: str) -> None:
        if task_id:
            report(task_id, stage_key, message)

    state = run_research(
        ticker,
        use_browser=bool(payload.get("use_browser", True)),
        use_rag=bool(payload.get("use_rag", True)),
        engine=str(payload.get("engine", "auto")),
        human_approval_enabled=bool(payload.get("human_approval_enabled", False)),
        force_human_review=bool(payload.get("force_human_review", False)),
        auto_resume_approval={"approved": True, "note": "（后台任务自动批准）"},
        progress_callback=_cb,
    )
    return state.to_dict()


# ------------------------------------------------------------------ 批次9：timeline SQLite 持久化

def _persist_timeline_event(task_id: str, stage: str, event: Dict[str, Any]) -> None:
    """尽力而为：把批次8 dict timeline event 持久化到 SQLite。

    批次10：追加 data_as_of + citation 列。citation 紧凑格式 "[S{idx}] {tool} @ {data_as_of}"。
    """
    from backend.models import AiTimelineEvent

    _type = event.get("type")
    _tool = event.get("tool")
    _idx = event.get("idx")
    _elapsed = event.get("elapsed_s")
    _status = event.get("status")
    _fmt = event.get("_fmt", "")
    _as_of = event.get("data_as_of")       # 批次10：research_agent tool_end.emit 追加
    # 批次10：紧凑 citation 串
    _citation = None
    if _idx and _tool:
        if _as_of:
            _citation = f"[S{_idx}] {_tool} @ {_as_of}"
        else:
            _citation = f"[S{_idx}] {_tool}"

    row = AiTimelineEvent(
        task_id=task_id,
        stage=stage,
        event_type=_type,
        tool_name=_tool,
        message=_fmt,
        event_json=AiTimelineEvent.dumps_json(event),
        idx=_idx,
        elapsed_s=_elapsed,
        status=_status,
        data_as_of=_as_of,
        citation=_citation,
        ts=event.get("__ts", time.time()),
    )

    from backend.extensions import db  # noqa: PLC0415
    db.session.add(row)
    db.session.commit()


# 全局单例
task_worker = TaskWorker()
