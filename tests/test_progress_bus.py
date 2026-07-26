"""R13 + R1/R2/R3/R5/R6：progress_bus 可观测性、静默吞错修复、有界内存、未知 id 安全、并发安全。

- report() 不应因 reporter 抛异常而向上传播；
- 但仍需记录最近一次错误，供 last_error() 暴露（可观测性）；
- 提供 is_registered() / clear() 管理能力；
- 新增有界事件存储（MAX_EVENTS 上限）、get_events()/get_status() 安全查询。
"""
import threading

import pytest

from backend.tasks.progress_bus import (
    register,
    unregister,
    report,
    last_error,
    is_registered,
    clear,
    get_events,
    get_status,
    MAX_EVENTS,
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


# ---------------------------------------------------------------------------
# R1 / R2 / R3 / R5 / R6：有界内存（事件上限）、未知 id 安全、并发安全、可观测性
# ---------------------------------------------------------------------------


def test_publish_then_read_back_event():
    """report() 发布的进度更新应可被 get_events() 读回（新增事件存储能力）。"""
    clear("t_pub")
    register("t_pub", lambda s, m: None)
    report("t_pub", "stage_a", "hello")
    events = get_events("t_pub")
    assert len(events) == 1
    assert events[0]["stage"] == "stage_a"
    assert events[0]["message"] == "hello"


def test_unknown_id_safe_no_keyerror():
    """未知 task_id 的查询不应抛 KeyError，返回安全默认值（R2）。"""
    assert get_events("never_existed_id") == []
    status = get_status("never_existed_id")
    assert status["registered"] is False
    assert status["event_count"] == 0
    assert status["last_event"] is None
    assert status["last_error"] is None
    # last_error 对未知 id 同样返回 None，不抛异常
    assert last_error("never_existed_id") is None


def test_event_cap_keeps_only_last_n():
    """发布超过上限的事件时，仅保留最近 MAX_EVENTS 条，避免无上限增长（R1）。"""
    clear("t_cap")
    register("t_cap", lambda s, m: None)
    total = MAX_EVENTS + 50
    for i in range(total):
        report("t_cap", "s", f"m{i}")
    events = get_events("t_cap")
    assert len(events) == MAX_EVENTS
    # 仅保留最后 N 条
    assert events[-1]["message"] == f"m{total - 1}"
    assert events[0]["message"] == f"m{total - MAX_EVENTS}"
    # get_status 反映 event_count 也受上限约束
    assert get_status("t_cap")["event_count"] == MAX_EVENTS


def test_concurrent_publish_no_corruption():
    """多线程并发 publish 不应破坏状态或抛异常（R3 并发安全）。"""
    clear("t_conc")
    register("t_conc", lambda s, m: None)

    def worker(wid):
        for j in range(10):
            report("t_conc", f"w{wid}", f"m{j}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 8 线程 * 10 次 = 80 条，未触及上限，应全部保留且不重复/丢失
    events = get_events("t_conc")
    assert len(events) == 80
    assert get_status("t_conc")["event_count"] == 80
