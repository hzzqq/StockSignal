"""并发取数助手：把页面里串行发起的多个独立网络调用并行化，显著缩短首屏等待。

与 timeout_exec 共用共享线程池，每个任务都有硬边界（不会无限阻塞），且底层
网络超时 < 任务边界，不泄漏线程。

典型用法（页面首屏一次性并发预取多路数据）：::

    @st.cache_data(show_spinner=False, ttl=300)
    def _prefetch_all():
        tasks = [
            ("northbound", get_northbound_fund_flow),
            ("industry", get_industry_fund_flow),
            ("market", lambda: get_market_fund_flow(days=30)),
            ...
        ]
        return fetch_many(tasks, max_workers=6, timeout=14)

    data = _prefetch_all()          # 并发跑完，最坏 ~14s（而非各路串行之和）
    nb = data.get("northbound")
"""
import concurrent.futures as cf
import logging

from modules.timeout_exec import _pool
from modules.site_config import FETCH_MAX_WORKERS, CALL_TIMEOUT_CAP

logger = logging.getLogger(__name__)


def _safe(fn):
    """包装：任务内任何异常都转成 None，绝不让单个取数拖垮整批。"""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def fetch_many(tasks, max_workers=None, timeout=None):
    """并发执行多个取数任务。

    :param tasks: 可迭代的 ``(key, callable)`` 二元组。
    :param max_workers: 并发度（默认 site_config.FETCH_MAX_WORKERS）。
    :param timeout: 单任务硬边界（秒，默认 site_config.CALL_TIMEOUT_CAP）。
    :returns: ``dict{key: result}``，任务超时 / 异常对应值为 None。
    """
    if max_workers is None:
        max_workers = FETCH_MAX_WORKERS
    if timeout is None:
        timeout = CALL_TIMEOUT_CAP

    out = {}
    # 用共享有界池提交；as_completed 逐结果收集，单任务超时被捕获为 None。
    # 因底层网络默认超时 < 此处 timeout，正常路径下每个 future 都在 timeout 内完成，
    # 不会丢弃线程。
    futs = {_pool().submit(_safe, fn): key for key, fn in tasks}
    for fut in cf.as_completed(list(futs)):
        key = futs[fut]
        try:
            out[key] = fut.result(timeout=timeout)
        except Exception:  # noqa: BLE001  TimeoutError / 任何异常 -> None
            out[key] = None
    return out
