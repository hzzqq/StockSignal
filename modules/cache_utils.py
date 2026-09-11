"""统一 TTL 缓存工具（R87）。

收口 ``fundflow`` / ``shepherd`` 等多处散落的 ``_cached`` 实现，提供单一
线程安全、fn 在锁外执行的 TTL 缓存。

设计要点：
- ``_CACHE`` / ``_CACHE_LOCK`` 作为**唯一**真相源，供需要直接 ``_CACHE.clear()``
  的测试/历史兼容代码引用（fundflow、shepherd 将其别名到本模块同名对象）。
- ``cached_ttl`` 锁内快速读 / 锁内快速写；**fn() 在锁外执行**，避免慢速取数
  串行化所有键的缓存访问（R85 double-check）。
- Streamlit 的 ``@st.cache_data`` / ``@st.cache_resource`` 处理 DataFrame 哈希与
  跨 session 共享，不在本模块范围，保持不变。
"""

import threading
import time
from typing import Any, Callable, Dict, Tuple

# 全局共享缓存（按 key 字符串索引 -> (timestamp, value)）
_CACHE: Dict[str, Tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()


def cached_ttl(ttl: float, key: str, fn: Callable[[], Any]) -> Any:
    """基于时间戳的轻量 TTL 缓存。

    - 线程安全（锁内快速读 / 锁内快速写）。
    - fn() 在锁**外**执行，避免慢速取数串行化所有键的缓存访问。
    - 同一 key 的并发 miss 会重复计算（可接受权衡，fn 自身应有超时边界）。
    - ttl<=0 视作「永不过期」由调用方控制；本函数不做特判，过期判定即 ``(now-hit[0])<ttl``。
    """
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and (now - hit[0]) < ttl:
            return hit[1]
    # 锁外执行昂贵取数：不阻塞其他键的缓存访问
    val = fn()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), val)
    return val


def clear_cache() -> int:
    """清空全部缓存条目；返回被清除的条目数（诚实语义：返回真实删除行数）。"""
    with _CACHE_LOCK:
        n = len(_CACHE)
        _CACHE.clear()
    return n
