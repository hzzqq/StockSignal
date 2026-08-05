"""锁定 fetch_parallel.fetch_many 的并发 / 隔离 / 超时行为（防回归）。

确保页面首屏并发预取：
- 多任务并发返回 {key: result}
- 单任务异常 / 超时只让该任务返回 None，不影响同批其他任务
- 并发明显快于串行（可观测的首屏提速收益）
"""
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
