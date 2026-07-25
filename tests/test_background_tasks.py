"""modules/background_tasks 回归测试（无网依赖，mock requests）。

覆盖：
- submit_task_with_error：成功 / 401 / 连接失败
- get_task：成功 / 401 哨兵 / 连接失败哨兵（不再吞成 None）
- wait_for_task：成功 / 连接失败快速失败（不空轮询到超时）
- submit_and_wait：统一错误出口（新增能力）
"""
from unittest.mock import Mock

import pytest

import modules.background_tasks as bt
import requests


def _resp(status_code, payload):
    m = Mock()
    m.status_code = status_code
    m.json.return_value = payload
    return m


@pytest.fixture
def no_auth(monkeypatch):
    """禁用鉴权头，聚焦任务逻辑。"""
    monkeypatch.setattr(bt, "get_token", lambda: None)
    yield


# ── submit_task_with_error ────────────────────────────────
def test_submit_success(no_auth, monkeypatch):
    monkeypatch.setattr(
        bt.requests, "post",
        Mock(return_value=_resp(200, {"status": "ok", "data": {"task_id": "T1"}})),
    )
    tid, err = bt.submit_task_with_error("analyze", {"ticker": "600000"})
    assert tid == "T1"
    assert err is None


def test_submit_401_friendly(no_auth, monkeypatch):
    monkeypatch.setattr(bt.requests, "post", Mock(return_value=_resp(401, {})))
    tid, err = bt.submit_task_with_error("analyze", {})
    assert tid is None
    assert "登录已过期" in (err or "")


def test_submit_connection_error(no_auth, monkeypatch):
    monkeypatch.setattr(
        bt.requests, "post",
        Mock(side_effect=requests.exceptions.ConnectionError("refused")),
    )
    tid, err = bt.submit_task_with_error("analyze", {})
    assert tid is None
    assert "连接失败" in (err or "")


# ── get_task ──────────────────────────────────────────────
def test_get_task_success(no_auth, monkeypatch):
    monkeypatch.setattr(
        bt.requests, "get",
        Mock(return_value=_resp(200, {"status": "ok",
                                       "data": {"status": "success", "result": {"a": 1}}})),
    )
    task = bt.get_task("T1")
    assert task["status"] == "success"
    assert task["result"] == {"a": 1}


def test_get_task_401_sentinel(no_auth, monkeypatch):
    monkeypatch.setattr(bt.requests, "get", Mock(return_value=_resp(401, {})))
    task = bt.get_task("T1")
    assert task["status"] == "error"
    assert task["code"] == 401


def test_get_task_connection_error_sentinel(no_auth, monkeypatch):
    monkeypatch.setattr(
        bt.requests, "get",
        Mock(side_effect=requests.exceptions.ConnectionError("refused")),
    )
    task = bt.get_task("T1")
    assert task["status"] == "error"
    assert task["code"] == 0
    assert "连接失败" in task["error"]


# ── wait_for_task ─────────────────────────────────────────
def test_wait_for_task_success(no_auth, monkeypatch):
    monkeypatch.setattr(bt.requests, "get", Mock(return_value=_resp(
        200, {"status": "ok", "data": {"status": "success", "result": {"x": 9}}})))
    # 第一次轮询即成功，不应抛异常
    result = bt.wait_for_task("T1", timeout=1.0, poll_interval=0.05)
    assert result == {"x": 9}


def test_wait_for_task_connection_error_fail_fast(no_auth, monkeypatch):
    monkeypatch.setattr(
        bt.requests, "get",
        Mock(side_effect=requests.exceptions.ConnectionError("refused")),
    )
    # 连接失败应立刻 RuntimeError，而不是空轮询 30s 后报 TimeoutError
    with pytest.raises(RuntimeError, match="连接失败"):
        bt.wait_for_task("T1", timeout=30.0, poll_interval=0.1)


def test_wait_for_task_task_error(no_auth, monkeypatch):
    monkeypatch.setattr(bt.requests, "get", Mock(return_value=_resp(
        200, {"status": "ok", "data": {"status": "error", "error": "执行失败"}})))
    with pytest.raises(RuntimeError, match="执行失败"):
        bt.wait_for_task("T1", timeout=1.0, poll_interval=0.05)


# ── submit_and_wait（新增能力） ───────────────────────────
def test_submit_and_wait_success(no_auth, monkeypatch):
    post = Mock(return_value=_resp(200, {"status": "ok", "data": {"task_id": "T1"}}))
    get = Mock(return_value=_resp(200, {"status": "ok",
                                         "data": {"status": "success", "result": {"v": 7}}}))
    monkeypatch.setattr(bt.requests, "post", post)
    monkeypatch.setattr(bt.requests, "get", get)
    result, err = bt.submit_and_wait("analyze", {"ticker": "600000"}, timeout=1.0)
    assert err is None
    assert result == {"v": 7}


def test_submit_and_wait_submit_fail(no_auth, monkeypatch):
    monkeypatch.setattr(bt.requests, "post", Mock(return_value=_resp(401, {})))
    result, err = bt.submit_and_wait("analyze", {}, timeout=1.0)
    assert result is None
    assert "登录已过期" in (err or "")


def test_submit_and_wait_timeout(no_auth, monkeypatch):
    post = Mock(return_value=_resp(200, {"status": "ok", "data": {"task_id": "T1"}}))
    # 永远 pending → 超时
    get = Mock(return_value=_resp(200, {"status": "ok",
                                         "data": {"status": "pending"}}))
    monkeypatch.setattr(bt.requests, "post", post)
    monkeypatch.setattr(bt.requests, "get", get)
    result, err = bt.submit_and_wait("analyze", {}, timeout=0.3, poll_interval=0.05)
    assert result is None
    assert "超时" in (err or "")
