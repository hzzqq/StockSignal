"""并发取数与超时执行器的离线回归测试。

验证本次架构债修复的核心不变量：
1. run_with_timeout 复用**进程级共享有界线程池**（不再每次新建 + 丢弃线程）。
2. 阻塞调用在硬边界内返回 None（UI 不卡死）。
3. fetch_many 真正并发（N 个 sleep 任务总耗时 < 串行之和），且挂起任务得 None。
"""
import time

from modules.timeout_exec import run_with_timeout, _pool, _MAX_WORKERS
from modules.fetch_parallel import fetch_many


def test_run_with_timeout_reuses_shared_pool():
    """共享有界池单例：跨调用复用同一对象，证明不再「每次新建线程池」。"""
    p1 = _pool()
    p2 = _pool()
    assert p1 is p2
    assert p1._max_workers == _MAX_WORKERS


def test_run_with_timeout_fast_returns_value():
    assert run_with_timeout(lambda: 42, timeout=1) == 42


def test_run_with_timeout_hang_returns_none():
    """挂起（sleep）调用在硬边界返回 None，不无限阻塞。"""
    t0 = time.monotonic()
    res = run_with_timeout(lambda: time.sleep(30), timeout=0.3)
    elapsed = time.monotonic() - t0
    assert res is None
    assert elapsed < 1.0, f"应在 ~0.3s 截断，实际 {elapsed:.2f}s"


def test_fetch_many_concurrent_and_bounded():
    """4 个 0.4s 任务并发(max_workers=4)总耗时 < 1.2s（远小于串行 1.6s）。"""
    def slow():
        time.sleep(0.4)
        return 1

    t0 = time.monotonic()
    res = fetch_many([(f"k{i}", slow) for i in range(4)], max_workers=4, timeout=5)
    elapsed = time.monotonic() - t0
    assert elapsed < 1.2, f"应并发执行，实际耗时 {elapsed:.2f}s"
    assert all(v == 1 for v in res.values())
    assert set(res.keys()) == {f"k{i}" for i in range(4)}


def test_fetch_many_hang_yields_none_others_ok():
    """批内一个挂起任务得 None，其余正常返回。"""
    res = fetch_many(
        [("ok", lambda: 7), ("hang", lambda: time.sleep(30))],
        max_workers=2, timeout=0.3,
    )
    assert res["ok"] == 7
    assert res["hang"] is None


def test_fetch_many_task_exception_yields_none():
    """单个任务抛异常被隔离为 None，不拖垮整批。"""
    def boom():
        raise RuntimeError("boom")

    res = fetch_many([("a", lambda: 1), ("b", boom)], max_workers=2, timeout=2)
    assert res["a"] == 1
    assert res["b"] is None
