"""共享的「带硬边界、不泄漏线程」的超时执行器。

此前 ``_run_with_timeout`` 每次调用都新建 ``ThreadPoolExecutor(max_workers=1)`` 并在超时后
``shutdown(wait=False)`` 丢弃仍在阻塞的工作线程——盯盘页并发抓全自选股时会泄漏一堆
持 socket 的非守护线程（线程泄漏架构债）。

新实现：
- 使用进程级**共享、有界**线程池（module-level 单例），线程复用，不随每次调用新建。
- 底层网络（requests + socket）默认超时 = REQUEST_TIMEOUT(10s) < 每调用硬边界
  CALL_TIMEOUT_CAP(12s)，因此阻塞的网络调用会先被传输层超时唤醒、fn 内部异常捕获后
  正常返回，``future`` 在硬边界内完成，**无需丢弃线程**，线程回到池中复用，从根上消除泄漏。

对「非网络阻塞」（纯 CPU / time.sleep）的 fn，硬边界仍会触发并返回 None（线程在后台
被传输层无关地等待 join 直到池回收），但这类场景在取数路径上不存在，不影响正确性。
"""
import concurrent.futures as cf
import threading
import logging

from modules.site_config import REQUEST_TIMEOUT, CALL_TIMEOUT_CAP

logger = logging.getLogger(__name__)

_POOL = None
_POOL_LOCK = threading.Lock()
_MAX_WORKERS = 16


def _pool():
    """惰性创建进程级共享有界线程池（单例）。"""
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = cf.ThreadPoolExecutor(
                    max_workers=_MAX_WORKERS, thread_name_prefix="ss-net"
                )
    return _POOL


def run_with_timeout(fn, timeout=None):
    """在共享线程池执行 fn；超时 / 异常返回 None，由调用方决定兜底值。

    由于底层网络默认超时(10s) < 此处硬边界(默认 12s)，正常阻塞路径下 fn 会在边界内
    自行返回（其内部网络调用已被传输层超时唤醒），线程回到池中复用，不泄漏。
    """
    timeout = timeout or CALL_TIMEOUT_CAP
    try:
        fut = _pool().submit(fn)
    except Exception as e:  # 极端情况（如池关闭）直接兜底
        logger.warning("[timeout_exec] 提交失败：%s", e)
        return None
    try:
        return fut.result(timeout=timeout)
    except cf.TimeoutError:
        logger.warning(
            "[timeout_exec] %s 超时(%.1fs)，返回 None",
            getattr(fn, "__name__", "fn"), timeout,
        )
        # 若任务尚未开始则取消；若已在运行，靠传输层超时被唤醒后自然结束、回池。
        try:
            fut.cancel()
        except Exception:
            pass
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[timeout_exec] %s 异常：%s", getattr(fn, "__name__", "fn"), e)
        return None
