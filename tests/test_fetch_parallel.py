"""锁定 fetch_parallel.fetch_many 的并发 / 隔离 / 超时行为（防回归）。

确保页面首屏并发预取：
- 多任务并发返回 {key: result}
- 单任务异常 / 超时只让该任务返回 None，不影响同批其他任务
- 并发明显快于串行（可观测的首屏提速收益）
"""
import threading
import time

import modules.fetch_parallel as fp


def test_empty_tasks():
    assert fp.fetch_many([]) == {}


def test_normal_dict():
    tasks = [("a", lambda: 1), ("b", lambda: 2)]
    assert fp.fetch_many(tasks) == {"a": 1, "b": 2}


def test_exception_isolated():
    tasks = [("ok", lambda: 42), ("bad", lambda: 1 / 0), ("ok2", lambda: "x")]
    out = fp.fetch_many(tasks)
    assert out["ok"] == 42
    assert out["bad"] is None
    assert out["ok2"] == "x"


def test_timeout_isolated():
    tasks = [("slow", lambda: time.sleep(1.0)), ("fast", lambda: "done")]
    out = fp.fetch_many(tasks, timeout=0.1)
    assert out["slow"] is None
    assert out["fast"] == "done"


def test_concurrency_faster_than_serial():
    def mk(d):
        return lambda: (time.sleep(d) or d)

    tasks = [("t1", mk(0.3)), ("t2", mk(0.3)), ("t3", mk(0.3))]
    t0 = time.time()
    out = fp.fetch_many(tasks, timeout=3)
    dt = time.time() - t0
    assert out == {"t1": 0.3, "t2": 0.3, "t3": 0.3}
    # 三个各 0.3s，串行需 ~0.9s；并发应在远小于此完成
    assert dt < 0.8


def test_keys_complete_on_timeout():
    """整批超时后返回的 key 集合必须与入参一致（未完成项预填 None，不缺键）。

    回归护栏：调用方普遍写 res.get(k) / res[k]，缺键会直接 KeyError 崩页。
    """
    tasks = [("fast", lambda: 1), ("slow", lambda: time.sleep(2.0))]
    out = fp.fetch_many(tasks, timeout=0.2)
    assert set(out) == {"fast", "slow"}
    assert out["slow"] is None


def test_blocking_task_does_not_hang_batch():
    """核心回归：某任务永久阻塞时，整批必须在 timeout 内返回而不是挂死。

    历史 bug：as_completed() 未传 timeout -> 无限等待，后面的
    fut.result(timeout=...) 根本执行不到，所谓超时保护形同虚设。
    """
    stop = threading.Event()
    try:
        tasks = [("ok", lambda: "v"), ("blocked", lambda: stop.wait())]
        t0 = time.time()
        out = fp.fetch_many(tasks, timeout=0.3)
        dt = time.time() - t0
        assert dt < 2.0, f"整批未在硬边界内返回，耗时 {dt:.1f}s（超时保护失效）"
        assert out["ok"] == "v"
        assert out["blocked"] is None
    finally:
        stop.set()      # 释放共享池线程，避免污染后续用例


def test_max_workers_limits_concurrency():
    """max_workers 必须真实限流（历史上该参数被静默忽略）。"""
    running = {"cur": 0, "peak": 0}
    lock = threading.Lock()

    def job():
        with lock:
            running["cur"] += 1
            running["peak"] = max(running["peak"], running["cur"])
        time.sleep(0.15)
        with lock:
            running["cur"] -= 1
        return 1

    tasks = [(f"t{i}", job) for i in range(8)]
    out = fp.fetch_many(tasks, max_workers=2, timeout=5)
    assert len(out) == 8
    assert running["peak"] <= 2, f"并发峰值 {running['peak']} 超过 max_workers=2"
