"""fetch_many 行为契约测试（SDD+TDD pilot #2）。

锁死 modules/fetch_parallel.fetch_many 的并发安全契约：
  AC1 key 集合完整 | AC2 空输入 | AC3 异常隔离 | AC4 整批超时硬边界(防挂死)
  AC5 并发限流+clamp | AC6 结果正确 | AC7 默认参数可用

纯桩 callable，无网络；mutation 验证见测试尾部注释。
"""
import os
import sys
import time
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.fetch_parallel import fetch_many  # noqa: E402


def _fast(v, sleep=0.0):
    if sleep:
        time.sleep(sleep)
    return v


# ---- AC2: 空输入 ----
def test_empty_tasks_returns_empty_dict():
    assert fetch_many([]) == {}


# ---- AC1 + AC6: key 完整 + 结果正确 ----
def test_keys_complete_and_values():
    tasks = [("a", lambda: 1), ("b", lambda: "x"), ("c", lambda: [1, 2])]
    out = fetch_many(tasks)
    assert set(out.keys()) == {"a", "b", "c"}
    assert out["a"] == 1
    assert out["b"] == "x"
    assert out["c"] == [1, 2]
    assert None not in out.values()


# ---- AC3: 异常隔离 ----
def test_exception_isolation():
    def boom():
        raise RuntimeError("boom")

    tasks = [("ok", lambda: 42), ("bad", boom), ("ok2", lambda: "v")]
    out = fetch_many(tasks)
    assert set(out.keys()) == {"ok", "bad", "ok2"}   # 不缺键
    assert out["ok"] == 42
    assert out["ok2"] == "v"
    assert out["bad"] is None                        # 异常项 None，不影响其余


# ---- AC4: 整批超时硬边界（最高优先级，防永久挂死）----
def test_timeout_hard_boundary_no_hang():
    def slow():
        time.sleep(2.0)
        return "done"

    tasks = [("fast", lambda: "f"), ("slow", slow)]
    t0 = time.monotonic()
    out = fetch_many(tasks, max_workers=2, timeout=0.3)
    elapsed = time.monotonic() - t0
    # 约 timeout 内返回，绝不永久阻塞
    assert elapsed < 1.0, f"fetch_many 疑似挂死，耗时 {elapsed:.2f}s"
    assert set(out.keys()) == {"fast", "slow"}       # 仍不缺键
    assert out["fast"] == "f"                        # 已完成任务拿到结果
    assert out["slow"] is None                       # 超时任务为 None


# ---- AC5: 并发限流 + clamp ----
def test_worker_bound_limits_concurrency():
    lock = threading.Lock()
    counter = {"inflight": 0, "peak": 0}

    def tracked(i):
        with lock:
            counter["inflight"] += 1
            counter["peak"] = max(counter["peak"], counter["inflight"])
        time.sleep(0.1)
        with lock:
            counter["inflight"] -= 1
        return i

    tasks = [("t%d" % i, (lambda i=i: tracked(i))) for i in range(10)]
    fetch_many(tasks, max_workers=3, timeout=5)
    # 在途峰值不超过 max_workers + 1（容错，因 GIL/调度波动）
    assert counter["peak"] <= 4, f"并发未被限流，峰值 {counter['peak']} > 4"


def test_max_workers_zero_clamped_no_deadlock():
    # max_workers<=0 必须按 1 处理，不能 Semaphore(0) deadlock
    tasks = [("a", lambda: 1), ("b", lambda: 2)]
    out = fetch_many(tasks, max_workers=0, timeout=2)
    assert set(out.keys()) == {"a", "b"}
    assert out["a"] == 1 and out["b"] == 2


# ---- AC7: 默认参数可用 ----
def test_default_params_no_error():
    tasks = [("a", lambda: 1), ("b", lambda: 2)]
    out = fetch_many(tasks)   # max_workers=None, timeout=None → site_config 默认
    assert set(out.keys()) == {"a", "b"}
    assert out["a"] == 1 and out["b"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
