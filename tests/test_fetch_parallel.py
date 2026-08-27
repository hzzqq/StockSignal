"""fetch_parallel 并发取数：异常隔离 / 整批超时护栏 / as-e 绑定回归。

证据优先——全部用纯函数构造可控的成功 / 失败 / 慢任务，不依赖真实网络：

- 单任务异常被隔离：其余任务正常返回，失败 key 为 None，key 集合与入参一致；
- 整批超时：超时任务 key 为 None，已完成任务仍返回正确值；
- 空任务列表返回 {}；
- 信号量限流：并发峰值不超过 max_workers；
- 回归（R-as-e）：``_safe`` 在任务抛异常时不得因 ``e`` 未绑定而再抛 NameError，
  必须正确记录异常并返回 None（覆盖 2026-08-27 修复的 as-e 转换器陷阱）。
"""
import logging
import threading
import time

import pytest

from modules.fetch_parallel import fetch_many, _safe


def test_empty_returns_empty_dict():
    assert fetch_many([]) == {}


def test_safe_isolates_exception_without_nameerror(caplog):
    """R-as-e 回归：此前 except 把 `as e:` 注释掉，真实异常会触发 NameError。"""
    with caplog.at_level(logging.WARNING):
        result = _safe(lambda: 1 / 0)
    assert result is None
    # 必须正确记录异常，而非因未绑定 e 而抛 NameError
    assert any("处理异常" in r.message for r in caplog.records), caplog.text
    assert any("division by zero" in r.message for r in caplog.records), caplog.text


def test_fetch_many_exception_isolation():
    def boom():
        raise RuntimeError("boom")

    def ok():
        return 42

    tasks = [("a", ok), ("b", boom), ("c", ok)]
    out = fetch_many(tasks, max_workers=3, timeout=5)
    assert set(out.keys()) == {"a", "b", "c"}
    assert out["a"] == 42
    assert out["c"] == 42
    assert out["b"] is None  # 单任务异常被隔离，预填 None 兜底


def test_fetch_many_batch_timeout_isolates_slow_task():
    def fast():
        return "fast"

    def slow():
        time.sleep(3)
        return "slow"

    out = fetch_many([("fast", fast), ("slow", slow)], max_workers=2, timeout=1)
    assert out["fast"] == "fast"
    assert out["slow"] is None


def test_fetch_many_keys_complete_on_timeout():
    def slow():
        time.sleep(2)
        return "x"

    tasks = [("k%d" % i, slow) for i in range(3)]
    out = fetch_many(tasks, max_workers=3, timeout=1)
    assert set(out.keys()) == {"k0", "k1", "k2"}
    assert all(v is None for v in out.values())


def test_concurrency_capped_by_semaphore():
    counter = {"active": 0, "peak": 0}
    lock = threading.Lock()

    def work(i):
        with lock:
            counter["active"] += 1
            counter["peak"] = max(counter["peak"], counter["active"])
        time.sleep(0.05)
        with lock:
            counter["active"] -= 1
        return i

    tasks = [("t%d" % i, (lambda i=i: work(i))) for i in range(20)]
    out = fetch_many(tasks, max_workers=4, timeout=10)
    assert len(out) == 20
    assert counter["peak"] <= 4
