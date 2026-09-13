"""行为契约测试：modules.cache_utils.cached_ttl / clear_cache。

SDD+TDD (self-driving Cycle 72)：spec 冻结于 .workbuddy/specs/cache_ttl_contract.md
覆盖 AC1–AC7。用可调时钟 + fn 调用计数器，锁定 TTL 双检锁的真实行为，
而非"与代码自洽"的假绿。mutation 实验见 spec 末段。
"""
import ast
import time
from unittest.mock import patch

import pytest

from modules.cache_utils import cached_ttl, clear_cache, _CACHE, _CACHE_LOCK


@pytest.fixture(autouse=True)
def _isolate_cache():
    """每个测试前清空共享缓存，避免串扰。"""
    with _CACHE_LOCK:
        _CACHE.clear()
    yield
    with _CACHE_LOCK:
        _CACHE.clear()


def _make_fn(counter, return_value="v"):
    """返回一个计数调用次数的无参 callable。"""
    def fn():
        counter["n"] += 1
        return return_value
    return fn


# ───────────────────────── AC1 首次必算 ─────────────────────────
def test_ac1_first_call_executes_fn_and_caches():
    counter = {"n": 0}
    out = cached_ttl(10, "k1", _make_fn(counter, "first"))
    assert out == "first"
    assert counter["n"] == 1  # 必执行一次


# ───────────────────────── AC2 命中不重算 ─────────────────────────
def test_ac2_within_ttl_no_recompute():
    clock = {"t": 1000.0}
    counter = {"n": 0}
    with patch("modules.cache_utils.time.time", side_effect=lambda: clock["t"]):
        assert cached_ttl(10, "k2", _make_fn(counter, "a")) == "a"
        assert cached_ttl(10, "k2", _make_fn(counter, "a")) == "a"  # 同一时钟，未过期
    assert counter["n"] == 1  # 第二次命中缓存，fn 未重算


# ───────────────────────── AC3 过期重算 ─────────────────────────
def test_ac3_after_ttl_recomputes():
    clock = {"t": 2000.0}
    counter = {"n": 0}
    with patch("modules.cache_utils.time.time", side_effect=lambda: clock["t"]):
        assert cached_ttl(10, "k3", _make_fn(counter, "x")) == "x"
        clock["t"] = 2000.0 + 11  # 推进 11s > ttl(10)
        assert cached_ttl(10, "k3", _make_fn(counter, "y")) == "y"
    assert counter["n"] == 2  # 过期后重算


# ───────────────────────── AC4 ttl<=0 永远 miss ─────────────────────────
def test_ac4_ttl_zero_always_recomputes():
    clock = {"t": 3000.0}
    counter = {"n": 0}
    with patch("modules.cache_utils.time.time", side_effect=lambda: clock["t"]):
        assert cached_ttl(0, "k4", _make_fn(counter, "p")) == "p"
        assert cached_ttl(0, "k4", _make_fn(counter, "p")) == "p"
    assert counter["n"] == 2  # ttl<=0 不特判，每次都 miss


# ───────────────────────── AC5 值一致性 ─────────────────────────
def test_ac5_hit_value_matches_fresh():
    clock = {"t": 4000.0}
    counter = {"n": 0}
    with patch("modules.cache_utils.time.time", side_effect=lambda: clock["t"]):
        first = cached_ttl(10, "k5", _make_fn(counter, [1, 2, 3]))
        second = cached_ttl(10, "k5", _make_fn(counter, [9, 9, 9]))
    assert second == first  # 命中返回缓存，不返回第二次传入的"假"值


# ───────────────────────── AC6 并发不改正确性 ─────────────────────────
def test_ac6_concurrent_calls_all_return_real_value():
    import threading
    counter = {"n": 0}
    results = []
    lock = threading.Lock()

    def worker():
        r = cached_ttl(10, "k6", _make_fn(counter, "shared"))
        with lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 每个调用都拿到 fn 的真实返回值（不返回 None/旧占位）
    assert all(r == "shared" for r in results)
    assert len(results) == 8


# ───────────────────────── AC7 clear_cache 诚实计数 ─────────────────────────
def test_ac7_clear_cache_returns_real_count_and_forces_recompute():
    clock = {"t": 5000.0}
    counter = {"n": 0}
    with patch("modules.cache_utils.time.time", side_effect=lambda: clock["t"]):
        cached_ttl(10, "k7a", _make_fn(counter, "1"))
        cached_ttl(10, "k7b", _make_fn(counter, "2"))
        removed = clear_cache()
        assert removed == 2  # 诚实返回真实条目数
        # 清空后该 key 再次调用必重算
        assert cached_ttl(10, "k7a", _make_fn(counter, "3")) == "3"
    assert counter["n"] == 3  # 2 初次 + 1 清后重算


# ───────────────────────── 源码层防回退：双检锁结构 ─────────────────────────
def test_source_double_check_lock_structure():
    """锁内读 + 锁外算 + 锁内写 三段必须齐全，防有人改成全程无锁/只锁写。"""
    src = open(__import__("modules.cache_utils", fromlist=["x"]).__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "cached_ttl")
    body = ast.dump(func)
    # 必须出现两次 `with _CACHE_LOCK`（读 + 写）
    assert body.count("_CACHE_LOCK") >= 2, "cached_ttl 必须含双 with _CACHE_LOCK（双检锁）"
    # 必须在锁外（函数结构里）调用 fn()
    calls_fn = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "fn"
        for n in ast.walk(func)
    )
    assert calls_fn, "cached_ttl 必须调用 fn()"
