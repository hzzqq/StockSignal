"""锁定 timeout_exec 共享线程池单例 + 超时/异常兜底行为（防回归）。

这些测试确保「带硬边界、不泄漏线程」的并发执行器行为稳定：
- 共享池是进程级单例（线程复用，不随调用新建）
- fn 正常返回结果；fn 抛异常 / 超时返回 None（由调用方兜底），绝不冒泡
"""
import time

import modules.timeout_exec as te


def test_shared_pool_singleton():
    a = te._pool()
    b = te._pool()
    assert a is b
    assert isinstance(a, te.cf.ThreadPoolExecutor)


def test_normal_return():
    assert te.run_with_timeout(lambda: 42) == 42
    assert te.run_with_timeout(lambda: "ok") == "ok"


def test_exception_returns_none():
    assert te.run_with_timeout(lambda: 1 / 0) is None


def test_timeout_returns_none():
    # 硬边界 0.1s，fn sleep 0.5s -> 超时返回 None，不丢线程
    assert te.run_with_timeout(lambda: time.sleep(0.5), timeout=0.1) is None


def test_fast_fn_within_timeout():
    assert te.run_with_timeout(lambda: (time.sleep(0.01) or "done"), timeout=2) == "done"


def test_submit_failure_guarded(monkeypatch):
    # 极端：池 submit 抛异常 -> 兜底 None 不崩
    real_pool = te._pool()

    def _boom(*_a, **_k):
        raise RuntimeError("pool dead")

    monkeypatch.setattr(real_pool, "submit", _boom)
    assert te.run_with_timeout(lambda: 1) is None
