"""_verify_token 行为契约测试 (SDD+TDD · Cycle 77).

锁死 token 校验的三种返回值语义：
  - user dict       : 有效
  - _TOKEN_INVALID  : 401/403 或 200 但 status!=ok -> 应清登录态（明确失效）
  - None            : 网络错/超时/5xx/json 解析失败 -> 瞬态, 保留登录态（不得误踢）

通过 monkeypatch modules.session.http_get 注入假响应，不依赖真实后端/网络。
"""
import modules.session as session
from modules.session import _TOKEN_INVALID, _verify_token

SENTINEL = _TOKEN_INVALID


class _FakeResp:
    def __init__(self, status_code=200, payload=None, raise_on_json=False):
        self.status_code = status_code
        self._payload = payload
        self._raise = raise_on_json

    def json(self):
        if self._raise:
            raise ValueError("malformed json body")
        return self._payload


def _patch_http(monkeypatch, resp):
    monkeypatch.setattr(session, "http_get", lambda *a, **k: resp)


# AC1: 200 + status=ok + 扁平 user(username) -> 返回 user dict
def test_ac1_valid_flat_user(monkeypatch):
    user = {"username": "alice", "uid": 7, "role": "user"}
    _patch_http(monkeypatch, _FakeResp(200, {"status": "ok", "data": user}))
    assert _verify_token("tok") == user


# AC2: 200 + status=ok + 嵌套 user.username -> 返回内层 user dict
def test_ac2_valid_nested_user(monkeypatch):
    inner = {"username": "bob", "uid": 9}
    _patch_http(monkeypatch, _FakeResp(200, {"status": "ok", "data": {"user": inner}}))
    assert _verify_token("tok") == inner


# AC3: 401/403 -> _TOKEN_INVALID（明确失效）
def test_ac3_401_403_invalid(monkeypatch):
    for code in (401, 403):
        _patch_http(monkeypatch, _FakeResp(code, {"status": "error"}))
        assert _verify_token("tok") is SENTINEL


# AC4: 200 但 status != ok -> _TOKEN_INVALID（明确失效）
def test_ac4_200_but_not_ok(monkeypatch):
    _patch_http(monkeypatch, _FakeResp(200, {"status": "error", "data": {"username": "x"}}))
    assert _verify_token("tok") is SENTINEL


# AC5: 5xx -> None（瞬态, 保留登录）
def test_ac5_5xx_transient(monkeypatch):
    _patch_http(monkeypatch, _FakeResp(500, {"status": "error"}))
    assert _verify_token("tok") is None


# AC6: http_get 抛异常(网络/超时) -> None（核心容错分支: 后端抖动不得误踢）
def test_ac6_network_exception_transient(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("backend unreachable")
    monkeypatch.setattr(session, "http_get", _boom)
    assert _verify_token("tok") is None


# AC7: 200 但 json 解析失败 -> None（瞬态）
def test_ac7_malformed_json_transient(monkeypatch):
    _patch_http(monkeypatch, _FakeResp(200, payload={}, raise_on_json=True))
    assert _verify_token("tok") is None
