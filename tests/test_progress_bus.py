"""R13：backend.tasks.progress_bus 可观测性 + 静默吞错修复。

- report() 不应因 reporter 抛异常而向上传播；
- 但仍需记录最近一次错误，供 last_error() 暴露（可观测性）；
- 提供 is_registered() / clear() 管理能力。
"""
import pytest

from backend.tasks.progress_bus import (
    register,
    unregister,
    report,
    last_error,
    is_registered,
    clear,
)


@pytest.fixture(autouse=True)
def _clean():
    # 每个用例用独立 task_id 并在结束后清理，避免全局 dict 串扰
    tid = "ut_" + str(id(pytest))
    yield tid
    clear(tid)


def test_report_invokes_reporter():
    calls = []
    register("t_ok", lambda s, m: calls.append((s, m)))
    report("t_ok", "stage_a", "hello")
    assert calls == [("stage_a", "hello")]
    assert is_registered("t_ok")


def test_report_does_not_propagate_and_records_error():
    def boom(stage, message):
        raise RuntimeError("reporter exploded")

    register("t_err", boom)
    # 不应抛异常
    report("t_err", "stage_x", "boom")
    err = last_error("t_err")
    assert err is not None
    assert "RuntimeError" in err
    assert "reporter exploded" in err


def test_unregistered_report_is_noop():
    # 未注册的 task_id 调用 report 不得抛错，也不得记录错误
    report("t_ghost", "s", "m")
    assert last_error("t_ghost") is None


def test_clear_forgets_error_and_registration():
    def boom(stage, message):
        raise ValueError("nope")

    register("t_clear", boom)
    report("t_clear", "s", "m")
    assert last_error("t_clear") is not None
    clear("t_clear")
    assert is_registered("t_clear") is False
    assert last_error("t_clear") is None


def test_reregister_clears_stale_error():
    def boom(stage, message):
        raise RuntimeError("first fail")

    register("t_rereg", boom)
    report("t_rereg", "s", "m")
    assert last_error("t_rereg") is not None

    calls = []
    register("t_rereg", lambda s, m: calls.append((s, m)))
    # 重新注册应清空旧错误
    assert last_error("t_rereg") is None
    report("t_rereg", "s2", "m2")
    assert calls == [("s2", "m2")]
