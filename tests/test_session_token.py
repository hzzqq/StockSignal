"""_me_response_valid 纯逻辑测试（无网络 / 不调用 requests）。

覆盖 /api/auth/me 的 `data`（user 对象）有效性判定：
- username / uid / 嵌套 user.username 均视为已登录有效证明
- 空字符串、None、空 dict、非预期嵌套结构视为无效
"""
from modules.session import _me_response_valid


def test_username_valid():
    assert _me_response_valid({"username": "x"}) is True


def test_uid_valid():
    assert _me_response_valid({"uid": "123"}) is True


def test_nested_user_username_valid():
    assert _me_response_valid({"user": {"username": "x"}}) is True


def test_empty_username_and_uid_invalid():
    assert _me_response_valid({"username": "", "uid": ""}) is False


def test_none_invalid():
    assert _me_response_valid(None) is False


def test_empty_dict_invalid():
    assert _me_response_valid({}) is False


def test_wrapped_data_invalid():
    # 真实响应里 user 在 body.data，而非 data.data 再套一层；
    # 此处 {"data": {"username": "x"}} 是 data 自身含 data 键，不算有效登录证明
    assert _me_response_valid({"data": {"username": "x"}}) is False
