"""
backend/tasks/__init__.py
后台任务队列入口。
"""
from __future__ import annotations
from .worker import task_worker

__all__ = ["task_worker"]
