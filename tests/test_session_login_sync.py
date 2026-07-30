"""
回归测试：init_session_state 必须将已恢复的 token 回写 URL query_params。

背景（刷新保持登录回归）：session.init_session_state 的 docstring 承诺「立刻把 token
回写 URL query_params」，但旧实现从未调用 _sync_query_params——仅凭 localStorage 兜底
恢复的 token 始终未同步回 URL，一旦 localStorage 也被清便直接掉登录，且违背「URL 为登录态
主存储」的契约。本测试用 AppTest 模拟「session_state 已有 token、URL 无 token」的场景，
断言 init_session_state 后 URL query_params 被补回 token。
"""
import os

from streamlit.testing.v1 import AppTest


STUB = os.path.join(os.path.dirname(__file__), "_stubs", "login_sync_stub.py")


def test_init_session_state_resyncs_token_to_url():
    at = AppTest.from_file(STUB)
    # 模拟 token 已存在于 session_state（如 localStorage 兜底已恢复），但 URL 无 token
    at.session_state["auth_token"] = "tok-abc-123"
    at.run()
    # Streamlit query_params 将值以列表形式存储，故断言列表形态
    assert at.query_params.get("token") == ["tok-abc-123"]


def test_init_session_state_no_token_no_url_write():
    at = AppTest.from_file(STUB)
    # 未登录场景：不应往 URL 写入空 token
    at.run()
    assert at.query_params.get("token") in (None, "")
