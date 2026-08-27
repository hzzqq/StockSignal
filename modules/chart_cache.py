"""图表 figure 构建缓存基础设施。

问题背景
--------
StockSignal 前端存在大量 Plotly figure，在每次脚本重跑（含交易时段
``st_autorefresh`` 每 60s 重跑）时都从头 rebuild，造成可观测的 CPU 浪费。
本模块提供 ``cached_fig`` 装饰器，把「纯函数式的 figure 构建」缓存起来，
按入参哈希（含 pandas DataFrame）命中，避免重复重建图形。

设计原则（遵循项目性能铁律）
----------------------------
- 加法式、非破坏性：只缓存，不改变任何业务逻辑 / 数据 / DOM。
- 不改变调用方语义：装饰后的函数与原函数签名一致，返回同一 figure 对象。
- 无 XSS 风险：figure 构建本身不拼接外部文本。

缓存键唯一性说明
----------------
``@st.cache_data`` 的缓存键由 ``(模块名, __qualname__, 函数字节码)`` 决定。
若直接用工厂函数包裹，所有被装饰的 builder 都会得到相同的内部 ``_cached``
qualname，从而在相同入参下发生「跨函数命中」的灾难性错位（例如
``build_kline_fig("A")`` 与 ``build_fundflow_fig("A")`` 返回同一张图）。
因此本装饰器在包装时把内部函数的 ``__qualname__`` / ``__name__`` 改写为
``<builder 名>__cached``，确保每张图拥有独立且稳定的缓存键。

约束：同一 builder 函数只应被 ``cached_fig`` 装饰一次（否则两次装饰会因
相同 qualname 共享同一缓存槽，ttl 以首次注册为准）。
"""

from __future__ import annotations

import functools

import streamlit as st


def cached_fig(ttl: int = 600):
    """装饰一个「figure 构建函数」，按入参哈希缓存其返回值（Plotly Figure）。

    适用场景：被装饰函数应为纯函数（相同入参返回相同 figure），入参需可被
    Streamlit 哈希（原生支持 pandas DataFrame / Series / 基本类型 / dataclass 等）。

    Args:
        ttl: 缓存有效期（秒）。带 ``st_autorefresh`` 的页建议 60~120；
             静态图可设更大（默认 600）。

    Returns:
        与原始函数签名一致、但带缓存的包装函数。可通过 ``__wrapped__``
        访问原始 builder（用于测试或强制绕过缓存）。
    """
    if ttl <= 0:
        raise ValueError("cached_fig: ttl 必须为正数（秒）")

    def decorator(builder):
        # show_spinner=False：命中缓存应是瞬时的，避免 UI 闪烁
        @st.cache_data(ttl=ttl, show_spinner=False)
        def _cached(*args, **kwargs):
            return builder(*args, **kwargs)

        # 关键：改写 qualname/name，避免 Streamlit 缓存键在不同 builder 间碰撞
        _cached.__name__ = f"{builder.__name__}__cached"
        _cached.__qualname__ = f"{builder.__qualname__}__cached"
        _cached.__doc__ = builder.__doc__
        _cached.__wrapped__ = builder  # 保留原始函数引用，便于测试/强制重建
        return _cached

    return decorator
