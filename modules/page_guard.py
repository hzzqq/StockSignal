"""
模块级错误边界与数据源隔离
================================
让每个功能模块「独立工作」——单点故障被隔离在局部，不会拖垮整页或跨模块污染。

提供四类工具：

1. safe_fragment(name, **frag_kwargs)
   - 装饰器，等价于 ``@st.fragment`` + 异常捕获。
   - 被装饰的区块（行情卡片 / 龙虎榜 / 复盘笔记 / 监控主表…）即使抛异常，
     也只在该区块内渲染「出错卡片」，不会整页变白 / 整页崩溃。
   - 出错卡片提供「🔄 重试本区块」按钮：调用 ``st.rerun(scope="fragment")``，
     只重跑当前 fragment（不整页重跑），符合 fragment 内禁整页 rerun 铁律。

2. safe_section(name, default=None)
   - 上下文管理器，包裹「一次数据取数 + 渲染」代码块。
   - 块内抛异常 → 渲染内联错误框（含区块名 + 错误摘要 + 折叠详情），
     并向调用方 yield 一个布尔表示是否成功，调用方可据此跳过依赖渲染。

3. page_error_boundary(name)
   - 上下文管理器，用于「整页级」兜底（包住页面主体逻辑）。
   - 与 safe_section 不同，页面级允许 st.rerun()，故提供「重试本页」按钮。

4. get_data_source_health() / render_data_degradation_banner()
   - 汇总 fetcher 各数据源成功率，页面顶部可调用横幅提示「数据降级」，
     让用户知道某些模块显示的是缓存 / 估算数据。
"""

import traceback

import streamlit as st
from contextlib import contextmanager


# ──────────────────────────────────────────────────────────
# 内联错误卡片（可复用）
# ──────────────────────────────────────────────────────────
def render_error_card(name: str, exc: Exception, *, retry: bool | str = False, hint: str = ""):
    """
    渲染一个内联错误卡片。

    :param name: 出错的模块 / 区块名（用于标题与按钮 key）。
    :param exc: 被捕获的异常。
    :param retry: 重试按钮行为：
        - False（默认）：无按钮。
        - True / "page"：页面级「重试本页」（整页 st.rerun()，仅页面级边界可用）。
        - "fragment"：片段级「重试」（st.rerun(scope="fragment")，只重跑当前 fragment，
          不整页重跑，可在 @safe_fragment 内安全使用）。
    :param hint: 额外提示文案。
    """
    err_type = type(exc).__name__
    summary = str(exc)
    if len(summary) > 200:
        summary = summary[:200] + " …"

    st.error(f"⚠️ **{name}** 加载失败（{err_type}）", icon="🧯")
    if hint:
        st.caption(hint)
    else:
        st.caption("该模块已被隔离，不会影响其它模块。刷新页面可重新加载。")
    with st.expander("查看错误详情", expanded=False):
        st.code(traceback.format_exc(limit=8), language="text")

    if retry:
        if retry == "fragment":
            # 片段级重试：只重跑当前 fragment，不整页重跑（符合 fragment 内禁整页 rerun 铁律）。
            if st.button("🔄 重试本区块", key=f"frag_retry_{name}", help="仅重新加载此模块"):
                st.rerun(scope="fragment")
        else:
            # 页面级重试（整页 st.rerun()）
            if st.button("🔄 重试本页", key=f"pg_retry_{name}", help="重新运行整个页面"):
                st.rerun()


# ──────────────────────────────────────────────────────────
# 1. Fragment 级隔离装饰器
# ──────────────────────────────────────────────────────────
def safe_fragment(name=None, **frag_kwargs):
    """
    装饰器：在 ``@st.fragment`` 之上再包一层异常捕获。

    两种用法均可（作为 ``@st.fragment`` 的「带错误边界」平替）::

        @safe_fragment("板块行情")          # 显式命名（错误卡片标题更可读）
        def fragment_sectors():
            ...

        @safe_fragment                       # 无括号，直接平替 @st.fragment
        def fragment_sectors():
            ...

    区块内任意未捕获异常都会被隔离为内联错误卡片，不会整页崩溃。
    """
    def decorator(func):
        # 标题：显式 name 优先；无括号用法时 name 即函数本身，取 __name__。
        _title = name if isinstance(name, str) else getattr(func, "__name__", "区块")
        @st.fragment(**frag_kwargs)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                # fragment 内：提供片段级「重试本区块」(st.rerun(scope="fragment") 不整页重跑)
                render_error_card(_title, exc, retry="fragment")
        wrapper.__name__ = getattr(func, "__name__", name)
        wrapper.__doc__ = getattr(func, "__doc__", None)
        return wrapper

    # 支持「无括号」用法：@safe_fragment 直接装饰函数时，name 即为函数本身。
    if callable(name):
        return decorator(name)
    return decorator


# ──────────────────────────────────────────────────────────
# 2. 代码块级隔离上下文管理器
# ──────────────────────────────────────────────────────────
@contextmanager
def safe_section(name: str, *, default=None, hint: str = ""):
    """
    上下文管理器：隔离「一次数据取数 + 渲染」代码块。

    用法::

        with safe_section("资金流向") as ok:
            if not ok:
                pass  # 已自动渲染错误卡片，跳过依赖渲染
            else:
                data = fetcher.get_xxx(code)
                st.plotly_chart(...)

    :yields: bool —— 代码块是否成功执行（False 表示已被异常隔离）。
    """
    ok = True
    try:
        yield ok
    except Exception as exc:  # noqa: BLE001
        ok = False
        render_error_card(name, exc, hint=hint)
    finally:
        pass


# ──────────────────────────────────────────────────────────
# 3. 整页级兜底上下文管理器
# ──────────────────────────────────────────────────────────
@contextmanager
def page_error_boundary(name: str):
    """
    整页级错误边界（包住页面主体逻辑）。

    与 safe_section 不同，页面级允许 st.rerun()，故提供「重试本页」按钮。

    用法::

        def main():
            ...
        with page_error_boundary("行情看板"):
            main()
    """
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        render_error_card(name, exc, retry=True)


# ──────────────────────────────────────────────────────────
# 4. 数据源健康度
# ──────────────────────────────────────────────────────────
def get_data_source_health():
    """
    汇总 fetcher 各数据源成功率，返回整体健康度。

    :returns: dict{status, degraded[], down[], sources{}}
        status ∈ {"ok", "degraded", "down", "unknown"}
    """
    try:
        from modules.fetcher import get_source_metrics
    except Exception:
        return {"status": "unknown", "degraded": [], "down": [], "sources": {}}

    metrics = get_source_metrics()
    if not metrics:
        return {"status": "unknown", "degraded": [], "down": [], "sources": {}}

    degraded, down = [], []
    for src, stat in metrics.items():
        calls = stat.get("calls", 0)
        if calls == 0:
            continue
        sr = stat.get("success_rate", 1.0)
        if sr < 0.5:
            down.append(src)
        elif sr < 0.95:
            degraded.append(src)

    if down:
        status = "down"
    elif degraded:
        status = "degraded"
    else:
        status = "ok"
    return {"status": status, "degraded": degraded, "down": down, "sources": metrics}


def render_data_degradation_banner():
    """
    页面顶部可选调用：若检测到数据源降级 / 不可用，渲染提示横幅。
    健康时无任何输出。
    """
    h = get_data_source_health()
    if h["status"] == "ok" or h["status"] == "unknown":
        return
    if h["status"] == "down":
        bad = ", ".join(h["down"])
        st.error(
            f"⚠️ 部分数据源当前不可用（{bad}），相关模块已自动降级或展示缓存数据。",
            icon="📡",
        )
    else:
        bad = ", ".join(h["degraded"])
        st.warning(
            f"⚠️ 部分数据源不稳定（{bad}），部分数据可能延迟或为估算值。",
            icon="📡",
        )
