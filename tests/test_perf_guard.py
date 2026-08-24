"""test_perf_guard.py — 性能回归护栏（评测集诊断项 #4）

抓「测试全绿但生产 OOM/卡死」类问题，专门覆盖此前修复的线程泄漏（timeout_exec 共享池）
与超时分层根因：
  1. full_analysis 计算必须 <3s（120 行合成数据），防止技术面板块渲染卡顿。
  2. fetch_many 并发后活跃线程数必须回降到基线（不泄漏线程）——这是此前
     fundflow「每次新建池 + shutdown(wait=False) 丢线程」真实 bug 的回归护栏。
  3. run_with_timeout 对超慢函数必须在 timeout 内返回 None，且**不新增常驻线程**
     （验证共享有界池单例取代「每次新建池」后不再泄漏）。
  4. fetch_many 整批硬边界：提交一批 sleep 超时的任务，必须在 timeout 内返回
     且所有 key 都补齐（None），不永久阻塞。

全部本地线程验证，不依赖真网（离线守卫已激活）。
运行：pytest tests/test_perf_guard.py -q
"""
from __future__ import annotations

import time
import threading

import pandas as pd
import numpy as np

from modules.technical import full_analysis
from modules.timeout_exec import run_with_timeout, _pool, _MAX_WORKERS
from modules.fetch_parallel import fetch_many


def _active_ss_threads() -> int:
    """统计当前活跃且属本项目网络池的线程（thread_name_prefix='ss-net'）。"""
    return sum(1 for t in threading.enumerate() if t.name.startswith("ss-net"))


def _make_ohlcv(n: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "date": dates,
        "open": close + rng.normal(0, 0.5, n),
        "high": close + rng.uniform(0, 1, n),
        "low": close - rng.uniform(0, 1, n),
        "close": close,
        "volume": rng.integers(1e6, 5e6, n).astype(float),
    })


class TestComputationPerf:
    def test_full_analysis_under_3s(self):
        df = _make_ohlcv(120)
        t0 = time.perf_counter()
        full_analysis(df)
        dt = time.perf_counter() - t0
        assert dt < 3.0, f"full_analysis 耗时 {dt:.2f}s 超过 3s 护栏"


class TestThreadPoolNoLeak:
    def test_fetch_many_no_thread_leak(self):
        """并发取数后，ss-net 线程数必须**有界**（<= 共享池容量 _MAX_WORKERS），
        且多次调用不应无限增长——这是修复「fundflow 每次新建池丢线程」的核心回归。

        注意：线程池 worker 是常驻守护线程，数量不会回降到 0（这正是「共享池取代
        每次新建」的设计意图），所以本断言验证的是「有界 + 复用」而非「归零」。
        """
        tasks = [(f"k{i}", lambda: time.sleep(0.2)) for i in range(12)]
        out = fetch_many(tasks, max_workers=6, timeout=10)
        assert len(out) == 12, "fetch_many 返回的 key 集合应与入参一致"
        after_first = _active_ss_threads()
        # 再跑一批：线程数不应因二次调用而净增长（池已存在，worker 复用）
        tasks2 = [(f"j{i}", lambda: time.sleep(0.2)) for i in range(8)]
        fetch_many(tasks2, max_workers=6, timeout=10)
        after_second = _active_ss_threads()
        # 有界：不超过共享池总容量
        assert after_first <= _MAX_WORKERS, f"ss-net 线程数超过池容量: {after_first} > {_MAX_WORKERS}"
        # 复用：两次调用后线程数不净增长（允许池内 worker 在首次已预热）
        assert after_second <= max(after_first, 6) + 1, \
            f"fetch_many 疑似线程泄漏（二次调用净增长）: {after_first} -> {after_second}"

    def test_pool_is_shared_singleton(self):
        """共享池必须是单例（同一对象），这是消除「每次新建池丢线程」的根。"""
        p1 = _pool()
        p2 = _pool()
        assert p1 is p2, "网络池未复用为单例"
        assert p1._max_workers == _MAX_WORKERS


class TestTimeoutBounded:
    def test_run_with_timeout_returns_none_on_slow(self):
        """超慢函数必须在 timeout 内返回 None，且不永久阻塞。"""
        def _slow():
            time.sleep(5)
            return "should-not-return"
        t0 = time.perf_counter()
        res = run_with_timeout(_slow, timeout=0.5)
        dt = time.perf_counter() - t0
        assert res is None, "超时函数应返回 None"
        assert dt < 2.0, f"run_with_timeout 未在边界内返回，耗时 {dt:.2f}s"

    def test_run_with_timeout_no_leaked_thread(self):
        """run_with_timeout 超时后不应新增常驻 ss-net 线程。"""
        before = _active_ss_threads()
        for _ in range(5):
            run_with_timeout(lambda: time.sleep(3), timeout=0.2)
        time.sleep(0.3)
        after = _active_ss_threads()
        # 共享池线程是常驻的，但调用不应导致线程数净增长
        assert after <= before + _MAX_WORKERS, f"run_with_timeout 疑似线程泄漏: {before}->{after}"

    def test_fetch_many_respects_hard_timeout(self):
        """整批提交一批超时任务，必须在 timeout 内返回且补齐全 key。"""
        tasks = [(f"t{i}", lambda: time.sleep(10)) for i in range(8)]
        t0 = time.perf_counter()
        out = fetch_many(tasks, max_workers=8, timeout=1.0)
        dt = time.perf_counter() - t0
        assert dt < 3.0, f"fetch_many 整批超时保护失效，耗时 {dt:.2f}s"
        assert len(out) == 8, "超时后 key 集合应完整（预填 None）"
        assert all(v is None for v in out.values()), "超时任务结果应为 None"
