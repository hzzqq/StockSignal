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

from modules.session import API_BASE, get_token


_TIMEOUT = 8

# 连接层失败哨兵：与 401/403 哨兵同构（{"status":"error","code":int,"error":str}），
# 供 wait_for_task 立即失败，而非把连接失败当作「未就绪」空轮询到超时。
_CONNECTION_ERROR = {"status": "error", "code": 0, "error": "后台服务连接失败，请确认服务已启动"}


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
    """查询任务状态。

    鉴权失效（401/403）不再哑返回 None，而是返回带 ``code`` 的哨兵 dict
    ``{"status":"error","code":401,"error":"登录已过期..."}``，让上层
    （wait_for_task / submit_and_wait）能据此立即提示重新登录，而非空轮询到超时。
    其余非 200（网络/5xx）仍返回 None，由调用方走超时/重试逻辑。
    """
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
        if resp.status_code in (401, 403):
            return {
                "status": "error",
                "code": resp.status_code,
                "error": "登录已过期，请重新登录",
            }
    except requests.exceptions.ConnectionError:
        # 后端未监听 / 连接被拒 → 明确失败，让 wait_for_task 立即失败，
        # 不再把「连接不上」误当作「任务未就绪」空轮询到超时。
        return dict(_CONNECTION_ERROR)
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


def submit_and_wait(task_type: str, payload: Dict[str, Any],
                    timeout: float = 30.0, poll_interval: float = 0.3) -> tuple[Optional[Any], Optional[str]]:
    """提交任务并同步等待结果，统一错误出口。

    返回 ``(result, error)``：``error`` 为 ``None`` 表示成功；否则为可读错误文案。
    相比分别调用 ``submit_task`` + ``wait_for_task``，本函数把五类错误收敛为单一出口：
    提交失败 / 鉴权失效(401/403) / 连接失败 / 任务执行失败 / 等待超时，
    调用方只需判断 ``error is None``，无需再 try 多种异常或自行区分空返回值。

    :param task_type: 任务类型
    :param payload: 任务参数
    :param timeout: 最长等待秒数
    :param poll_interval: 轮询间隔秒数
    :return: (结果对象, 错误文案)
    """
    task_id, err = submit_task_with_error(task_type, payload)
    if err:
        return None, err
    if not task_id:
        return None, "提交失败：未返回任务 ID"
    try:
        result = wait_for_task(task_id, timeout=timeout, poll_interval=poll_interval)
        return result, None
    except (RuntimeError, TimeoutError) as e:
        return None, str(e)


# =====================================================================
# 星辰 AI 对话历史持久化（后端按用户维度）
# =====================================================================
def get_chat_history() -> list:
    """获取当前登录用户的星辰 AI 对话历史。失败/无记录返回空列表。"""
    try:
        resp = requests.get(
            f"{API_BASE}/api/chat/history",
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") == "ok":
                msgs = body.get("data", {}).get("messages")
                if isinstance(msgs, list):
                    return msgs
    except Exception:
        pass
    return []


def save_chat_history(messages: list) -> bool:
    """保存当前登录用户的星辰 AI 对话历史。成功返回 True，失败返回 False。"""
    try:
        resp = requests.post(
            f"{API_BASE}/api/chat/history",
            json={"messages": messages},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        return resp.status_code == 200 and resp.json().get("status") == "ok"
    except Exception:
        return False
