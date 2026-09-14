"""modules/background_tasks 回归测试（无网依赖，mock http_post/http_get）。

覆盖：
- submit_task_with_error：成功 / 401 / 连接失败
- get_task：成功 / 401 哨兵 / 连接失败哨兵（不再吞成 None）
- wait_for_task：成功 / 连接失败快速失败（不空轮询到超时）
- submit_and_wait：统一错误出口（新增能力）

⚠️ 历史缺陷（2026-09-14 修）：早期该模块直接 `import requests` 并调用
``requests.post/get``；#89 共享 Session 优化后改为统一走 ``request_utils.http_post/http_get``。
旧测试一直 patch ``bt.requests.post/get`` —— 由于模块已不再引用 ``bt.requests``，
**patch 完全没生效**，9 个测试等于在真打网络、且永远不会失败。
本版把 patch 目标改成 ``bt.http_post/http_get``（模块级导入名），并额外断言
「mock 确实被调用」，从根上杜绝「patch 没挂上却显示通过」的假绿。
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


def _patch_post(monkeypatch, mock):
    monkeypatch.setattr(bt, "http_post", mock)
    return mock


def _patch_get(monkeypatch, mock):
    monkeypatch.setattr(bt, "http_get", mock)
    return mock


# ── submit_task_with_error ────────────────────────────────
def test_submit_success(no_auth, monkeypatch):
    post = _patch_post(monkeypatch, Mock(return_value=_resp(200, {"status": "ok", "data": {"task_id": "T1"}})))
    tid, err = bt.submit_task_with_error("analyze", {"ticker": "600000"})
    assert post.called, "http_post 未被调用（patch 未生效？）"
    assert tid == "T1"
    assert err is None


def test_submit_401_friendly(no_auth, monkeypatch):
    post = _patch_post(monkeypatch, Mock(return_value=_resp(401, {})))
    tid, err = bt.submit_task_with_error("analyze", {})
    assert post.called
    assert tid is None
    assert "登录已过期" in (err or "")


def test_submit_connection_error(no_auth, monkeypatch):
    post = _patch_post(monkeypatch, Mock(side_effect=requests.exceptions.ConnectionError("refused")))
    tid, err = bt.submit_task_with_error("analyze", {})
    assert post.called
    assert tid is None
    assert "连接失败" in (err or "")


# ── get_task ──────────────────────────────────────────────
def test_get_task_success(no_auth, monkeypatch):
    get = _patch_get(monkeypatch, Mock(return_value=_resp(200, {"status": "ok",
                                                                     "data": {"status": "success", "result": {"a": 1}}})))
    task = bt.get_task("T1")
    assert get.called
    assert task["status"] == "success"
    assert task["result"] == {"a": 1}


def test_get_task_401_sentinel(no_auth, monkeypatch):
    get = _patch_get(monkeypatch, Mock(return_value=_resp(401, {})))
    task = bt.get_task("T1")
    assert get.called
    assert task["status"] == "error"
    assert task["code"] == 401


def test_get_task_connection_error_sentinel(no_auth, monkeypatch):
    get = _patch_get(monkeypatch, Mock(side_effect=requests.exceptions.ConnectionError("refused")))
    task = bt.get_task("T1")
    assert get.called
    assert task["status"] == "error"
    assert task["code"] == 0
    assert "连接失败" in task["error"]


# ── wait_for_task ─────────────────────────────────────────
def test_wait_for_task_success(no_auth, monkeypatch):
    get = _patch_get(monkeypatch, Mock(return_value=_resp(
        200, {"status": "ok", "data": {"status": "success", "result": {"x": 9}}})))
    # 第一次轮询即成功，不应抛异常
    result = bt.wait_for_task("T1", timeout=1.0, poll_interval=0.05)
    assert get.called
    assert result == {"x": 9}


def test_wait_for_task_connection_error_fail_fast(no_auth, monkeypatch):
    get = _patch_get(monkeypatch, Mock(side_effect=requests.exceptions.ConnectionError("refused")))
    # 连接失败应立刻 RuntimeError，而不是空轮询 30s 后报 TimeoutError
    with pytest.raises(RuntimeError, match="连接失败"):
        bt.wait_for_task("T1", timeout=30.0, poll_interval=0.1)
    assert get.called


def test_wait_for_task_task_error(no_auth, monkeypatch):
    get = _patch_get(monkeypatch, Mock(return_value=_resp(
        200, {"status": "ok", "data": {"status": "error", "error": "执行失败"}})))
    with pytest.raises(RuntimeError, match="执行失败"):
        bt.wait_for_task("T1", timeout=1.0, poll_interval=0.05)
    assert get.called


# ── submit_and_wait（新增能力） ───────────────────────────
def test_submit_and_wait_success(no_auth, monkeypatch):
    post = _patch_post(monkeypatch, Mock(return_value=_resp(200, {"status": "ok", "data": {"task_id": "T1"}})))
    get = _patch_get(monkeypatch, Mock(return_value=_resp(200, {"status": "ok",
                                                                  "data": {"status": "success", "result": {"v": 7}}})))
    result, err = bt.submit_and_wait("analyze", {"ticker": "600000"}, timeout=1.0)
    assert post.called and get.called
    assert err is None
    assert result == {"v": 7}


def test_submit_and_wait_submit_fail(no_auth, monkeypatch):
    post = _patch_post(monkeypatch, Mock(return_value=_resp(401, {})))
    result, err = bt.submit_and_wait("analyze", {}, timeout=1.0)
    assert post.called
    assert result is None
    assert "登录已过期" in (err or "")


def test_submit_and_wait_timeout(no_auth, monkeypatch):
    post = _patch_post(monkeypatch, Mock(return_value=_resp(200, {"status": "ok", "data": {"task_id": "T1"}})))
    # 永远 pending → 超时
    get = _patch_get(monkeypatch, Mock(return_value=_resp(200, {"status": "ok",
                                                                  "data": {"status": "pending"}})))
    result, err = bt.submit_and_wait("analyze", {}, timeout=0.3, poll_interval=0.05)
    assert post.called and get.called
    assert result is None
    assert "超时" in (err or "")
