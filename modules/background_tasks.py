"""
modules/background_tasks.py
---------------------------
前端调用后台任务 API 的客户端封装。
个股分析、多股对比、AI 咨询统一走这里提交后台任务，避免阻塞 Streamlit 主线程。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests
import streamlit as st

from modules.session import API_BASE, get_token


_TIMEOUT = 8


def _headers() -> Dict[str, str]:
    token = get_token()
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def submit_task_with_error(task_type: str, payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """提交任务，返回 (task_id, error_message)。成功时 error_message 为 None。"""
    try:
        resp = requests.post(
            f"{API_BASE}/api/tasks/",
            json={"type": task_type, "payload": payload},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") == "ok":
                return body.get("data", {}).get("task_id"), None
            return None, body.get("message") or "提交失败"
        if resp.status_code in (401, 403):
            return None, "登录已过期，请重新登录"
        if resp.status_code == 404:
            return None, "后台服务不可用（404）"
        if resp.status_code >= 500:
            return None, f"后台服务异常（HTTP {resp.status_code}）"
        return None, f"提交失败（HTTP {resp.status_code}）"
    except requests.exceptions.ConnectionError as e:
        return None, f"连接失败：{e}"
    except Exception as e:
        return None, f"提交异常：{e}"


def submit_task(task_type: str, payload: Dict[str, Any]) -> Optional[str]:
    """提交任务，返回 task_id；失败返回 None（不污染页面，由调用方处理）。"""
    task_id, _ = submit_task_with_error(task_type, payload)
    return task_id


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """查询任务状态。"""
    try:
        resp = requests.get(
            f"{API_BASE}/api/tasks/{task_id}",
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") == "ok":
                return body.get("data")
    except Exception:
        pass
    return None


def poll_task(task_id: str, max_wait: float = 0.5) -> Optional[Dict[str, Any]]:
    """快速轮询一次任务，返回最新状态；不阻塞。"""
    t0 = time.time()
    while time.time() - t0 < max_wait:
        task = get_task(task_id)
        if task and task.get("status") in ("success", "error"):
            return task
        time.sleep(0.05)
    return get_task(task_id)


def wait_for_task(task_id: str, timeout: float = 30.0, poll_interval: float = 0.3) -> Optional[Dict[str, Any]]:
    """同步等待任务完成（用于仍需要立即结果的场景）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        task = get_task(task_id)
        if task:
            if task.get("status") == "success":
                return task.get("result")
            if task.get("status") == "error":
                raise RuntimeError(task.get("error") or "任务执行失败")
            if task.get("status") in ("pending", "running"):
                time.sleep(poll_interval)
                continue
        time.sleep(poll_interval)
    raise TimeoutError("等待任务结果超时")
