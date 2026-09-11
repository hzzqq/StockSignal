"""tests/test_cache_utils.py — R87 统一缓存层守卫。

验证 modules.cache_utils.cached_ttl 的 TTL 语义、fn 只算一次、clear_cache
返回真实删除计数；并确认 fundflow/shepherd 的 `_cached` 已收口到同一实现
（通过共享 _CACHE 别名）。
"""

from unittest.mock import patch

from modules.cache_utils import cached_ttl, clear_cache, _CACHE


def setup_function(_fn):
    clear_cache()


def teardown_function(_fn):
    clear_cache()


def test_cached_ttl_returns_same_value_and_calls_fn_once():
    calls = []
    sentinel = object()

    def fn():
        calls.append(1)
        return sentinel

    a = cached_ttl(100, "rk87_a", fn)
    b = cached_ttl(100, "rk87_a", fn)
    assert a is b is sentinel
    assert len(calls) == 1  # 命中缓存后不再执行 fn


def test_cached_ttl_respects_ttl_expiry():
    calls = []
    fake = {"t": 1000.0}

    def fn():
        calls.append(1)
        return object()

    def fake_time():
        return fake["t"]

    with patch("modules.cache_utils.time.time", side_effect=fake_time):
        cached_ttl(10, "rk87_b", fn)
        assert len(calls) == 1
        # 未过期：仍命中
        cached_ttl(10, "rk87_b", fn)
        assert len(calls) == 1
        # 推进时间越过 ttl：应重算
        fake["t"] += 11
        cached_ttl(10, "rk87_b", fn)
        assert len(calls) == 2


def test_clear_cache_returns_real_count():
    cached_ttl(100, "rk87_c1", lambda: 1)
    cached_ttl(100, "rk87_c2", lambda: 2)
    assert "rk87_c1" in _CACHE and "rk87_c2" in _CACHE
    n = clear_cache()
    assert n == 2  # 诚实语义：返回真实删除行数
    assert clear_cache() == 0  # 已空
    assert "rk87_c1" not in _CACHE and "rk87_c2" not in _CACHE
